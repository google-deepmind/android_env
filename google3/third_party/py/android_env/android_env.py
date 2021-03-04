"""Android environment implementation."""

import copy
import datetime
import time

from typing import Any, Dict
from absl import logging
from android_env.components import action_type
from android_env.components import adb_controller
from android_env.components import base_simulator
from android_env.components import remote_controller
from android_env.components import specs
from android_env.proto import task_pb2
import dm_env
import numpy as np


StepType = dm_env.StepType


class AndroidEnv(dm_env.Environment):
  """An environment to play Android games."""

  def __init__(self,
               simulator: base_simulator.BaseSimulator,
               task: task_pb2.Task,
               max_bad_states: int = 3,
               dumpsys_check_frequency: int = 150,
               max_failed_current_activity: int = 10,
               step_timeout_sec: int = 10,
               expected_fps: int = 5,
               periodic_restart_time_min: float = 0.0):
    """Instantiate an Android environment."""

    self._task = task
    self._is_closed = False
    self._latest_action = {}
    self._latest_observation = {}
    self._latest_extras = {}
    self._latest_step_type = StepType.LAST
    self._reset_next_step = True
    self._task_start_time = None

    self._episode_cumulative_internal_time = 0.0
    self._episode_cumulative_external_time = 0.0
    self._episode_max_external_time = 0.0
    self._episode_max_internal_time = 0.0

    # Initialize remote controller
    self._remote_controller = remote_controller.RemoteController(
        simulator=simulator,
        task=task,
        max_bad_states=max_bad_states,
        dumpsys_check_frequency=dumpsys_check_frequency,
        max_failed_current_activity=max_failed_current_activity,
        step_timeout_sec=step_timeout_sec,
        expected_fps=expected_fps,
        periodic_restart_time_min=periodic_restart_time_min)

    # Logging settings
    self._log_dict = {
        'wrong_step_type_count': 0,
        'restart_count': 0,  # Counts unexpected simulator restarts.
        'reset_count_step_timeout': 0,
        'reset_count_player_exited': 0,
        'reset_count_episode_end': 0,
        'reset_count_max_duration_reached': 0,
    }
    self._log_prefixes = ['androidenv_total', 'androidenv_episode']
    for prefix in self._log_prefixes:
      self._log_dict[f'{prefix}_steps'] = 0.0
      for act_type in action_type.ActionType:
        self._log_dict[f'{prefix}_action_type_{act_type.name}'] = 0.0

    # Log init info
    logging.info('Task config: %s', self._task)
    logging.info('Action spec: %s', self.action_spec())
    logging.info('Observation spec: %s', self.observation_spec())
    logging.info('Task extras spec: %s', self.task_extras_spec())

  def action_spec(self) -> Dict[str, dm_env.specs.Array]:
    return specs.base_action_spec()

  def observation_spec(self) -> Dict[str, dm_env.specs.Array]:
    return specs.base_observation_spec(
        screen_dimension=self._remote_controller.screen_dimensions)

  def task_extras_spec(self) -> Dict[str, dm_env.specs.Array]:
    return specs.task_extras_spec(task=self._task)

  @property
  def raw_action(self):
    return self._latest_action

  @property
  def raw_observation(self):
    return self._latest_observation

  def reset(self) -> dm_env.TimeStep:
    """Reset the environment."""

    logging.info('Resetting AndroidEnv.')
    self._remote_controller.reset()

    # Reset relevant values
    self._latest_action = {}
    self._reset_log_dict()
    self._task_start_time = datetime.datetime.now()

    # Fetch observation and task_extras from remote controller
    observation = self._remote_controller.get_current_observation()
    task_extras = self._remote_controller.get_current_extras()
    if observation is not None:
      self._latest_observation = observation.copy()
    self._latest_extras = task_extras.copy()

    # Validate FIRST step type
    self._reset_next_step = False
    step_type = StepType.FIRST
    self._validate_step_type(step_type)
    self._latest_step_type = step_type

    self._step_exit_time = time.time()

    logging.info('Done resetting AndroidEnv.')
    logging.info('************* NEW EPISODE *************')

    return dm_env.TimeStep(
        step_type=self._latest_step_type,
        observation=self._latest_observation,
        reward=0.0,
        discount=0.0)

  def step(self, action: Dict[str, np.ndarray]) -> dm_env.TimeStep:
    """Take a step in the environment."""
    step_start_time = time.time()
    external_time = step_start_time - self._step_exit_time
    self._episode_max_external_time = max(self._episode_max_external_time,
                                          external_time)
    self._episode_cumulative_external_time += external_time

    self._latest_action = action.copy()

    # Check if remote controller has to be restarted
    if self._remote_controller.should_restart:
      self._log_dict['restart_count'] += 1
      self._remote_controller.restart()
      return self._last_timestep()

    if self._remote_controller.check_timeout():
      self._log_dict['reset_count_step_timeout'] += 1
      logging.info('Step has timed out. Ending episode.')
      return self._last_timestep()

    # Check if it's time to reset the episode
    if self._reset_next_step:
      return self.reset()

    # Validate and perform action
    self._validate_action(action)
    self._remote_controller.execute_action(action)
    self._update_log_dict(act_type=action['action_type'].item())

    # Fetch observation, reward and task_extras from remote controller
    observation = self._remote_controller.get_current_observation()
    task_extras = self._remote_controller.get_current_extras()
    reward = self._remote_controller.get_current_reward()
    if observation is not None:
      self._latest_observation = observation.copy()
    self._latest_extras = task_extras.copy()

    # Determine and validate step type
    self._reset_next_step = self._check_if_should_terminate()
    step_type = StepType.LAST if self._reset_next_step else StepType.MID
    self._validate_step_type(step_type)
    self._latest_step_type = step_type

    self._step_exit_time = time.time()
    internal_time = self._step_exit_time - step_start_time
    self._episode_max_internal_time = max(self._episode_max_internal_time,
                                          internal_time)
    self._episode_cumulative_internal_time += internal_time

    # Return timestep with reward and observation just computed
    return dm_env.TimeStep(
        step_type=self._latest_step_type,
        observation=self._latest_observation,
        reward=reward,
        discount=0.0 if self._reset_next_step else 1.0)

  def _last_timestep(self) -> dm_env.TimeStep:
    """Creates and returns the last timestep of an episode."""

    self._reset_next_step = True
    step_type = StepType.LAST
    self._validate_step_type(step_type)
    self._latest_step_type = step_type

    return dm_env.TimeStep(
        step_type=self._latest_step_type,
        observation=self._latest_observation,
        reward=0.0,
        discount=0.0)

  def _check_if_should_terminate(self) -> bool:
    """Determines whether the episode should be terminated and reset."""

    # Fetch reward from remote controller
    if self._remote_controller.check_player_exited():
      self._log_dict['reset_count_player_exited'] += 1
      logging.warning('Player exited the game. Ending episode.')
      logging.info('************* END OF EPISODE *************')
      return True

    # Check if episode has ended
    if self._remote_controller.check_episode_end():
      self._log_dict['reset_count_episode_end'] += 1
      logging.info('End of episode from logcat! Ending episode.')
      logging.info('************* END OF EPISODE *************')
      return True

    # Check if step limit or time limit has been reached
    if self._task.max_num_steps > 0:
      episode_steps = self._log_dict['androidenv_episode_steps']
      if episode_steps > self._task.max_num_steps:
        self._log_dict['reset_count_max_duration_reached'] += 1
        logging.info('Maximum task duration (steps) reached. Ending episode.')
        logging.info('************* END OF EPISODE *************')
        return True

    if self._task.max_duration_sec > 0.0:
      task_duration = datetime.datetime.now() - self._task_start_time
      max_duration_sec = self._task.max_duration_sec
      if task_duration > datetime.timedelta(seconds=int(max_duration_sec)):
        self._log_dict['reset_count_max_duration_reached'] += 1
        logging.info('Maximum task duration (sec) reached. Ending episode.')
        logging.info('************* END OF EPISODE *************')
        return True

    return False

  def _validate_action(self, action: Dict[str, np.ndarray]) -> None:
    """Confirm that the action conforms to the action spec."""

    assert set(action.keys()) == set(self.action_spec().keys())
    for key, spec in self.action_spec().items():
      spec.validate(action[key])

  def _validate_step_type(self, step_type: StepType) -> None:
    """Confirms that step_types follow each other in the correct order."""

    if (self._latest_step_type, step_type) in [
        (StepType.FIRST, StepType.FIRST),
        (StepType.MID, StepType.FIRST),
        (StepType.LAST, StepType.MID),
        (StepType.LAST, StepType.LAST)
    ]:
      self._log_dict['wrong_step_type_count'] += 1
      logging.warning('%r -> %r', self._latest_step_type.name, step_type.name)

  def task_extras(self, latest_only: bool = True) -> Dict[str, np.ndarray]:
    """Return latest task extras."""

    task_extras = {}
    for key, spec in self.task_extras_spec().items():
      if key in self._latest_extras:
        extra_values = self._latest_extras[key].astype(spec.dtype)
        for extra in extra_values:
          spec.validate(extra)
        task_extras[key] = extra_values[-1] if latest_only else extra_values
    return task_extras

  def android_logs(self) -> Dict[str, Any]:
    """Expose internal counter values."""
    return self._flush_log_dict()

  def _update_log_dict(self, act_type: int) -> None:
    """Increment internal counters."""

    act_type = action_type.ActionType(act_type)
    for prefix in self._log_prefixes:
      self._log_dict[f'{prefix}_steps'] += 1
      self._log_dict[f'{prefix}_action_type_{act_type.name}'] += 1

  def _flush_log_dict(self) -> Dict[str, Any]:
    """Return internal counter values."""

    log_dict = copy.deepcopy(self._log_dict)
    log_dict.update(self._remote_controller.log_dict())
    for prefix in self._log_prefixes:
      if log_dict[f'{prefix}_steps'] == 0:
        logging.warning('%s_steps is 0. Skipping ratio logs.', prefix)
        continue
      for act_type in action_type.ActionType:
        log_dict[f'{prefix}_action_type_ratio_{act_type.name}'] = log_dict[
            f'{prefix}_action_type_{act_type.name}'] / log_dict[
                f'{prefix}_steps']
    episode_steps = log_dict['androidenv_episode_steps']
    if episode_steps:
      log_dict['time_per_step_external_mean'] = (
          self._episode_cumulative_external_time / episode_steps)
      log_dict['time_per_step_internal_mean'] = (
          self._episode_cumulative_internal_time / episode_steps)
      log_dict['time_per_step_external_max'] = self._episode_max_external_time
      log_dict['time_per_step_internal_max'] = self._episode_max_internal_time

    return log_dict

  def _reset_log_dict(self) -> None:
    """Reset internal counter values."""

    for key in self._log_dict:
      if key.startswith('androidenv_episode'):
        self._log_dict[key] = 0.0
    self._episode_cumulative_internal_time = 0.0
    self._episode_cumulative_external_time = 0.0
    self._episode_max_external_time = 0.0
    self._episode_max_internal_time = 0.0

  def create_adb_controller(self) -> adb_controller.AdbController:
    """Creates an adb_controller and transfer ownership to the caller."""
    return self._remote_controller.create_adb_controller()

  def close(self) -> None:
    """Clean up running processes, threads and local files."""

    logging.info('Cleaning up AndroidEnv...')
    if hasattr(self, '_remote_controller'):
      self._remote_controller.close()
    self._is_closed = True
    logging.info('Done cleaning up AndroidEnv.')

  def __del__(self) -> None:
    if not self._is_closed:
      self.close()
