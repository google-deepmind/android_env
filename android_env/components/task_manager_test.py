# coding=utf-8
# Copyright 2022 DeepMind Technologies Limited.
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
from unittest import mock

from absl.testing import absltest
from android_env.components import adb_call_parser as adb_call_parser_lib
from android_env.components import dumpsys_thread
from android_env.components import log_stream
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.components import task_manager
from android_env.proto import task_pb2
import numpy as np


class TaskManagerTest(absltest.TestCase):

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

  def test_update_task(self):
    init_task = task_pb2.Task(id='initial_task')
    new_task = task_pb2.Task(id='updated_task')
    task_mgr = task_manager.TaskManager(task=init_task)

    # Setting up the initial task so that the setup_step_interpreter
    # is properly initialized.
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)

    self.assertEqual(init_task, task_mgr.task())
    self.assertEqual(0, task_mgr.stats()['task_updates'])
    task_mgr.update_task(new_task)
    self.assertEqual(new_task, task_mgr.task())
    self.assertEqual(1, task_mgr.stats()['task_updates'])

  def test_setup_task(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
    self.assertIsNotNone(task_mgr._logcat_thread)
    self.assertIsNotNone(task_mgr._setup_step_interpreter)

  def test_step_count(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
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
      match = event_listener.regexp.match('Reward: 123.0')
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
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
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
      match_3 = event_listener.regexp.match('Reward: 2.0')
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
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
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
      match = event.match('score: 200.0')
      if match is None:  # Ignore events that are not scores.
        return

      event_listener.handler_fn(event, match)

      # Scores are accumulated by their differences, so a subsequent lower score
      # means that the final reward decreases.
      match = event.match('score: 185')
      event_listener.handler_fn(event, match)

    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.score = (
        '^score: ([-+]?[0-9]*\\.?[0-9]*)$')
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
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
      match = event.match('extra: some_extra [1, 2]')
      if match is None:  # Ignore events that are not extras.
        return

      # Emit events.
      fn = event_listener.handler_fn
      fn(event, event.match('extra: an_extra [1, 2, 3]'))
      fn(event, event.match('extra: an_extra [4, 5, 6]'))
      fn(event, event.match('extra: another_extra 0.5'))
      fn(event, event.match('extra: multi_dimension_extra [[9,8,7],[6,5,4]]'))
      fn(event, event.match('extra: boolean_extra'))

    # Setup the task and trigger the listener.
    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.extra.extend([
        '^extra: (?P<name>[^ ]*)[ ]?(?P<extra>.*)$'
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)

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
      match = event.match('json_extra: {}')
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
      fn(event, event.match(f'json_extra: {json.dumps(extra)}'))
      fn(event, event.match(f'json_extra: {json.dumps(extra_update)}'))

    # Setup the task and trigger the listener.
    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.json_extra.extend([
        '^json_extra: (?P<json_extra>.*)$'
    ])
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)

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
    np.testing.assert_almost_equal(
        expected_extra.get('extra_scalar'), extras.get('extra_scalar'))
    np.testing.assert_almost_equal(
        expected_extra.get('extra_list'), extras.get('extra_list'))
    np.testing.assert_equal(
        expected_extra.get('extra_string'), extras.get('extra_string'))
    np.testing.assert_almost_equal(
        expected_extra.get('extra_float'), extras.get('extra_float'))
    np.testing.assert_equal(
        expected_extra.get('extra_dict'), extras.get('extra_dict'))

  def test_multi_log_regexp(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event_listener: logcat_thread.EventListener):
      # Check that the event matches what's expected.
      match = event_listener.regexp.match('Reward_2: 123.0')
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
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
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
      match_1 = event_listener.regexp.match('Reward_1: 5.0')
      match_2 = event_listener.regexp.match('Reward_2: 10.0')

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
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
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
    task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
    timestep = task_mgr.rl_step(
        observation={
            'pixels': np.array([1, 2, 3]),
        })
    self.assertTrue(timestep.last())


def test_setup_steps_skipped_if_no_change(self):
  setup_steps = [task_pb2.SetupStep(sleep=task_pb2.Sleep(time_sec=10))]
  task_mgr = task_manager.TaskManager(
      task=task_pb2.Task(id='first_task', setup_steps=setup_steps))
  adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
  task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
  self.assertIsNotNone(task_mgr._logcat_thread)
  self.assertIsNotNone(task_mgr._setup_step_interpreter)
  self._setup_step_interpreter.interpret.assert_called_once_with(setup_steps)
  task_mgr.update_task(
      task=task_pb2.Task(id='second_task', setup_steps=setup_steps))
  # The interpreter should not be called again.
  task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
  self._setup_step_interpreter.interpret.assert_called_once()


def test_setup_steps_interpreted_if_changed(self):
  setup_steps = [task_pb2.SetupStep(sleep=task_pb2.Sleep(time_sec=10))]
  task_mgr = task_manager.TaskManager(
      task=task_pb2.Task(id='first_task', setup_steps=setup_steps))
  adb_call_parser = mock.create_autospec(adb_call_parser_lib.AdbCallParser)
  task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
  self.assertIsNotNone(task_mgr._logcat_thread)
  self.assertIsNotNone(task_mgr._setup_step_interpreter)
  self._setup_step_interpreter.interpret.assert_called_once_with(setup_steps)
  new_setup_steps = [task_pb2.SetupStep(sleep=task_pb2.Sleep(time_sec=5))]
  task_mgr.update_task(
      task=task_pb2.Task(id='second_task', setup_steps=new_setup_steps))
  task_mgr.setup_task(lambda: adb_call_parser, log_stream=self._log_stream)
  self.assertEqual(2, self._setup_step_interpreter.interpret.num_calls())
  self._setup_step_interpreter.interpret.assert_has_calls(
      mock.call(setup_steps), mock.call(new_setup_steps))

if __name__ == '__main__':
  absltest.main()
