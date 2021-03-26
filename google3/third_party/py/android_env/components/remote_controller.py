"""RemoteController handles the communication with AndroidOS."""

import copy
import queue
import socket
import time
from typing import Any, Dict, Optional, Tuple

from absl import logging
from android_env.components import action_type
from android_env.components import app_screen_checker
from android_env.components import base_simulator
from android_env.components import dumpsys_thread
from android_env.components import errors
from android_env.components import logcat_thread
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
      task: task_pb2.Task,
      max_bad_states: int = 3,
      dumpsys_check_frequency: int = 150,
      max_failed_current_activity: int = 10,
      step_timeout_sec: int = 10,
      max_steps_per_sec: float = 5.0,
      periodic_restart_time_min: float = 0.0,
      force_simulator_launch: bool = True,
  ):
    """Handles communication between AndroidEnv and AndroidOS.

    Args:
      simulator: A BaseSimulator Instance.
      task: A task proto defining the RL task.
      max_bad_states: How many bad states in a row are allowed before a restart
        of the simulator is triggered.
      dumpsys_check_frequency: Frequency, in steps, at which to check
        current_activity and view hierarchy
      max_failed_current_activity: The maximum number of tries for extracting
        the current activity before forcing the episode to restart.
      step_timeout_sec: Timeout in seconds between steps. If step is not called
        within that time, the episode will reset at the next step. Set to 0 to
        disable.
      max_steps_per_sec: Maximum steps per second. If the simulator is
        faster, RemoteController will wait before returning an observation.
      periodic_restart_time_min: Time between periodic restarts in minutes. If >
        0.0, will trigger a simulator restart at the end of the next episode
        once the time has been reached.
      force_simulator_launch: Forces the simulator to relaunch even if it is
        already launched.
    """
    self._simulator = simulator
    self._task = task
    self._max_bad_states = max_bad_states
    self._dumpsys_check_frequency = dumpsys_check_frequency
    self._max_failed_current_activity = max_failed_current_activity
    self._step_timeout_sec = step_timeout_sec
    self._max_steps_per_sec = max_steps_per_sec
    self._periodic_restart_time_min = periodic_restart_time_min
    self._force_simulator_launch = force_simulator_launch

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
    self._simulator_start_time = None

    self._launch_simulator()
    self._start_logcat_thread()

    self._setup_step_interpreter = setup_step_interpreter.SetupStepInterpreter(
        self._adb_controller, logcat=self._logcat_thread)

    # Execute setup steps
    try:
      self._setup_step_interpreter.interpret(self._task.setup_steps)
    except errors.StepCommandError:
      logging.exception('Failed to execute setup steps. Restarting simulator.')
      self._log_dict['restart_count_simulator_setup'] += 1
      self.restart()
      return

  def _launch_simulator(self):
    """Launches the simulator for the first time."""

    num_tries = 0
    while num_tries < _MAX_SIMULATOR_INIT_TRIES:
      num_tries += 1
      try:
        if self._force_simulator_launch or not self._simulator.is_launched():
          self._simulator.launch()
          self._simulator_start_time = time.time()
        else:
          logging.info('Simulator already launched. Will not relaunch it.')
        self._adb_controller = self._simulator.create_adb_controller()
        return
      except errors.AdbControllerError:
        logging.warning('Error launching the simulator. Try %d of %d',
                        num_tries, _MAX_SIMULATOR_INIT_TRIES)

    logging.error('Remote controller is unable to launch the simulator.')
    raise errors.RemoteControllerInitError()

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
        self._setup_step_interpreter.interpret(self._task.setup_steps)
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

    if self._simulator_start_time is not None:
      simulator_alive_time = (time.time() - self._simulator_start_time) / 60.0
      logging.info('Simulator has been running for %f minutes',
                   simulator_alive_time)
      if (self._periodic_restart_time_min > 0.0 and
          simulator_alive_time > self._periodic_restart_time_min):
        logging.info('Max alive time for simulator has been reached. '
                     'Triggering a restart.')
        # These restarts will not be counted in the 'restart_count' logging, as
        # this is part of the expected behavior.
        self._log_dict['restart_count_periodic'] += 1
        self.restart()

    logging.info('Resetting the remote controller...')

    # Execute a lift action before resetting
    self._execute_action({
        'action_type': np.array(action_type.ActionType.LIFT),
        'touch_position': np.array([0, 0])
    })

    # Reset counters
    self._latest_observation_local_time = None
    if not self._is_bad_episode:
      self._bad_state_counter = 0
    self._is_bad_episode = False

    # Pause dumpsys thread for the duration of the reset
    self._stop_dumpsys_thread()

    # Execute reset steps
    try:
      self._setup_step_interpreter.interpret(self._task.reset_steps)
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

  def execute_action(
      self,
      action: Optional[Dict[str, np.ndarray]],
  ) -> Tuple[Optional[Dict[str, np.ndarray]], float, Dict[str, Any]]:
    """Returns the observation (pixels) from the screen, rewards and extras."""

    self._execute_action(action)
    self._wait_for_next_frame()

    obs = None
    try:
      self._latest_observation_local_time = time.time()
      obs = self._simulator.get_observation()
    except (errors.ReadObservationError, socket.error):
      logging.exception('Unable to fetch observation. Restarting simulator.')
      self._log_dict['restart_count_fetch_observation'] += 1
      self._should_restart = True

    reward = self._get_current_reward()
    extras = self._logcat_thread.get_and_reset_extras()
    return (obs, reward, extras)

  def _execute_action(self, action: Optional[Dict[str, np.ndarray]]) -> None:
    """Applies the action from the agent."""

    if action is None:
      return

    if action['action_type'].item() == action_type.ActionType.REPEAT:
      return

    try:
      self._simulator.send_action(action)
    except (socket.error, errors.SendActionError):
      logging.exception('Unable to execute action. Restarting simulator.')
      self._log_dict['restart_count_execute_action'] += 1
      self._should_restart = True

  def _wait_for_next_frame(self) -> None:
    """Pauses the environment so that the interaction is around 1/FPS."""

    time_since_observation = self._get_time_since_last_observation()
    logging.debug('Time since obs: %0.6f', time_since_observation)

    time_to_wait = 1. / self._max_steps_per_sec - time_since_observation
    if time_to_wait > 0.0:
      time.sleep(time_to_wait)

  def _get_time_since_last_observation(self) -> float:
    if self._latest_observation_local_time is not None:
      return time.time() - self._latest_observation_local_time
    else:
      return np.inf

  def _get_current_reward(self) -> float:
    reward = self._logcat_thread.get_and_reset_reward()
    return 0.0 if reward is None else reward

  def check_timeout(self) -> bool:
    """Checks if timeout between steps have exceeded."""
    if self._step_timeout_sec:
      time_since_last_obs = self._get_time_since_last_observation()
      if time_since_last_obs > self._step_timeout_sec:
        return True
    return False

  def close(self):
    """Cleans up the state of this RemoteController."""
    logging.info('Cleaning up remote controller...')
    self._stop_logcat_thread()
    self._stop_dumpsys_thread()
    if hasattr(self, '_simulator'):
      self._simulator.close()
    logging.info('Done cleaning up remote controller.')

  def _start_logcat_thread(self):
    """Starts a logcat thread."""
    self._logcat_thread = logcat_thread.LogcatThread(
        adb_command_prefix=self._adb_controller.command_prefix(),
        log_parsing_config=self._task.log_parsing_config,
        print_all_lines=False,
        block_input=True,
        block_output=False)

  def _start_dumpsys_thread(self):
    """Starts a dumpsys thread."""
    self._dumpsys_thread = dumpsys_thread.DumpsysThread(
        app_screen_checker=app_screen_checker.AppScreenChecker(
            self._adb_controller, self._task.expected_app_screen),
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
