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

"""Tests for android_env.components.coordinator."""

import tempfile
import time
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import action_type
from android_env.components import adb_call_parser
from android_env.components import coordinator as coordinator_lib
from android_env.components import errors
from android_env.components import task_manager
from android_env.components.simulators import base_simulator
from android_env.proto import adb_pb2
from android_env.proto import task_pb2
import dm_env
import numpy as np


class CoordinatorTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._simulator = mock.create_autospec(base_simulator.BaseSimulator)
    self._random_screenshot = np.random.randint(
        low=0, high=255, size=(800, 600, 3), dtype=np.uint8)
    self._simulator.get_screenshot.return_value = self._random_screenshot
    self._task_manager = mock.create_autospec(task_manager.TaskManager)
    self._adb_call_parser = mock.create_autospec(adb_call_parser.AdbCallParser)
    self.enter_context(
        mock.patch.object(
            adb_call_parser,
            'AdbCallParser',
            autospec=True,
            return_value=self._adb_call_parser))
    self.enter_context(mock.patch.object(time, 'sleep', autospec=True))
    self._coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        num_fingers=1,
        periodic_restart_time_min=0)

  def test_relaunch_simulator(self):
    relaunch_count = self._coordinator.stats()['relaunch_count']
    self._coordinator._launch_simulator()
    self.assertEqual(self._coordinator.stats()['relaunch_count'],
                     relaunch_count + 1)

  def test_reset(self):
    self._coordinator.rl_reset()

  def test_lift_all_fingers(self):
    self._coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        num_fingers=3,
        periodic_restart_time_min=0)
    self._coordinator.rl_reset()
    expected_actions = [
        # (x, y, is_down, identifier).
        (0, 0, False, 0),
        (0, 0, False, 1),
        (0, 0, False, 2),
    ]
    actual_actions = self._simulator.send_touch.call_args[0][0]
    for actual, expected in zip(actual_actions, expected_actions):
      np.testing.assert_array_equal(actual, expected)

  def test_process_action(self):

    def fake_rl_step(simulator_signals):
      return dm_env.transition(
          reward=10.0,
          observation={
              'pixels': simulator_signals['pixels'],
              'orientation': simulator_signals['orientation'],
              'timedelta': simulator_signals['timedelta'],
              'extras': {
                  'extra': [0.0]
              }
          })

    self._task_manager.rl_step.side_effect = fake_rl_step
    timestep = self._coordinator.rl_step(
        agent_action={
            'action_type': np.array(action_type.ActionType.LIFT),
            'touch_position': np.array([0.5, 0.5]),
        })
    obs = timestep.observation
    self.assertEqual(obs['pixels'].shape, (800, 600, 3))
    np.testing.assert_equal(obs['orientation'],
                            np.array([0, 0, 0, 0], dtype=np.uint8))
    self.assertEqual(timestep.reward, 10.0)
    self.assertEqual(obs['extras'], {'extra': [0.0]})
    self.assertFalse(timestep.last())

  def test_process_action_error(self):

    def fake_rl_step(simulator_signals):
      self.assertFalse(simulator_signals['simulator_healthy'])
      return dm_env.truncation(reward=0.0, observation=None)

    self._task_manager.rl_step.side_effect = fake_rl_step
    self._simulator.get_screenshot.side_effect = errors.ReadObservationError()
    timestep = self._coordinator.rl_step(
        agent_action={
            'action_type': np.array(action_type.ActionType.LIFT),
            'touch_position': np.array([0.5, 0.5]),
        })
    self.assertIsNone(timestep.observation)
    self.assertEqual(timestep.reward, 0.0)
    self.assertTrue(timestep.last())

  def test_execute_action_touch(self):

    def fake_rl_step(simulator_signals):
      return dm_env.transition(
          reward=123.0,
          observation={
              'pixels': simulator_signals['pixels'],
              'orientation': simulator_signals['orientation'],
              'timedelta': simulator_signals['timedelta'],
              'extras': {
                  'extra': [0.0]
              }
          })

    self._task_manager.rl_step.side_effect = fake_rl_step
    timestep = self._coordinator.rl_step(
        agent_action={
            'action_type': np.array(action_type.ActionType.TOUCH),
            'touch_position': np.array([0.5, 0.5])
        })
    self.assertEqual(timestep.reward, 123.0)
    np.testing.assert_equal(timestep.observation['pixels'],
                            self._random_screenshot)
    self._simulator.send_touch.assert_called_once_with([(300, 400, True, 0)])

  def test_execute_multitouch_action(self):
    self._coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        num_fingers=3,
        periodic_restart_time_min=0)

    def fake_rl_step(simulator_signals):
      return dm_env.transition(
          reward=456.0,
          observation={
              'pixels': simulator_signals['pixels'],
              'orientation': simulator_signals['orientation'],
              'timedelta': simulator_signals['timedelta'],
              'extras': {
                  'extra': [0.0]
              }
          })

    self._task_manager.rl_step.side_effect = fake_rl_step
    action = {
        'action_type': np.array([action_type.ActionType.TOUCH]),
        'touch_position': np.array([0.25, 0.75]),
        'action_type_2': np.array([action_type.ActionType.TOUCH]),
        'touch_position_2': np.array([0.75, 0.25]),
        'action_type_3': np.array([action_type.ActionType.LIFT]),
        'touch_position_3': np.array([0.5, 0.5]),
    }
    timestep = self._coordinator.rl_step(action)
    self._simulator.send_touch.assert_called_once_with([(150, 600, True, 0),
                                                        (450, 200, True, 1),
                                                        (300, 400, False, 2)])
    self.assertEqual(timestep.reward, 456.0)
    np.testing.assert_equal(timestep.observation['pixels'],
                            self._random_screenshot)

  def test_execute_action_repeat(self):

    def fake_rl_step(simulator_signals):
      return dm_env.transition(
          reward=10.0,
          observation={
              'pixels': simulator_signals['pixels'],
              'orientation': simulator_signals['orientation'],
              'timedelta': simulator_signals['timedelta'],
              'extras': {
                  'extra': [0.0]
              }
          })

    self._task_manager.rl_step.side_effect = fake_rl_step
    timestep = self._coordinator.rl_step(
        {'action_type': np.array(action_type.ActionType.REPEAT)})
    self._simulator.send_touch.assert_not_called()
    np.testing.assert_equal(timestep.observation['pixels'],
                            self._random_screenshot)

  def test_execute_action_error(self):

    def fake_rl_step(simulator_signals):
      self.assertFalse(simulator_signals['simulator_healthy'])
      return dm_env.truncation(reward=0.0, observation=None)

    self._task_manager.rl_step.side_effect = fake_rl_step
    self._simulator.send_touch.side_effect = errors.SendActionError
    timestep = self._coordinator.rl_step({
        'action_type': np.array(action_type.ActionType.TOUCH),
        'touch_position': np.array([0.3, 0.8])
    })
    self.assertIsNone(timestep.observation)

  def test_max_restarts_setup_steps(self):
    init_fn_call = self._task_manager.setup_task.call_count
    self._task_manager.setup_task.side_effect = errors.StepCommandError
    self.assertRaises(errors.TooManyRestartsError,
                      self._coordinator._launch_simulator)
    # The method was called three more times when attempting to relaunch.
    self.assertEqual(init_fn_call + 3,
                     self._task_manager.setup_task.call_count)

  def test_execute_adb_call(self):
    call = adb_pb2.AdbRequest(
        force_stop=adb_pb2.AdbRequest.ForceStop(package_name='blah'))
    expected_response = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    self._adb_call_parser.parse.side_effect = [expected_response]

    response = self._coordinator.execute_adb_call(call)

    self.assertEqual(response, expected_response)
    self._adb_call_parser.parse.assert_called_with(call)

  @mock.patch.object(tempfile, 'gettempdir', autospec=True)
  def test_with_tmp_dir_no_tempfile_call(self, mock_gettempdir):
    """If passing a `tmp_dir`, `tempfile.gettempdir()` should not be called."""
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        periodic_restart_time_min=0,
        tmp_dir=absltest.get_default_test_tmpdir())
    mock_gettempdir.assert_not_called()

  @mock.patch.object(tempfile, 'gettempdir', autospec=True)
  def test_no_tmp_dir_calls_tempfile(self, mock_gettempdir):
    """If not passing a `tmp_dir`, `tempfile.gettempdir()` should be called."""
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        periodic_restart_time_min=0)
    mock_gettempdir.assert_called_once()

  @parameterized.parameters(
      (True, '1'),
      (False, '0'),
  )
  def test_touch_indicator(self, show, expected_value):
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        show_touches=show)
    self._adb_call_parser.parse.assert_any_call(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='show_touches', value=expected_value))))

  @parameterized.parameters(
      (True, '1'),
      (False, '0'),
  )
  def test_pointer_location(self, show, expected_value):
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        show_pointer_location=show)
    self._adb_call_parser.parse.assert_any_call(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='pointer_location', value=expected_value))))

  @parameterized.parameters(
      (True, True, 'null*'),
      (True, False, 'immersive.status=*'),
      (False, True, 'immersive.navigation=*'),
      (False, False, 'immersive.full=*'),
      (None, None, 'immersive.full=*'),  # Defaults to hiding both.
  )
  def test_bar_visibility(self, show_navigation_bar, show_status_bar,
                          expected_value):
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        show_navigation_bar=show_navigation_bar,
        show_status_bar=show_status_bar)
    self._adb_call_parser.parse.assert_any_call(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='policy_control', value=expected_value))))

  def test_update_task_succeeds(self):
    task = task_pb2.Task(id='my_task')
    stop_call_count = self._task_manager.stop_task.call_count
    setup_call_count = self._task_manager.setup_task.call_count
    success = self._coordinator.update_task(task)
    self.assertEqual(1,
                     self._task_manager.stop_task.call_count - stop_call_count)
    self.assertEqual(
        1, self._task_manager.setup_task.call_count - setup_call_count)
    self._task_manager.update_task.assert_called_once_with(task)
    self.assertTrue(success)
    self._task_manager.stats.return_value = {}
    self.assertEqual(0, self._coordinator.stats()['failed_task_updates'])

  def test_update_task_fails(self):
    task = task_pb2.Task(id='my_task')
    self._task_manager.setup_task.side_effect = errors.StepCommandError
    stop_call_count = self._task_manager.stop_task.call_count
    setup_call_count = self._task_manager.setup_task.call_count
    success = self._coordinator.update_task(task)
    self.assertEqual(1,
                     self._task_manager.stop_task.call_count - stop_call_count)
    self.assertEqual(
        1, self._task_manager.setup_task.call_count - setup_call_count)
    self._task_manager.update_task.assert_called_once_with(task)
    self.assertFalse(success)
    self._task_manager.stats.return_value = {}
    self.assertEqual(1, self._coordinator.stats()['failed_task_updates'])


if __name__ == '__main__':
  absltest.main()
