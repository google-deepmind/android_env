# coding=utf-8
# Copyright 2021 DeepMind Technologies Limited.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""TaskManager handles all events and information related to the task."""

import ast
import copy
import datetime
import json
import queue
import re
import threading
from typing import Any, Dict

from absl import logging
from android_env.components import adb_controller as adb_control
from android_env.components import app_screen_checker
from android_env.components import dumpsys_thread
from android_env.components import errors
from android_env.components import log_stream as log_stream_lib
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.proto import task_pb2
import numpy as np


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
    self._extras_max_buffer_size = 100
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
    self._episode_steps = 0
    self._bad_state_counter = 0
    self._is_bad_episode = False

    self._latest_values = {
        'reward': 0.0,
        'score': 0.0,
        'extra': {},
        'episode_end': False,
    }

    logging.info('Task config: %s', self._task)

  def task(self) -> task_pb2.Task:
    return self._task

  def increment_steps(self):
    self._episode_steps += 1

  def log_dict(self) -> Dict[str, Any]:
    log_dict = copy.deepcopy(self._log_dict)
    log_dict.update(self._setup_step_interpreter.log_dict())
    return log_dict

  def _reset_counters(self):
    """Reset counters at the end of an RL episode."""

    if not self._is_bad_episode:
      self._bad_state_counter = 0
    self._is_bad_episode = False

    self._episode_steps = 0
    self._task_start_time = datetime.datetime.now()
    with self._lock:
      self._latest_values = {
          'reward': 0.0,
          'score': 0.0,
          'extra': {},
          'episode_end': False,
      }

  def setup_task(self,
                 adb_controller: adb_control.AdbController,
                 log_stream: log_stream_lib.LogStream) -> None:
    """Starts the given task along with all relevant processes."""

    self._adb_controller = adb_controller
    self._start_logcat_thread(log_stream=log_stream)
    self._start_setup_step_interpreter()
    self._setup_step_interpreter.interpret(self._task.setup_steps)

  def reset_task(self) -> None:
    """Resets a task at the end of an RL episode."""

    self.pause_task()
    self._setup_step_interpreter.interpret(self._task.reset_steps)
    self._resume_task()
    self._reset_counters()

  def pause_task(self) -> None:
    self._stop_dumpsys_thread()

  def _resume_task(self) -> None:
    self._start_dumpsys_thread()

  def get_current_reward(self) -> float:
    """Returns total reward accumulated since the last step."""

    with self._lock:
      reward = self._latest_values['reward']
      self._latest_values['reward'] = 0.0
    return reward

  def get_current_extras(self) -> Dict[str, Any]:
    """Returns task extras accumulated since the last step."""

    with self._lock:
      extras = {}
      for name, values in self._latest_values['extra'].items():
        extras[name] = np.stack(values)
      self._latest_values['extra'] = {}
      return extras

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
      if self._latest_values['episode_end']:
        self._log_dict['reset_count_episode_end'] += 1
        logging.info('End of episode from logcat! Ending episode.')
        logging.info('************* END OF EPISODE *************')
        return True

    # Check if step limit or time limit has been reached
    if self._task.max_num_steps > 0:
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

  def _start_setup_step_interpreter(self):
    self._setup_step_interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self._adb_controller,
        logcat=self._logcat_thread)

  def _start_logcat_thread(self, log_stream: log_stream_lib.LogStream):
    self._logcat_thread = logcat_thread.LogcatThread(
        log_stream=log_stream,
        log_parsing_config=self._task.log_parsing_config)

    for event_listener in self._logcat_listeners():
      self._logcat_thread.add_event_listener(event_listener)

  def _start_dumpsys_thread(self):
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

  def _logcat_listeners(self):
    """Creates list of EventListeners for logcat thread."""

    # Defaults to 'a^' since that regex matches no string by definition.
    regexps = self._task.log_parsing_config.log_regexps
    listeners = []

    # Reward listeners
    def _reward_handler(event, match):
      del event
      reward = float(match.group(1))
      with self._lock:
        self._latest_values['reward'] += reward

    for regexp in regexps.reward:
      listeners.append(logcat_thread.EventListener(
          regexp=re.compile(regexp or 'a^'),
          handler_fn=_reward_handler))

    # RewardEvent listeners
    for reward_event in regexps.reward_event:

      def get_reward_event_handler(reward):
        def _reward_event_handler(event, match):
          del event, match
          with self._lock:
            self._latest_values['reward'] += reward
        return _reward_event_handler

      listeners.append(logcat_thread.EventListener(
          regexp=re.compile(reward_event.event or 'a^'),
          handler_fn=get_reward_event_handler(reward_event.reward)))

    # Score listener
    def _score_handler(event, match):
      del event
      current_score = float(match.group(1))
      with self._lock:
        current_reward = current_score - self._latest_values['score']
        self._latest_values['score'] = current_score
        self._latest_values['reward'] += current_reward

    listeners.append(logcat_thread.EventListener(
        regexp=re.compile(regexps.score or 'a^'),
        handler_fn=_score_handler))

    # Episode end listeners
    def _episode_end_handler(event, match):
      del event, match
      with self._lock:
        self._latest_values['episode_end'] = True

    for regexp in regexps.episode_end:
      listeners.append(logcat_thread.EventListener(
          regexp=re.compile(regexp or 'a^'),
          handler_fn=_episode_end_handler))

    # Extra listeners
    def _extras_handler(event, match):
      del event
      extra_name = match.group('name')
      extra = match.group('extra')
      if extra:
        try:
          extra = ast.literal_eval(extra)
        # Except all to avoid unnecessary crashes, only log error.
        except Exception:  # pylint: disable=broad-except
          logging.exception('Could not parse extra: %s', extra)
      else:
        # No extra value provided for boolean extra. Setting value to True.
        extra = 1
      _process_extra(extra_name, extra)

    for regexp in regexps.extra:
      listeners.append(logcat_thread.EventListener(
          regexp=re.compile(regexp or 'a^'),
          handler_fn=_extras_handler))

    # JSON extra listeners
    def _json_extras_handler(event, match):
      del event
      extra_data = match.group('json_extra')
      try:
        extra = dict(json.loads(extra_data))
      except ValueError:
        logging.error('JSON string could not be parsed: %s', extra_data)
        return
      for extra_name, extra_value in extra.items():
        _process_extra(extra_name, extra_value)

    for regexp in regexps.json_extra:
      listeners.append(logcat_thread.EventListener(
          regexp=re.compile(regexp or 'a^'),
          handler_fn=_json_extras_handler))

    def _process_extra(extra_name, extra):
      extra = np.array(extra)
      with self._lock:
        latest_extras = self._latest_values['extra']
        if extra_name in latest_extras:
          # If latest extra is not flushed, append.
          if len(latest_extras[extra_name]) >= self._extras_max_buffer_size:
            latest_extras[extra_name].pop(0)
          latest_extras[extra_name].append(extra)
        else:
          latest_extras[extra_name] = [extra]
        self._latest_values['extra'] = latest_extras

    return listeners

  def close(self):
    if hasattr(self, '_logcat_thread'):
      self._logcat_thread.kill()
    if hasattr(self, '_dumpsys_thread'):
      self._dumpsys_thread.kill()
