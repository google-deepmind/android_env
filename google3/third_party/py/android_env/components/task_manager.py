"""TaskManager handles all events and information related to the task."""

import copy
import datetime
import queue
import re
import threading
from typing import Any, Dict

from absl import logging
from android_env.components import adb_controller as adb_control
from android_env.components import app_screen_checker
from android_env.components import dumpsys_thread
from android_env.components import errors
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.proto import task_pb2


class TaskManager():
  """Handles all events and information related to the task."""

  def __init__(
      self,
      task: task_pb2.Task,
      max_bad_states: int = 3,
      dumpsys_check_frequency: int = 150,
      max_failed_current_activity: int = 10,
  ):
    """Controls task-relevant events and information.

    Args:
      task: A task proto defining the RL task.
      max_bad_states: How many bad states in a row are allowed before a restart
        of the simulator is triggered.
      dumpsys_check_frequency: Frequency, in steps, at which to check
        current_activity and view hierarchy
      max_failed_current_activity: The maximum number of tries for extracting
        the current activity before forcing the episode to restart.
    """
    self._task = task
    self._max_bad_states = max_bad_states
    self._dumpsys_check_frequency = dumpsys_check_frequency
    self._max_failed_current_activity = max_failed_current_activity
    self._lock = threading.Lock()

    self._adb_controller = None
    self._setup_step_interpreter = None

    # Logging settings
    self._log_dict = {
        'reset_count_step_timeout': 0,
        'reset_count_player_exited': 0,
        'reset_count_episode_end': 0,
        'reset_count_max_duration_reached': 0,
        'restart_count_max_bad_states': 0,
    }

    # Initialize internal state
    self._task_start_time = None
    self._episode_ended = False
    self._episode_steps = 0
    self._bad_state_counter = 0
    self._is_bad_episode = False

  def log_dict(self) -> Dict[str, Any]:
    log_dict = copy.deepcopy(self._log_dict)
    log_dict.update(self._setup_step_interpreter.log_dict())
    return log_dict

  def reset_counters(self):
    """Reset counters at the end of an RL episode."""

    if not self._is_bad_episode:
      self._bad_state_counter = 0
    self._is_bad_episode = False

    self._task_start_time = datetime.datetime.now()
    with self._lock:
      self._episode_ended = False
    self._episode_steps = 0
    self._logcat_thread.reset_counters()

  def setup_task(self, adb_controller: adb_control.AdbController) -> None:
    self._adb_controller = adb_controller
    self._start_logcat_thread()
    self._start_setup_step_interpreter()
    self._setup_step_interpreter.interpret(self._task.setup_steps)

  def reset_task(self) -> None:
    self._setup_step_interpreter.interpret(self._task.reset_steps)

  def pause_task(self) -> None:
    self._stop_dumpsys_thread()

  def resume_task(self) -> None:
    self._start_dumpsys_thread()

  def get_current_reward(self) -> float:
    reward = self._logcat_thread.get_and_reset_reward()
    return 0.0 if reward is None else reward

  def get_current_extras(self) -> Dict[str, Any]:
    extras = self._logcat_thread.get_and_reset_extras()
    return {} if extras is None else extras

  def check_if_episode_ended(self) -> bool:
    """Determines whether the episode should be terminated and reset."""

    # Check if player existed the task
    if self._check_player_exited():
      self._log_dict['reset_count_player_exited'] += 1
      logging.warning('Player exited the game. Ending episode.')
      logging.info('************* END OF EPISODE *************')
      return True

    # Check if episode has ended
    with self._lock:
      if self._episode_ended:
        self._log_dict['reset_count_episode_end'] += 1
        logging.info('End of episode from logcat! Ending episode.')
        logging.info('************* END OF EPISODE *************')
        return True

    # Check if step limit or time limit has been reached
    if self._task.max_num_steps > 0:
      # TODO(agergely) How should we count episode steps?
      # Should we put all the step counting here instead of AndroidEnv?
      if self._episode_steps > self._task.max_num_steps:
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

  def _check_player_exited(self) -> bool:
    """Returns whether the player has exited the game."""
    try:
      self._check_player_exited_impl()
      return False
    except errors.NotAllowedError:
      return True

  def _check_player_exited_impl(self):
    """Raises an error if the OS is not in an allowed state."""

    if not hasattr(self, '_dumpsys_thread'):
      return

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

  def close(self):
    """Cleans up the state of this TaskManager."""
    if hasattr(self, '_logcat_thread'):
      self._logcat_thread.kill()
    if hasattr(self, '_dumpsys_thread'):
      self._dumpsys_thread.kill()
    logging.info('Done cleaning up task_manager.')

  def _start_setup_step_interpreter(self):
    self._setup_step_interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self._adb_controller,
        logcat=self._logcat_thread)

  def _episode_end_handler(self, event, match):
    with self._lock:
      self._episode_ended = True

  def _start_logcat_thread(self):
    """Starts a logcat thread."""
    self._logcat_thread = logcat_thread.LogcatThread(
        adb_command_prefix=self._adb_controller.command_prefix(),
        log_parsing_config=self._task.log_parsing_config,
        print_all_lines=False,
        block_input=True,
        block_output=False)

    regexps = self._task.log_parsing_config.log_regexps

    # Defaults to 'a^' since that regex matches no string by definition.
    episode_end_event = re.compile(regexps.episode_end or 'a^')

    self._logcat_thread.add_event_listener(episode_end_event,
                                           self._episode_end_handler)

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
