# coding=utf-8
# Copyright 2026 DeepMind Technologies Limited.
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

"""Tests for android_env.components.task_manager.py."""

import json
import re
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import adb_call_parser as adb_call_parser_lib
from android_env.components import config_classes
from android_env.components import dumpsys_thread
from android_env.components import log_stream
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.components import task_manager
from android_env.proto import task_pb2
import numpy as np


class TaskManagerTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._setup_step_interpreter = mock.create_autospec(
        setup_step_interpreter.SetupStepInterpreter)
    self._dumpsys_thread = mock.create_autospec(dumpsys_thread.DumpsysThread)
    self._logcat_thread = mock.create_autospec(logcat_thread.LogcatThread)
    self._log_stream = mock.create_autospec(log_stream.LogStream)

    mock.patch.object(
        setup_step_interpreter,
        'SetupStepInterpreter',
        return_value=self._setup_step_interpreter).start()
    mock.patch.object(
        dumpsys_thread, 'DumpsysThread',
        return_value=self._dumpsys_thread).start()
    mock.patch.object(
        logcat_thread, 'LogcatThread',
        return_value=self._logcat_thread).start()
    mock.patch.object(
        log_stream, 'LogStream',
        return_value=self._log_stream).start()

  def _assert_match(self, event: re.Pattern[str], text: str) -> re.Match[str]:
    self.assertRegex(text, event)
    match = event.fullmatch(text)
    self.assertIsNotNone(match)
    return match

  def test_start(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    self.assertIsNotNone(task_mgr._logcat_thread)
    self.assertIsNotNone(task_mgr._dumpsys_thread)
    self.assertIsNotNone(task_mgr._setup_step_interpreter)

  def test_setup_task(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    self._setup_step_interpreter.interpret.assert_called_once()

  def test_step_count(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    task_mgr.rl_reset(observation={})
    self.assertEqual(task_mgr.stats()['episode_steps'], 0)
    task_mgr.rl_step(observation={})
    self.assertEqual(task_mgr.stats()['episode_steps'], 1)
    task_mgr.rl_step(observation={})
    self.assertEqual(task_mgr.stats()['episode_steps'], 2)
    task_mgr.rl_reset(observation={})
    self.assertEqual(task_mgr.stats()['episode_steps'], 0)

  def test_get_current_reward(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      match = event_listener.regexp.fullmatch('Reward: 123.0')
      if match is None:  # Ignore events that are not rewards.
        return

      event_listener.handler_fn(event_listener.regexp, match)

    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.reward.extend([
        '^[Rr]eward: ([-+]?[0-9]*\\.?[0-9]*)$'
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })
    self.assertEqual(timestep.reward, 123.0)
    np.testing.assert_equal(timestep.observation['pixels'], np.array([1, 2, 3]))

  def test_reward_event(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      match_1 = event_listener.regexp.match('foo_1')
      match_2 = event_listener.regexp.match('foo_2')
      match_3 = event_listener.regexp.fullmatch('Reward: 2.0')
      if match_1:
        event_listener.handler_fn(event_listener.regexp, match_1)
      if match_2:
        event_listener.handler_fn(event_listener.regexp, match_2)
      if match_3:
        event_listener.handler_fn(event_listener.regexp, match_3)

    task = task_pb2.Task()
    reward_event_1 = task_pb2.LogParsingConfig.LogRegexps.RewardEvent(
        event='foo_1', reward=5.0)
    reward_event_2 = task_pb2.LogParsingConfig.LogRegexps.RewardEvent(
        event='foo_2', reward=-1.0)
    task.log_parsing_config.log_regexps.reward_event.extend(
        [reward_event_1, reward_event_2])
    task.log_parsing_config.log_regexps.reward.extend(
        ['^[Rr]eward: ([-+]?[0-9]*\\.?[0-9]*)$'])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })
    self.assertEqual(timestep.reward, 6.0)

  def test_get_current_reward_via_score(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      event = event_listener.regexp
      match = event.fullmatch('score: 200.0')
      if match is None:  # Ignore events that are not scores.
        return

      event_listener.handler_fn(event, match)

      # Scores are accumulated by their differences, so a subsequent lower score
      # means that the final reward decreases.
      match2 = self._assert_match(event, 'score: 185')
      event_listener.handler_fn(event, match2)

    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.score = (
        '^score: ([-+]?[0-9]*\\.?[0-9]*)$')
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })
    self.assertEqual(timestep.reward, 185.0)

  def test_get_current_extras(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      event = event_listener.regexp
      match = event.fullmatch('extra: some_extra [1, 2]')
      if match is None:  # Ignore events that are not extras.
        return

      # Emit events.
      fn = event_listener.handler_fn
      fn(event, self._assert_match(event, 'extra: an_extra [1, 2, 3]'))
      fn(event, self._assert_match(event, 'extra: an_extra [4, 5, 6]'))
      fn(event, self._assert_match(event, 'extra: another_extra 0.5'))
      fn(
          event,
          self._assert_match(
              event, 'extra: multi_dimension_extra [[9,8,7],[6,5,4]]'
          ),
      )
      fn(event, self._assert_match(event, 'extra: boolean_extra'))

    # Setup the task and trigger the listener.
    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.extra.extend([
        '^extra: (?P<name>[^ ]*)[ ]?(?P<extra>.*)$'
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()

    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })

    # Check expectations.
    self.assertIn('extras', timestep.observation)
    extras = timestep.observation['extras']
    np.testing.assert_almost_equal([[1, 2, 3], [4, 5, 6]],
                                   extras.get('an_extra'))
    np.testing.assert_almost_equal([0.5], extras.get('another_extra'))
    np.testing.assert_almost_equal([[[9, 8, 7], [6, 5, 4]]],
                                   extras.get('multi_dimension_extra'))
    np.testing.assert_equal([1], extras.get('boolean_extra'))

  def test_get_current_extras_json_format(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      event = event_listener.regexp
      match = event.fullmatch('json_extra: {}')
      if match is None:  # Ignore events that are not extras.
        return

      # Emit events.
      extra = {
          'extra_scalar': 0,
          'extra_list': [1, 2, 3, 4],
          'extra_dict': {
              'foo': 'bar'
          },
          'extra_string': 'a_string'
      }
      extra_update = {'extra_string': 'a_new_string', 'extra_float': 0.6}
      fn = event_listener.handler_fn
      fn(event, self._assert_match(event, f'json_extra: {json.dumps(extra)}'))
      fn(
          event,
          self._assert_match(event, f'json_extra: {json.dumps(extra_update)}'),
      )

    # Setup the task and trigger the listener.
    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.json_extra.extend([
        '^json_extra: (?P<json_extra>.*)$'
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()

    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })

    # Check expectations.
    self.assertIn('extras', timestep.observation)
    extras = timestep.observation['extras']
    expected_extra = {
        'extra_scalar': [0],
        'extra_list': [[1, 2, 3, 4]],
        'extra_dict': [{
            'foo': 'bar'
        }],
        'extra_string': ['a_string', 'a_new_string'],
        'extra_float': [0.6]
    }
    with self.subTest(name='extra_scalar'):
      np.testing.assert_almost_equal(
          expected_extra['extra_scalar'], extras['extra_scalar']
      )
    with self.subTest(name='extra_list'):
      np.testing.assert_almost_equal(
          expected_extra['extra_list'], extras['extra_list']
      )
    with self.subTest(name='extra_string'):
      np.testing.assert_equal(
          expected_extra['extra_string'], extras['extra_string']
      )
    with self.subTest(name='extra_float'):
      np.testing.assert_almost_equal(
          expected_extra['extra_float'], extras['extra_float']
      )
    with self.subTest(name='extra_dict'):
      np.testing.assert_equal(
          expected_extra['extra_dict'], extras['extra_dict']
      )

  def test_get_current_extras_failed_to_parse(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      event = event_listener.regexp
      match = event.fullmatch('extra: some_extra [1, 2]')
      if match is None:  # Ignore events that are not extras.
        return

      # Emit events.
      fn = event_listener.handler_fn
      fn(event, self._assert_match(event, 'extra: extra_with_malformed_1 [1]'))
      fn(
          event,
          self._assert_match(
              event, "extra: extra_with_malformed_1 ['this is \\ bad]"
          ),
      )
      fn(event, self._assert_match(event, 'extra: extra_with_malformed_1 [2]'))
      fn(
          event,
          self._assert_match(
              event, "extra: extra_with_malformed_2 ['this is bad]"
          ),
      )
      fn(event, self._assert_match(event, 'extra: extra_with_malformed_2 [1]'))
      fn(
          event,
          self._assert_match(
              event, 'extra: extra_malformed_only [_very_bad_news]'
          ),
      )

    # Setup the task and trigger the listener.
    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.extra.extend([
        '^extra: (?P<name>[^ ]*)[ ]?(?P<extra>.*)$'
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()

    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })

    # Check expectations.
    self.assertIn('extras', timestep.observation)
    extras = timestep.observation['extras']
    np.testing.assert_almost_equal(extras.get('extra_with_malformed_1'),
                                   [[1], [2]])
    np.testing.assert_almost_equal(extras.get('extra_with_malformed_2'), [[1]])
    self.assertNotIn('extra_malformed_only', extras)

  def test_multi_log_regexp(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      match = event_listener.regexp.fullmatch('Reward_2: 123.0')
      if match is None:  # Ignore events that are not rewards.
        return

      event_listener.handler_fn(event_listener.regexp, match)

    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.reward.extend([
        '^[Rr]eward_1: ([-+]?[0-9]*\\.?[0-9]*)$',
        '^[Rr]eward_2: ([-+]?[0-9]*\\.?[0-9]*)$'
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })
    self.assertEqual(timestep.reward, 123.0)

  def test_multi_reward_regexp(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.'

    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      match_1 = event_listener.regexp.fullmatch('Reward_1: 5.0')
      match_2 = event_listener.regexp.fullmatch('Reward_2: 10.0')

      if match_1:
        event_listener.handler_fn(event_listener.regexp, match_1)

      if match_2:
        event_listener.handler_fn(event_listener.regexp, match_2)

    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.reward.extend([
        '^[Rr]eward_1: ([-+]?[0-9]*\\.?[0-9]*)$',
        '^[Rr]eward_2: ([-+]?[0-9]*\\.?[0-9]*)$',
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })
    self.assertEqual(timestep.reward, 15.0)

  def test_determine_transition_fn(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      event = event_listener.regexp
      match = event.match('I am done!')
      if match is None:  # Ignore events that are not episode end.
        return

      event_listener.handler_fn(event, match)

    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.episode_end.extend(['I am done!'])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()
    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })
    self.assertTrue(timestep.last())

  def test_setup_task_before_start_raises_assertion(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    with self.assertRaisesRegex(
        AssertionError, 'setup_step_interpreter is None'
    ):
      task_mgr.setup_task()

  def test_reset_task_before_start_raises_assertion(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    with self.assertRaisesRegex(AssertionError, 'LogcatThread is None'):
      task_mgr.reset_task()

  @parameterized.named_parameters(
      dict(testcase_name='rl_reset', method_name='rl_reset'),
      dict(testcase_name='rl_step', method_name='rl_step'),
  )
  def test_rl_methods_before_start_raise_assertion(self, method_name):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    method = getattr(task_mgr, method_name)
    with self.assertRaisesRegex(AssertionError, 'LogcatThread is None'):
      method(observation={})

  def test_rl_step_raises_if_dumpsys_missing(self):
    # Setup a task manager with mocked logcat but no dumpsys.
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    task_mgr._logcat_thread = self._logcat_thread

    # rl_step calls _determine_transition_fn, triggering dumpsys assertion.
    with self.assertRaisesRegex(AssertionError, 'DumpsysThread is None'):
      task_mgr.rl_step(observation={})

  def test_rl_step_raises_if_start_time_missing(self):
    # Now mock dumpsys too, but no task_start_time, and set max_episode_sec.
    task = task_pb2.Task(max_episode_sec=10.0)
    task_mgr = task_manager.TaskManager(task=task)
    task_mgr._logcat_thread = self._logcat_thread
    task_mgr._dumpsys_thread = self._dumpsys_thread
    self._dumpsys_thread.check_user_exited.return_value = False

    # rl_step will check max_episode_sec, triggering start time assertion.
    with self.assertRaisesRegex(AssertionError, 'Task start time is None'):
      task_mgr.rl_step(observation={})

  def test_extras_buffer_overflow(self):
    # Setup TaskManagerConfig with a small buffer size of 2.
    config = config_classes.TaskManagerConfig(extras_max_buffer_size=2)

    # Replace `LogcatThread.add_event_listener` with one that pushes 3 values.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      event = event_listener.regexp
      match = event.fullmatch('extra: some_extra [1, 2]')
      if match is None:
        return
      fn = event_listener.handler_fn
      fn(event, self._assert_match(event, 'extra: overflow_extra 1'))
      fn(event, self._assert_match(event, 'extra: overflow_extra 2'))
      fn(event, self._assert_match(event, 'extra: overflow_extra 3'))

    task = task_pb2.Task(
        log_parsing_config=task_pb2.LogParsingConfig(
            log_regexps=task_pb2.LogParsingConfig.LogRegexps(
                extra=['^extra: (?P<name>[^ ]*)[ ]?(?P<extra>.*)$']
            )
        )
    )
    task_mgr = task_manager.TaskManager(task=task, config=config)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.start(lambda: adb_call_parser, log_stream=self._log_stream)
    task_mgr.setup_task()

    timestep = task_mgr.rl_step(observation={'pixels': np.array([1, 2, 3])})

    # Verify buffer overflow popped the first value (1) and kept only (2, 3).
    self.assertIn('extras', timestep.observation)
    extras = timestep.observation['extras']
    np.testing.assert_almost_equal([2, 3], extras['overflow_extra'])


if __name__ == '__main__':
  absltest.main()
