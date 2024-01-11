# coding=utf-8
# Copyright 2023 DeepMind Technologies Limited.
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
from android_env.components import errors
from android_env.components import task_manager
from android_env.components.simulators import base_simulator
from android_env.proto import adb_pb2
from android_env.proto import state_pb2
from android_env.proto import task_pb2
import dm_env
import numpy as np


class MockScreenshotGetter:
  def __init__(self):
    self._screenshot_index = 0

  def get_screenshot(self):
    self._screenshot_index += 1
    return np.array(self._screenshot_index, ndmin=3)


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
        simulator=self._simulator, task_manager=self._task_manager
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
    self._coordinator.rl_reset()

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_lift_all_fingers(self, unused_mock_sleep):
    self._coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
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
  def test_process_action_error_async(self, unused_mock_sleep):
    mock_interaction_thread = mock.create_autospec(
        coordinator_lib.InteractionThread)
    with mock.patch.object(
        coordinator_lib,
        'InteractionThread',
        autospec=True,
        return_value=mock_interaction_thread):
      coordinator = coordinator_lib.Coordinator(
          simulator=self._simulator,
          task_manager=self._task_manager,
          config=config_classes.CoordinatorConfig(
              num_fingers=1, interaction_rate_sec=0.016
          ),
      )

      def fake_rl_step(agent_action, simulator_signals):
        del agent_action
        self.assertFalse(simulator_signals['simulator_healthy'])
        return dm_env.truncation(reward=0.0, observation=None)

      self._task_manager.rl_step.side_effect = fake_rl_step
      mock_interaction_thread.screenshot.side_effect = errors.ReadObservationError(
      )
      timestep = coordinator.rl_step(
          agent_action={
              'action_type': np.array(action_type.ActionType.LIFT),
              'touch_position': np.array([0.5, 0.5]),
          })
      self.assertIsNone(timestep.observation)
      self.assertEqual(timestep.reward, 0.0)
      self.assertTrue(timestep.last())
      coordinator.close()

  def test_async_step_faster_than_screenshot(self):
    """Return same screenshot when step is faster than the interaction rate."""
    screenshot_getter = MockScreenshotGetter()
    self._simulator.get_screenshot.side_effect = screenshot_getter.get_screenshot
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
    coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        config=config_classes.CoordinatorConfig(
            num_fingers=1, interaction_rate_sec=0.5
        ),
    )
    ts1 = coordinator.rl_step(
        agent_action={
            'action_type': np.array(action_type.ActionType.LIFT),
            'touch_position': np.array([0.5, 0.5]),
        })
    ts2 = coordinator.rl_step(
        agent_action={
            'action_type': np.array(action_type.ActionType.LIFT),
            'touch_position': np.array([0.5, 0.5]),
        })
    np.testing.assert_almost_equal(ts2.observation['pixels'],
                                   ts1.observation['pixels'])
    coordinator.close()

  def test_async_step_slower_than_screenshot(self):
    """Return different screenshots when step slower than the interaction rate."""
    screenshot_getter = MockScreenshotGetter()
    self._simulator.get_screenshot.side_effect = screenshot_getter.get_screenshot

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
    coordinator = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        config=config_classes.CoordinatorConfig(
            num_fingers=1, interaction_rate_sec=0.01
        ),
    )
    ts1 = coordinator.rl_step(
        agent_action={
            'action_type': np.array(action_type.ActionType.LIFT),
            'touch_position': np.array([0.5, 0.5]),
        })
    time.sleep(0.5)
    ts2 = coordinator.rl_step(
        agent_action={
            'action_type': np.array(action_type.ActionType.LIFT),
            'touch_position': np.array([0.5, 0.5]),
        })
    np.testing.assert_raises(AssertionError, np.testing.assert_array_equal,
                             ts2.observation['pixels'],
                             ts1.observation['pixels'])
    coordinator.close()

  def test_interaction_thread_closes_upon_relaunch(self):
    """Async coordinator should kill the InteractionThread when relaunching."""
    mock_interaction_thread = mock.create_autospec(
        coordinator_lib.InteractionThread)
    with mock.patch.object(
        coordinator_lib,
        'InteractionThread',
        autospec=True,
        return_value=mock_interaction_thread):
      coordinator = coordinator_lib.Coordinator(
          simulator=self._simulator,
          task_manager=self._task_manager,
          config=config_classes.CoordinatorConfig(
              num_fingers=1,
              periodic_restart_time_min=1e-6,
              interaction_rate_sec=0.5,
          ),
      )
      mock_interaction_thread.stop.assert_not_called()
      mock_interaction_thread.join.assert_not_called()
      time.sleep(0.1)
      coordinator.rl_reset()
      mock_interaction_thread.stop.assert_called_once()
      mock_interaction_thread.join.assert_called_once()
      coordinator.close()

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

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(tempfile, 'gettempdir', autospec=True)
  def test_with_tmp_dir_no_tempfile_call(self, mock_gettempdir,
                                         unused_mock_sleep):
    """If passing a `tmp_dir`, `tempfile.gettempdir()` should not be called."""
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        config=config_classes.CoordinatorConfig(
            tmp_dir=absltest.get_default_test_tmpdir()
        ),
    )
    mock_gettempdir.assert_not_called()

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(tempfile, 'gettempdir', autospec=True)
  def test_no_tmp_dir_calls_tempfile(self, mock_gettempdir, unused_mock_sleep):
    """If not passing a `tmp_dir`, `tempfile.gettempdir()` should be called."""
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator, task_manager=self._task_manager
    )
    mock_gettempdir.assert_called_once()

  @parameterized.parameters(
      (True, '1'),
      (False, '0'),
  )
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_touch_indicator(self, show, expected_value, unused_mock_sleep):
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        config=config_classes.CoordinatorConfig(show_touches=show),
    )
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
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_pointer_location(self, show, expected_value, unused_mock_sleep):
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        config=config_classes.CoordinatorConfig(show_pointer_location=show),
    )
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
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_bar_visibility(self, show_navigation_bar, show_status_bar,
                          expected_value, unused_mock_sleep):
    _ = coordinator_lib.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        config=config_classes.CoordinatorConfig(
            show_navigation_bar=show_navigation_bar,
            show_status_bar=show_status_bar,
        ),
    )
    self._adb_call_parser.parse.assert_any_call(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='policy_control', value=expected_value))))

  def test_load_state(self):
    expected_response = state_pb2.LoadStateResponse(
        status=state_pb2.LoadStateResponse.Status.OK
    )
    request = state_pb2.LoadStateRequest(args={'foo': 'bar'})
    self._simulator.load_state.return_value = expected_response
    stop_call_count = self._task_manager.stop.call_count
    start_call_count = self._task_manager.start.call_count
    response = self._coordinator.load_state(request)
    self.assertEqual(response, expected_response)
    self._simulator.load_state.assert_called_once_with(request)
    self.assertEqual(self._task_manager.stop.call_count, stop_call_count + 1)
    self.assertEqual(self._task_manager.start.call_count, start_call_count + 1)

  def test_save_state(self):
    expected_response = state_pb2.SaveStateResponse(
        status=state_pb2.SaveStateResponse.Status.OK
    )
    request = state_pb2.SaveStateRequest(args={'foo': 'bar'})
    self._simulator.save_state.return_value = expected_response
    response = self._coordinator.save_state(request)
    self.assertEqual(response, expected_response)
    self._simulator.save_state.assert_called_once_with(request)


if __name__ == '__main__':
  absltest.main()
