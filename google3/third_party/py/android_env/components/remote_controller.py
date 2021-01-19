# Lint as: python3
"""RemoteController handles the communication with AndroidOS."""

import copy
import queue
import socket
import time
from typing import Any, Dict, Optional

from absl import logging
from android_env.components import action_type
from android_env.components import adb_controller
from android_env.components import app_screen_checker
from android_env.components import base_simulator
from android_env.components import dumpsys_thread
from android_env.components import errors
from android_env.components import setup_step_interpreter
from android_env.proto import task_pb2
import numpy as np


_MAX_SIMULATOR_INIT_TRIES = 3
_MAX_RESTART_TRIES = 3


class RemoteController():
  """Handles communication between AndroidEnv and AndroidOS."""

  def __init__(
      self,
      simulator: base_simulator.BaseSimulator,
      max_bad_states: int,
      dumpsys_check_frequency: int,
      max_failed_current_activity: int,
      step_timeout_sec: int,
      expected_fps: int,
      task_config: task_pb2.Task,
      periodic_restart_time_min: float = 0.0,
  ):
    """Handles communication between AndroidEnv and AndroidOS.

    Args:
      simulator: A BaseSimulator Instance.
      max_bad_states: How many bad states in a row are allowed before a restart
        of the simulator is triggered.
      dumpsys_check_frequency: Frequency, in steps, at which to check
        current_activity and view hierarchy
      max_failed_current_activity: The maximum number of tries for extracting
        the current activity before forcing the episode to restart.
      step_timeout_sec: Timeout in seconds between steps. If step is not called
        within that time, the episode will reset at the next step. Set to 0 to
        disable.
      expected_fps: Maximum steps per second. If the simulator is faster,
        RemoteController will wait before returning an observation.
      task_config: A task proto defining the RL task.
      periodic_restart_time_min: Time between periodic restarts in minutes. If >
        0.0, will trigger a simulator restart at the end of the next episode
        once the time has been reached.
    """
    self._simulator = simulator
    self._max_bad_states = max_bad_states
    self._dumpsys_check_frequency = dumpsys_check_frequency
    self._max_failed_current_activity = max_failed_current_activity
    self._step_timeout_sec = step_timeout_sec
    self._expected_fps = expected_fps
    self._task_config = task_config
    self._periodic_restart_time_min = periodic_restart_time_min

    # Logging settings
    self._log_dict = {
        'restart_count_adb_crash': 0,
        'restart_count_fetch_observation': 0,
        'restart_count_simulator_setup': 0,
        'restart_count_simulator_reset': 0,
        'restart_count_simulator_restart': 0,
        'restart_count_restart_setup_steps': 0,
        'restart_count_execute_action': 0,
        'restart_count_max_bad_states': 0,
        'restart_count_periodic': 0,
    }

    # Initialize counters
    self._should_restart = False
    self._bad_state_counter = 0
    self._is_bad_episode = False
    self._latest_observation_local_time = None
    self._latest_reward = None
    self._simulator_start_time = None
    self._launch_simulator()
    self._start_logcat_thread()

    self._setup_step_interpreter = setup_step_interpreter.SetupStepInterpreter(
        self._adb_controller, logcat=self._logcat_thread)

    # Execute setup steps
    try:
      self._setup_step_interpreter.interpret(self._task_config.setup_steps)
    except errors.StepCommandError:
      logging.exception('Failed to execute setup steps. Restarting simulator.')
      self._log_dict['restart_count_simulator_setup'] += 1
      self.restart()
      return

  @property
  def screen_dimensions(self) -> np.ndarray:
    return self._simulator.screen_dimensions

  @property
  def should_restart(self) -> bool:
    return self._should_restart

  def log_dict(self) -> Dict[str, Any]:
    log_dict = copy.deepcopy(self._log_dict)
    log_dict.update(self._setup_step_interpreter.log_dict())
    return log_dict

  def restart(self):
    """Restarts the remote controller."""

    logging.info('Restarting the remote controller...')

    # Reset counters
    self._should_restart = False
    self._bad_state_counter = 0

    # Pause both threads for the duration of the restart
    self._stop_dumpsys_thread()
    self._stop_logcat_thread()

    num_tries = 1
    while True:
      if num_tries > _MAX_RESTART_TRIES:
        logging.error('Maximum number of restarts reached.')
        raise errors.TooManyRestartsError
      logging.info('Restart attempt %d of %d', num_tries, _MAX_RESTART_TRIES)

      # Restart the simulator
      try:
        self._simulator.restart()
        self._adb_controller = self._simulator.create_adb_controller()
        self._simulator_start_time = time.time()
      except errors.AdbControllerError:
        logging.error('Error restarting the simulator.')
        self._log_dict['restart_count_simulator_restart'] += 1
        num_tries += 1
        continue

      # Execute setup steps
      try:
        self._setup_step_interpreter.interpret(self._task_config.setup_steps)
      except errors.StepCommandError:
        logging.error('Failed to execute setup steps. Restarting simulator.')
        self._log_dict['restart_count_restart_setup_steps'] += 1
        num_tries += 1
        continue

      # Restart was successful
      break

    # Restart logcat thread
    self._start_logcat_thread()

    logging.info('Done restarting the remote controller.')

  def reset(self):
    """Resets the episode."""

    simulator_alive_time = (time.time() - self._simulator_start_time) / 60.0
    logging.info('Simulator has been running for %f minutes',
                 simulator_alive_time)
    if (self._periodic_restart_time_min > 0.0 and
        simulator_alive_time > self._periodic_restart_time_min):
      logging.info(
          'Max alive time for simulator has been reached. Triggering a restart.'
      )
      # These restarts will not be counted in the 'restart_count' logging, as
      # this is part of the expected behavior.
      self._log_dict['restart_count_periodic'] += 1
      self.restart()

    logging.info('Resetting the remote controller...')

    # Execute a lift action before resetting
    self.execute_action({
        'action_type': np.array(action_type.ActionType.LIFT),
        'touch_position': np.array([0, 0])
    })

    # Reset counters
    self._latest_observation_local_time = None
    self._latest_reward = None
    if not self._is_bad_episode:
      self._bad_state_counter = 0
    self._is_bad_episode = False

    # Pause dumpsys thread for the duration of the reset
    self._stop_dumpsys_thread()

    # Execute reset steps
    try:
      self._setup_step_interpreter.interpret(self._task_config.reset_steps)
    except errors.StepCommandError:
      logging.exception('Failed to execute reset steps. Restarting simulator.')
      self._log_dict['restart_count_simulator_reset'] += 1
      self._should_restart = True
      return

    self._simulator.update_device_orientation()
    self._logcat_thread.reset_counters()

    # Restart dumpsys thread
    self._start_dumpsys_thread()

    logging.info('Done resetting the remote controller.')

  def get_current_reward(self) -> float:
    self._latest_reward = self._logcat_thread.get_and_reset_reward()
    return self._fetch_latest_reward()

  def get_current_extras(self) -> Dict[str, Any]:
    return self._logcat_thread.get_and_reset_extras()

  def check_player_exited(self) -> bool:
    """Returns whether the player has exited the game."""
    try:
      self._check_player_exited_impl()
      return False
    except errors.NotAllowedError:
      return True

  def _check_player_exited_impl(self):
    """Raises an error if the OS is not in an allowed state."""

    self._dumpsys_thread.write(
        dumpsys_thread.DumpsysThread.Signal.FETCH_DUMPSYS)

    try:
      v = self._dumpsys_thread.read(block=False)
      if v == dumpsys_thread.DumpsysThread.Signal.USER_EXITED_ACTIVITY:
        self._increment_bad_state()
        raise errors.PlayerExitedActivityError()
      elif v == dumpsys_thread.DumpsysThread.Signal.USER_EXITED_VIEW_HIERARCHY:
        self._increment_bad_state()
        raise errors.PlayerExitedViewHierarchyError()
    except queue.Empty:
      pass  # Don't block here, just ignore if we have nothing.

  def check_episode_end(self) -> bool:
    """Returns whether the episode ended from the output of `adb logcat`."""
    return self._logcat_thread.get_and_reset_episode_end()

  def get_current_observation(
      self,
      wait_for_next_frame: bool = True
  ) -> Optional[Dict[str, np.ndarray]]:
    """Returns pixels from the screen."""

    if wait_for_next_frame:
      self._wait_for_next_frame()

    try:
      self._latest_observation_local_time = time.time()
      return self._simulator.get_observation()
    except (errors.ReadObservationError, socket.error):
      logging.exception('Unable to fetch observation. Restarting simulator.')
      self._log_dict['restart_count_fetch_observation'] += 1
      self._should_restart = True
      return None

  def check_timeout(self) -> bool:
    """Checks if timeout between steps have exceeded."""
    if self._step_timeout_sec:
      time_since_last_obs = self._get_time_since_last_observation()
      if time_since_last_obs > self._step_timeout_sec:
        return True
    return False

  def execute_action(self, action: Dict[str, np.ndarray]):
    """Applies the action from the agent."""

    if action['action_type'].item() == action_type.ActionType.REPEAT:
      return

    try:
      self._simulator.send_action(action)
    except (socket.error, errors.SendActionError):
      logging.exception('Unable to execute action. Restarting simulator.')
      self._log_dict['restart_count_execute_action'] += 1
      self._should_restart = True

  def create_adb_controller(self) -> adb_controller.AdbController:
    """Creates an adb_controller and transfer ownership to the caller."""
    return self._simulator.create_adb_controller()

  def close(self):
    """Cleans up the state of this RemoteController."""
    logging.info('Cleaning up remote controller...')
    if hasattr(self, '_logcat_thread'):
      self._logcat_thread.kill()
    if hasattr(self, '_dumpsys_thread'):
      self._dumpsys_thread.kill()
    if hasattr(self, '_simulator'):
      self._simulator.close()
    logging.info('Done cleaning up remote controller.')

  def _launch_simulator(self):
    """Launches the simulator for the first time."""

    num_tries = 0
    while num_tries < _MAX_SIMULATOR_INIT_TRIES:
      num_tries += 1
      try:
        self._simulator.launch()
        self._adb_controller = self._simulator.create_adb_controller()
        self._simulator_start_time = time.time()
        return
      except errors.AdbControllerError:
        logging.warning('Error launching the simulator. Try %d of %d',
                        num_tries, _MAX_SIMULATOR_INIT_TRIES)

    logging.error('Remote controller is unable to launch the simulator.')
    raise errors.RemoteControllerInitError()

  def _start_logcat_thread(self):
    """Starts a logcat thread."""
    logcat_filters = ['AndroidRLTask:V', '*:S']
    if self._task_config.log_tag:
      logcat_filters.append('{}:V'.format(self._task_config.log_tag))
    self._logcat_thread = self._adb_controller.create_logcat_thread(
        logcat_filters,
        log_prefix=self._task_config.log_prefix,
        print_all_lines=False)

  def _start_dumpsys_thread(self):
    """Starts a dumpsys thread."""
    self._dumpsys_thread = dumpsys_thread.DumpsysThread(
        app_screen_checker=app_screen_checker.AppScreenChecker(
            self._adb_controller, self._task_config.expected_app_screen),
        check_frequency=self._dumpsys_check_frequency,
        max_failed_current_activity=self._max_failed_current_activity,
        block_input=True,
        block_output=True)

  def _stop_logcat_thread(self):
    if hasattr(self, '_logcat_thread'):
      self._logcat_thread.kill()

  def _stop_dumpsys_thread(self):
    if hasattr(self, '_dumpsys_thread'):
      self._dumpsys_thread.kill()

  def _fetch_latest_reward(self):
    if self._latest_reward is not None:
      reward = self._latest_reward
      self._latest_reward = None
      return reward
    else:
      return 0.0

  def _get_time_since_last_observation(self) -> float:
    if self._latest_observation_local_time is not None:
      return time.time() - self._latest_observation_local_time
    else:
      return np.inf

  def _wait_for_next_frame(self) -> None:
    """Pauses the environment so that the interaction is around 1/FPS."""

    time_since_observation = self._get_time_since_last_observation()
    logging.debug('Time since obs: %0.6f', time_since_observation)

    time_to_wait = 1. / self._expected_fps - time_since_observation
    if time_to_wait > 0.0:
      time.sleep(time_to_wait)

  def _increment_bad_state(self) -> None:
    """Increments the bad state counter.

    Bad states are errors that shouldn't happen and that trigger an
    episode reset. If enough bad states have been seen consecutively,
    we restart the simulation in the hope of returning the simulation
    to a good state.
    """
    logging.warning('Bad state detected.')
    if self._max_bad_states:
      self._is_bad_episode = True
      self._bad_state_counter += 1
      logging.warning('Bad state counter: %d.', self._bad_state_counter)
      if self._bad_state_counter >= self._max_bad_states:
        logging.error('Too many consecutive bad states. Restarting simulator.')
        self._log_dict['restart_count_max_bad_states'] += 1
        self._should_restart = True
    else:
      logging.warning('Max bad states not set, bad states will be ignored.')
