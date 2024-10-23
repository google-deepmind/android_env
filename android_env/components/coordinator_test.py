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

"""Tests for android_env.components.coordinator."""

import tempfile
import time
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import action_type
from android_env.components import adb_call_parser
from android_env.components import config_classes
from android_env.components import coordinator as coordinator_lib
from android_env.components import device_settings as device_settings_lib
from android_env.components import errors
from android_env.components import task_manager
from android_env.components.simulators import base_simulator
from android_env.proto import adb_pb2
from android_env.proto import state_pb2
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
    self._coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        device_settings=device_settings_lib.DeviceSettings(self._simulator),
    )

  def tearDown(self):
    super().tearDown()
    self._coordinator.close()

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_relaunch_simulator(self, unused_mock_sleep):
    relaunch_count = self._coordinator.stats()['relaunch_count']
    self._coordinator._launch_simulator()
    self.assertEqual(self._coordinator.stats()['relaunch_count'],
                     relaunch_count + 1)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_reset(self, unused_mock_sleep):
    """'relaunch_count_execute_action' should be zero if there's no error."""

    self._coordinator.rl_reset()
    stats = self._coordinator.stats()
    self.assertIn('relaunch_count_execute_action', stats)
    self.assertEqual(stats['relaunch_count_execute_action'], 0)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_reset_error_sending_action(self, unused_mock_sleep):
    """'relaunch_count_execute_action' should be positive if there's an error."""

    self._simulator.send_touch.side_effect = errors.SendActionError()
    self._coordinator.rl_reset()
    stats = self._coordinator.stats()
    self.assertIn('relaunch_count_execute_action', stats)
    self.assertEqual(stats['relaunch_count_execute_action'], 1)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_lift_all_fingers(self, unused_mock_sleep):
    self._coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        device_settings=device_settings_lib.DeviceSettings(self._simulator),
        config=config_classes.CoordinatorConfig(num_fingers=3),
    )
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

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_process_action(self, unused_mock_sleep):

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

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_process_action_error(self, unused_mock_sleep):

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

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_execute_action_touch(self, unused_mock_sleep):

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

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_execute_multitouch_action(self, unused_mock_sleep):
    self._coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        device_settings=device_settings_lib.DeviceSettings(self._simulator),
        config=config_classes.CoordinatorConfig(num_fingers=3),
    )

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

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_execute_action_repeat(self, unused_mock_sleep):
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

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_execute_action_error(self, unused_mock_sleep):
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

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_max_restarts_setup_steps(self, unused_mock_sleep):
    init_fn_call = self._task_manager.setup_task.call_count
    self._task_manager.setup_task.side_effect = errors.StepCommandError
    self.assertRaises(errors.TooManyRestartsError,
                      self._coordinator._launch_simulator)
    # The method was called three more times when attempting to relaunch.
    self.assertEqual(init_fn_call + 3,
                     self._task_manager.setup_task.call_count)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_execute_adb_call(self, unused_mock_sleep):
    call = adb_pb2.AdbRequest(
        force_stop=adb_pb2.AdbRequest.ForceStop(package_name='blah'))
    expected_response = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    self._adb_call_parser.parse.side_effect = [expected_response]

    response = self._coordinator.execute_adb_call(call)

    self.assertEqual(response, expected_response)
    self._adb_call_parser.parse.assert_called_with(call)


if __name__ == '__main__':
  absltest.main()
