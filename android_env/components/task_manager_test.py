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

"""Tests for task_manager.py."""

import json

from absl.testing import absltest
from android_env.components import adb_controller
from android_env.components import dumpsys_thread
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.components import task_manager
from android_env.proto import task_pb2
import mock
import numpy as np


class TaskManagerTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._adb_controller = mock.create_autospec(adb_controller.AdbController)
    self._setup_step_interpreter = mock.create_autospec(
        setup_step_interpreter.SetupStepInterpreter)
    self._dumpsys_thread = mock.create_autospec(dumpsys_thread.DumpsysThread)
    self._logcat_thread = mock.create_autospec(logcat_thread.LogcatThread)

    mock.patch.object(
        adb_controller, 'AdbController',
        return_value=self._adb_controller).start()
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

  def test_setup_task(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    task_mgr.setup_task(adb_controller=self._adb_controller)
    assert hasattr(task_mgr, '_logcat_thread')
    assert hasattr(task_mgr, '_setup_step_interpreter')

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
    task.log_parsing_config.log_regexps.reward = (
        '^[Rr]eward: ([-+]?[0-9]*\\.?[0-9]*)$')
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    task_mgr.setup_task(adb_controller=self._adb_controller)
    self.assertEqual(task_mgr.get_current_reward(), 123.0)

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
    task_mgr.setup_task(adb_controller=self._adb_controller)
    self.assertEqual(task_mgr.get_current_reward(), 185.0)

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
    task.log_parsing_config.log_regexps.extra = (
        '^extra: (?P<name>[^ ]*)[ ]?(?P<extra>.*)$')
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    task_mgr.setup_task(adb_controller=self._adb_controller)

    # Check expectations.
    extras = task_mgr.get_current_extras()
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
    task.log_parsing_config.log_regexps.json_extra = (
        '^json_extra: (?P<json_extra>.*)$')
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    task_mgr.setup_task(adb_controller=self._adb_controller)

    # Check expectations.
    expected_extra = {
        'extra_scalar': [0],
        'extra_list': [[1, 2, 3, 4]],
        'extra_dict': [{
            'foo': 'bar'
        }],
        'extra_string': ['a_string', 'a_new_string'],
        'extra_float': [0.6]
    }
    extras = task_mgr.get_current_extras()
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

  def test_check_episode_end(self):
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
    task.log_parsing_config.log_regexps.episode_end = 'I am done!'
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    task_mgr.setup_task(adb_controller=self._adb_controller)
    episode_end = task_mgr.check_if_episode_ended()
    self.assertTrue(episode_end)

if __name__ == '__main__':
  absltest.main()
