"""Coordinator handles the communication with AndroidOS."""

import copy
import socket
import time
from typing import Any, Dict, Optional

from absl import logging
from android_env.components import action_type
from android_env.components import base_simulator
from android_env.components import errors
from android_env.components import task_manager as task_manager_lib
import numpy as np


_MAX_RESTART_TRIES = 3


class Coordinator():
  """Handles interaction between internal components of AndroidEnv."""

  def __init__(
      self,
      simulator: base_simulator.BaseSimulator,
      task_manager: task_manager_lib.TaskManager,
      step_timeout_sec: int = 10,
      max_steps_per_sec: float = 5.0,
      periodic_restart_time_min: float = 0.0,
      force_simulator_launch: bool = True,
  ):
    """Handles communication between AndroidEnv and AndroidOS.

    Args:
      simulator: A BaseSimulator Instance.
      task_manager: TaskManager.
      step_timeout_sec: Timeout in seconds between steps. If step is not called
        within that time, the episode will reset at the next step. Set to 0 to
        disable.
      max_steps_per_sec: Maximum steps per second. If the simulator is
        faster, the Coordinator will wait before returning an observation.
      periodic_restart_time_min: Time between periodic restarts in minutes. If >
        0.0, will trigger a simulator restart at the end of the next episode
        once the time has been reached.
      force_simulator_launch: Forces the simulator to relaunch even if it is
        already launched.
    """
    self._simulator = simulator
    self._task_manager = task_manager
    self._step_timeout_sec = step_timeout_sec
    self._max_steps_per_sec = max_steps_per_sec
    self._periodic_restart_time_min = periodic_restart_time_min
    self._force_simulator_launch = force_simulator_launch

    # Logging settings.
    self._log_dict = {
        'restart_count_fetch_observation': 0,
        'restart_count_simulator_setup': 0,
        'restart_count_simulator_reset': 0,
        'restart_count_simulator_restart': 0,
        'restart_count_restart_setup_steps': 0,
        'restart_count_execute_action': 0,
        'restart_count_periodic': 0,
    }

    # Initialize counters.
    self._should_restart = False
    self._bad_state_counter = 0
    self._latest_observation_local_time = None
    self._simulator_start_time = None

    self.restart_simulator()

  @property
  def should_restart(self) -> bool:
    return self._should_restart

  def log_dict(self) -> Dict[str, Any]:
    log_dict = copy.deepcopy(self._log_dict)
    log_dict.update(self._task_manager.log_dict())
    return log_dict

  def restart_simulator(self):
    """Restarts the simulation."""

    # Reset counters
    self._should_restart = False
    self._bad_state_counter = 0  # TODO(agergely) Do we need this?

    # Pause task for the duration of the restart
    self._task_manager.pause_task()

    num_tries = 1
    while True:
      if num_tries > _MAX_RESTART_TRIES:
        logging.error('Maximum number of restarts reached.')
        raise errors.TooManyRestartsError
      logging.info('Launch attempt %d of %d', num_tries, _MAX_RESTART_TRIES)

      # Launch the simulator (will restart if already launched)
      try:
        if self._force_simulator_launch or not self._simulator.is_launched():
          self._simulator.launch()
          self._simulator_start_time = time.time()
        adb_controller = self._simulator.create_adb_controller()
      except errors.AdbControllerError:
        logging.error('Error launching the simulator.')
        self._log_dict['restart_count_simulator_restart'] += 1
        num_tries += 1
        continue

      # Start task
      try:
        self._task_manager.setup_task(adb_controller=adb_controller)
      except errors.StepCommandError:
        logging.error('Failed to execute setup steps. Restarting simulator.')
        self._log_dict['restart_count_restart_setup_steps'] += 1
        num_tries += 1
        continue

      # Restart was successful
      break

  def reset(self):
    """Resets the episode."""

    self._maybe_periodic_restart()

    # Execute a lift action before resetting
    self._execute_action({
        'action_type': np.array(action_type.ActionType.LIFT),
        'touch_position': np.array([0, 0])
    })

    # Reset counters
    self._latest_observation_local_time = None

    # Pause task for the duration of the reset
    self._task_manager.pause_task()

    # Execute reset steps
    try:
      self._task_manager.reset_task()
    except errors.StepCommandError:
      logging.exception('Failed to execute reset steps. Restarting simulator.')
      self._log_dict['restart_count_simulator_reset'] += 1
      self._should_restart = True
      return

    self._simulator.update_device_orientation()
    self._task_manager.reset_counters()

    # Resume task
    self._task_manager.resume_task()

  def _maybe_periodic_restart(self):
    """Checks if it is time to restart the simulator."""

    if self._simulator_start_time is None:
      return

    simulator_alive_time = (time.time() - self._simulator_start_time) / 60.0
    logging.info('Simulator has been running for %f mins', simulator_alive_time)
    if (self._periodic_restart_time_min > 0.0 and
        simulator_alive_time > self._periodic_restart_time_min):
      logging.info('Max alive time for simulator has been reached.'
                   'Triggering a restart.')
      # These restarts will not be counted in the 'restart_count' logging, as
      # this is part of the expected behavior.
      self._log_dict['restart_count_periodic'] += 1
      self.restart_simulator()

  def execute_action(
      self,
      action: Optional[Dict[str, np.ndarray]],
  ) -> Optional[Dict[str, np.ndarray]]:
    """Returns the observation (pixels) from the screen, rewards and extras."""

    if (action is not None and
        action['action_type'].item() != action_type.ActionType.REPEAT):
      self._execute_action(action)

    self._wait_for_next_frame()

    try:
      self._latest_observation_local_time = time.time()
      observation = self._simulator.get_observation()
      return observation
    except (errors.ReadObservationError, socket.error):
      logging.exception('Unable to fetch observation. Restarting simulator.')
      self._log_dict['restart_count_fetch_observation'] += 1
      self._should_restart = True

  def _execute_action(self, action: Dict[str, np.ndarray]) -> None:
    """Sends the selected action to the simulator."""

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

  def check_timeout(self) -> bool:
    """Checks if timeout between steps have exceeded."""
    if self._step_timeout_sec:
      time_since_last_obs = self._get_time_since_last_observation()
      if time_since_last_obs > self._step_timeout_sec:
        return True
    return False

  def close(self):
    """Cleans up the state of this Coordinator."""
    logging.info('Cleaning up coordinator...')
    if hasattr(self, '_task_manager'):
      self._task_manager.close()
    if hasattr(self, '_simulator'):
      self._simulator.close()
    logging.info('Done cleaning up coordinator.')
