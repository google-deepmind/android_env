# coding=utf-8
# Copyright 2024 DeepMind Technologies Limited.
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
from collections.abc import Callable
import copy
import datetime
import json
import re
import threading
from typing import Any

from absl import logging
from android_env.components import adb_call_parser as adb_call_parser_lib
from android_env.components import app_screen_checker
from android_env.components import config_classes
from android_env.components import dumpsys_thread
from android_env.components import log_stream as log_stream_lib
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.proto import task_pb2
import dm_env
import numpy as np


class TaskManager:
  """Handles all events and information related to the task."""

  def __init__(
      self,
      task: task_pb2.Task,
      config: config_classes.TaskManagerConfig | None = None,
  ):
    """Controls task-relevant events and information.

    Args:
      task: A task proto defining the RL task.
      config: Configuration for this instance.
    """

    self._task = task
    self._config = config or config_classes.TaskManagerConfig()
    self._lock = threading.Lock()
    self._logcat_thread = None
    self._dumpsys_thread = None
    self._setup_step_interpreter = None

    # Initialize stats.
    self._stats = {
        'episode_steps': 0,
        'reset_count_step_timeout': 0,
        'reset_count_user_exited': 0,
        'reset_count_episode_end': 0,
        'reset_count_max_duration_reached': 0,
        'restart_count_max_bad_states': 0,
        'task_updates': 0,
    }

    # Initialize internal state
    self._task_start_time = None
    self._bad_state_counter = 0
    self._is_bad_episode = False

    self._latest_values = {
        'reward': 0.0,
        'score': 0.0,
        'extra': {},
        'episode_end': False,
    }

    logging.info('Task config: %s', self._task)

  def stats(self) -> dict[str, Any]:
    """Returns a dictionary of stats.

    This method is expected to be called after setup_task() has been called.
    """
    output = copy.deepcopy(self._stats)
    if self._setup_step_interpreter is not None:
      output.update(self._setup_step_interpreter.stats())
    return output

  def setup_task(self) -> None:
    """Performs one-off task setup.."""
    self._setup_step_interpreter.interpret(self._task.setup_steps)

  def stop(self) -> None:
    """Suspends task processing."""
    self._stop_logcat_thread()

  def start(
      self,
      adb_call_parser_factory: Callable[[], adb_call_parser_lib.AdbCallParser],
      log_stream: log_stream_lib.LogStream) -> None:
    """Starts task processing."""

    self._start_logcat_thread(log_stream=log_stream)
    self._logcat_thread.resume()
    self._start_dumpsys_thread(adb_call_parser_factory())
    self._start_setup_step_interpreter(adb_call_parser_factory())

  def reset_task(self) -> None:
    """Resets a task for a new run."""

    self._logcat_thread.pause()
    self._setup_step_interpreter.interpret(self._task.reset_steps)
    self._logcat_thread.resume()

    # Reset some other variables.
    if not self._is_bad_episode:
      self._bad_state_counter = 0
    self._is_bad_episode = False

    self._task_start_time = datetime.datetime.now()
    with self._lock:
      self._latest_values = {
          'reward': 0.0,
          'score': 0.0,
          'extra': {},
          'episode_end': False,
      }

  def rl_reset(self, observation: dict[str, Any]) -> dm_env.TimeStep:
    """Performs one RL step."""

    self._stats['episode_steps'] = 0

    self._logcat_thread.line_ready().wait()
    with self._lock:
      extras = self._get_current_extras()

    observation['extras'] = extras

    return dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=0.0,
        discount=0.0,
        observation=observation)

  def rl_step(self, observation: dict[str, Any]) -> dm_env.TimeStep:
    """Performs one RL step."""

    self._stats['episode_steps'] += 1

    self._logcat_thread.line_ready().wait()
    with self._lock:
      reward = self._get_current_reward()
      extras = self._get_current_extras()
      transition_fn = self._determine_transition_fn()

    observation['extras'] = extras

    return transition_fn(reward=reward, observation=observation)

  def _get_current_reward(self) -> float:
    """Returns total reward accumulated since the last step."""
    reward = self._latest_values['reward']
    self._latest_values['reward'] = 0.0
    return reward

  def _get_current_extras(self) -> dict[str, Any]:
    """Returns task extras accumulated since the last step."""
    extras = {}
    for name, values in self._latest_values['extra'].items():
      extras[name] = np.stack(values)
    self._latest_values['extra'] = {}
    return extras

  def _determine_transition_fn(self) -> Callable[..., dm_env.TimeStep]:
    """Determines the type of RL transition will be used."""

    # Check if user existed the task
    if self._dumpsys_thread.check_user_exited():
      self._increment_bad_state()
      self._stats['reset_count_user_exited'] += 1
      logging.warning('User exited the task. Truncating the episode.')
      logging.info('************* END OF EPISODE *************')
      return dm_env.truncation

    # Check if episode has ended
    if self._latest_values['episode_end']:
      self._stats['reset_count_episode_end'] += 1
      logging.info('End of episode from logcat! Ending episode.')
      return dm_env.termination

    # Check if step limit or time limit has been reached
    if self._task.max_episode_steps > 0:
      if self._stats['episode_steps'] > self._task.max_episode_steps:
        self._stats['reset_count_max_duration_reached'] += 1
        logging.info('Maximum task duration (%r steps) reached. '
                     'Truncating the episode.', self._task.max_episode_steps)
        return dm_env.truncation

    if self._task.max_episode_sec > 0.0:
      task_duration = datetime.datetime.now() - self._task_start_time
      max_episode_sec = self._task.max_episode_sec
      if task_duration > datetime.timedelta(seconds=int(max_episode_sec)):
        self._stats['reset_count_max_duration_reached'] += 1
        logging.info('Maximum task duration (%r sec) reached. '
                     'Truncating the episode.', max_episode_sec)
        return dm_env.truncation

    return dm_env.transition

  def _start_setup_step_interpreter(
      self, adb_call_parser: adb_call_parser_lib.AdbCallParser):
    self._setup_step_interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=adb_call_parser)

  def _start_logcat_thread(self, log_stream: log_stream_lib.LogStream):
    log_stream.set_log_filters(list(self._task.log_parsing_config.filters))
    self._logcat_thread = logcat_thread.LogcatThread(log_stream=log_stream)

    for event_listener in self._logcat_listeners():
      self._logcat_thread.add_event_listener(event_listener)

  def _start_dumpsys_thread(self,
                            adb_call_parser: adb_call_parser_lib.AdbCallParser):
    self._dumpsys_thread = dumpsys_thread.DumpsysThread(
        app_screen_checker=app_screen_checker.AppScreenChecker(
            adb_call_parser=adb_call_parser,
            expected_app_screen=self._task.expected_app_screen,
        ),
        check_frequency=self._config.dumpsys_check_frequency,
        max_failed_current_activity=self._config.max_failed_current_activity,
    )

  def _stop_logcat_thread(self):
    if self._logcat_thread is not None:
      self._logcat_thread.kill()
      self._logcat_thread = None

  def _increment_bad_state(self) -> None:
    """Increments the bad state counter.

    Bad states are errors that shouldn't happen and that trigger an
    episode reset. If enough bad states have been seen consecutively,
    we restart the simulation in the hope of returning the simulation
    to a good state.
    """
    logging.warning('Bad state detected.')
    if self._config.max_bad_states:
      self._is_bad_episode = True
      self._bad_state_counter += 1
      logging.warning('Bad state counter: %d.', self._bad_state_counter)
      if self._bad_state_counter >= self._config.max_bad_states:
        logging.error('Too many consecutive bad states. Restarting simulator.')
        self._stats['restart_count_max_bad_states'] += 1
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
        except (
            ValueError,
            TypeError,
            SyntaxError,
            MemoryError,
            RecursionError,
        ):
          logging.exception('Could not parse extra: %s', extra)
          # Don't try to process the extra as text; that would probably crash.
          return
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
          if (
              len(latest_extras[extra_name])
              >= self._config.extras_max_buffer_size
          ):
            latest_extras[extra_name].pop(0)
          latest_extras[extra_name].append(extra)
        else:
          latest_extras[extra_name] = [extra]
        self._latest_values['extra'] = latest_extras

    return listeners
