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

"""Tests for playground device_runner."""

import typing
from unittest import mock

from absl.testing import absltest
from android_env.components import android_device
from android_env.components import config_classes
from android_env.components import errors
from android_env.playground import actions as actions_lib
from android_env.playground import device_runner
from android_env.playground import state as state_lib
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2
from android_env.proto import task_pb2
import numpy as np


class DeviceRunnerTest(absltest.TestCase):

  def test_update_orientation_no_change(self):
    orientation_container = [0]
    device_runner._update_orientation(0, orientation_container)
    self.assertEqual(orientation_container[0], 0)

  def test_update_orientation_changed(self):
    orientation_container = [0]
    with mock.patch.object(device_runner.logging, 'info') as mock_info:
      device_runner._update_orientation(1, orientation_container)
      self.assertEqual(orientation_container[0], 1)
      mock_info.assert_called_once()

  def test_extract_screenshot_valid(self):
    state = device_env_service_pb2.DeviceState()
    signal = state.signals.add()
    signal.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    img_data = np.zeros((10, 20, 3), dtype=np.uint8)
    signal.screenshot.decoded.raw_pixels = img_data.tobytes()
    signal.screenshot.decoded.width = 20
    signal.screenshot.decoded.height = 10

    pixels = device_runner._extract_screenshot(state)
    self.assertIsNotNone(pixels)
    self.assertEqual(pixels.shape, (10, 20, 3))

  def test_extract_screenshot_missing(self):
    state = device_env_service_pb2.DeviceState()
    pixels = device_runner._extract_screenshot(state)
    self.assertIsNone(pixels)

  @mock.patch.object(
      device_runner.frame_processing, 'process_frame', autospec=True
  )
  @mock.patch.object(device_runner.websocket, 'try_send_frame', autospec=True)
  def test_update_frame(self, mock_send_frame, mock_process_frame):
    state = state_lib.PlaygroundState()
    pixels = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_process_frame.return_value = b'jpeg_bytes'

    device_runner._update_frame(state, pixels, 0)

    mock_process_frame.assert_called_once_with(pixels, 0)
    self.assertEqual(state.current_frame, b'jpeg_bytes')
    mock_send_frame.assert_called_once_with(state, b'jpeg_bytes')

  def test_get_actions_empty(self):
    state = state_lib.PlaygroundState()
    actions = device_runner._get_actions(state, frame_rate_secs=0.1)
    self.assertEqual(actions, [])

  def test_get_actions_single(self):
    state = state_lib.PlaygroundState()
    act = actions_lib.ClientAction(
        action_type='touch_down',
        x=0.5,
        y=0.5,
        client_timestamp_ms=100.0,
        recv_timestamp_ms=105.0,
    )
    state.action_queue.put(act)
    actions = device_runner._get_actions(state, frame_rate_secs=0.1)
    self.assertEqual(actions, [act])

  def test_get_actions_multiple_coalesced(self):
    state = state_lib.PlaygroundState()
    act1 = actions_lib.ClientAction(
        action_type='touch_move',
        x=0.5,
        y=0.5,
        client_timestamp_ms=100.0,
        recv_timestamp_ms=105.0,
    )
    act2 = actions_lib.ClientAction(
        action_type='touch_move',
        x=0.6,
        y=0.6,
        client_timestamp_ms=110.0,
        recv_timestamp_ms=115.0,
    )
    state.action_queue.put(act1)
    state.action_queue.put(act2)
    actions = device_runner._get_actions(state, frame_rate_secs=0.1)
    self.assertLen(actions, 1)
    self.assertEqual(actions[0].x, 0.6)

  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(
      device_runner.coordinates, 'map_client_coordinates', autospec=True
  )
  @mock.patch.object(
      device_runner.actions_lib, 'map_client_action_to_proto', autospec=True
  )
  def test_send_client_actions(
      self, mock_map_proto, mock_map_coords, mock_update_frame
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    orientation_container = [0]
    last_pos = np.array([0.0, 0.0])

    dev_state = device_env_service_pb2.DeviceState(orientation=0)
    sig = dev_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    sig.screenshot.decoded.raw_pixels = img.tobytes()
    sig.screenshot.decoded.width = 10
    sig.screenshot.decoded.height = 10
    mock_dev.get_state.return_value = dev_state

    proto_action = device_env_service_pb2.Action(
        action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
    )
    mock_map_proto.return_value = proto_action
    mock_map_coords.return_value = np.array([5.0, 5.0])

    act_data = actions_lib.ClientAction(
        action_type='touch_down',
        x=0.5,
        y=0.5,
        client_timestamp_ms=100.0,
        recv_timestamp_ms=105.0,
    )

    res_last_pos, res_pixels = device_runner._send_client_actions(
        mock_dev,
        [act_data],
        state,
        orientation_container,
        last_pos,
        (10, 10),
    )

    mock_dev.send_action.assert_called_once_with(proto_action)
    np.testing.assert_array_equal(res_last_pos, np.array([5.0, 5.0]))
    self.assertIsNotNone(res_pixels)
    mock_update_frame.assert_called_once()

  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(
      device_runner.coordinates, 'map_client_coordinates', autospec=True
  )
  @mock.patch.object(
      device_runner.actions_lib, 'map_client_action_to_proto', autospec=True
  )
  def test_send_client_actions_updates_orientation_per_action(
      self, mock_map_proto, mock_map_coords, mock_update_frame
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    orientation_container = [0]
    last_pos = np.array([0.0, 0.0])

    dev_state_0 = device_env_service_pb2.DeviceState(orientation=1)
    dev_state_1 = device_env_service_pb2.DeviceState(orientation=1)
    mock_dev.get_state.side_effect = [dev_state_0, dev_state_1]

    mock_map_proto.return_value = device_env_service_pb2.Action()
    mock_map_coords.side_effect = [np.array([1.0, 1.0]), np.array([2.0, 2.0])]

    act_1 = actions_lib.ClientAction(
        action_type='touch_down',
        x=0.1,
        y=0.1,
        client_timestamp_ms=100.0,
        recv_timestamp_ms=105.0,
    )
    act_2 = actions_lib.ClientAction(
        action_type='touch_move',
        x=0.2,
        y=0.2,
        client_timestamp_ms=110.0,
        recv_timestamp_ms=115.0,
    )

    device_runner._send_client_actions(
        mock_dev,
        [act_1, act_2],
        state,
        orientation_container,
        last_pos,
        (10, 10),
    )

    self.assertEqual(mock_dev.send_action.call_count, 2)
    self.assertEqual(mock_dev.get_state.call_count, 2)
    self.assertEqual(orientation_container[0], 1)
    self.assertEqual(mock_map_coords.call_args_list[0][0][2], 0)
    self.assertEqual(mock_map_coords.call_args_list[1][0][2], 1)
    mock_update_frame.assert_not_called()

  def test_update_battery_stats(self):
    state = state_lib.PlaygroundState()
    dev_state = device_env_service_pb2.DeviceState()
    sig = dev_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER
    sig.battery_power.level_percent = 85
    sig.battery_power.voltage_mv = 4100

    device_runner._update_battery_stats(dev_state, state)

    battery_stats = state.get_battery_power_stats()
    self.assertIsNotNone(battery_stats)
    self.assertEqual(battery_stats.get('level_percent'), 85)
    self.assertEqual(battery_stats.get('voltage_mv'), 4100)

  def test_update_battery_stats_missing(self):
    state = state_lib.PlaygroundState()
    dev_state = device_env_service_pb2.DeviceState()
    device_runner._update_battery_stats(dev_state, state)
    self.assertIsNone(state.get_battery_power_stats())

  def test_load_task_proto_from_textproto_file(self):
    task_file = self.create_tempfile(
        'task.textproto', content='id: "my_task"\nname: "My Task"\n'
    )
    task = device_runner._load_task_proto(
        task_file.full_path, self.create_tempdir().full_path
    )
    self.assertEqual(task.id, 'my_task')
    self.assertEqual(task.name, 'My Task')

  def test_get_interpreter_for_device_fallback(self):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    mock_dev.execute_adb_call.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK
    )
    interpreter = device_runner._get_interpreter_for_device(mock_dev)
    self.assertIsNotNone(interpreter)
    req = adb_pb2.AdbRequest()
    res = interpreter._adb_call_parser.parse(req)
    self.assertEqual(res.status, adb_pb2.AdbResponse.Status.OK)
    mock_dev.execute_adb_call.assert_called_once_with(req)

  def test_handle_task_reload_no_request(self):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    current_task = task_pb2.Task()
    orientation_container = [0]

    task, pixels = device_runner._handle_task_reload(
        mock_dev, state, orientation_container, current_task
    )
    self.assertEqual(task, current_task)
    self.assertIsNone(pixels)

  @mock.patch.object(device_runner.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(device_runner, '_load_task_proto', autospec=True)
  @mock.patch.object(
      device_runner, '_get_interpreter_for_device', autospec=True
  )
  def test_handle_task_reload_success(
      self, mock_get_interp, mock_load_proto, mock_send_status
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.set_reload('sample_task')

    loaded_task = task_pb2.Task()
    mock_load_proto.return_value = loaded_task

    mock_interp = mock.MagicMock()
    mock_get_interp.return_value = mock_interp

    dev_state = device_env_service_pb2.DeviceState(orientation=1)
    sig = dev_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    sig.screenshot.decoded.raw_pixels = img.tobytes()
    sig.screenshot.decoded.width = 10
    sig.screenshot.decoded.height = 10
    mock_dev.get_state.return_value = dev_state

    orientation_container = [0]
    task, pixels = device_runner._handle_task_reload(
        mock_dev, state, orientation_container, None
    )

    self.assertEqual(task, loaded_task)
    self.assertIsNotNone(pixels)
    self.assertEqual(orientation_container[0], 1)
    mock_interp.interpret.assert_called_once_with(loaded_task.setup_steps)
    mock_send_status.assert_any_call(state, 'Ready! Task: sample_task')

  @mock.patch.object(device_runner.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(device_runner, '_load_task_proto', autospec=True)
  def test_handle_task_reload_load_error(
      self, mock_load_proto, mock_send_status
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.set_reload('bad_task')
    mock_load_proto.side_effect = RuntimeError('Failed to load')

    orientation_container = [0]
    task, pixels = device_runner._handle_task_reload(
        mock_dev, state, orientation_container, None
    )

    self.assertIsNone(task)
    self.assertIsNone(pixels)
    mock_send_status.assert_any_call(
        state, 'ERROR loading task bad_task: Failed to load'
    )

  def test_handle_episode_reset_no_request(self):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    orientation_container = [0]

    pixels = device_runner._handle_episode_reset(
        mock_dev, state, orientation_container, None
    )
    self.assertIsNone(pixels)

  @mock.patch.object(device_runner.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(
      device_runner, '_get_interpreter_for_device', autospec=True
  )
  def test_handle_episode_reset_success(
      self, mock_get_interp, mock_send_status
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.set_reset()

    current_task = task_pb2.Task()
    current_task.reset_steps.add()

    mock_interp = mock.MagicMock()
    mock_get_interp.return_value = mock_interp

    dev_state = device_env_service_pb2.DeviceState(orientation=0)
    sig = dev_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    sig.screenshot.decoded.raw_pixels = img.tobytes()
    sig.screenshot.decoded.width = 10
    sig.screenshot.decoded.height = 10
    mock_dev.get_state.return_value = dev_state

    orientation_container = [0]
    pixels = device_runner._handle_episode_reset(
        mock_dev, state, orientation_container, current_task
    )

    self.assertIsNotNone(pixels)
    mock_interp.interpret.assert_called_once_with(current_task.reset_steps)
    mock_send_status.assert_any_call(state, 'Ready! Episode reset.')

  @mock.patch.object(
      device_runner.websocket, 'try_send_adb_response', autospec=True
  )
  def test_execute_single_adb_command_syntax_error(self, mock_send_adb):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    device_runner._execute_single_adb_command(
        mock_dev, state, 'shell "unclosed'
    )
    mock_send_adb.assert_called_once()
    self.assertEqual(
        mock_send_adb.call_args[1]['status'], 'FAILED_PRECONDITION'
    )

  @mock.patch.object(
      device_runner.websocket, 'try_send_adb_response', autospec=True
  )
  def test_execute_single_adb_command_empty(self, mock_send_adb):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    device_runner._execute_single_adb_command(mock_dev, state, 'adb')
    device_runner._execute_single_adb_command(mock_dev, state, '   ')
    self.assertEqual(mock_send_adb.call_count, 2)
    self.assertEqual(
        mock_send_adb.call_args_list[0][1]['status'], 'FAILED_PRECONDITION'
    )
    self.assertEqual(
        mock_send_adb.call_args_list[1][1]['status'], 'FAILED_PRECONDITION'
    )

  @mock.patch.object(
      device_runner.websocket, 'try_send_adb_response', autospec=True
  )
  def test_execute_single_adb_command_execution_error(self, mock_send_adb):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    mock_dev.execute_adb_call.side_effect = RuntimeError('ADB connection lost')
    state = state_lib.PlaygroundState()
    with mock.patch.object(
        device_runner.time, 'time', autospec=True, side_effect=[10.0, 10.15]
    ):
      device_runner._execute_single_adb_command(
          mock_dev, state, 'adb shell getprop'
      )
    mock_send_adb.assert_called_once()
    self.assertEqual(mock_send_adb.call_args[1]['status'], 'INTERNAL_ERROR')
    self.assertEqual(mock_send_adb.call_args[1]['duration_ms'], 150.0)

  @mock.patch.object(
      device_runner.websocket, 'try_send_adb_response', autospec=True
  )
  def test_execute_single_adb_command_success(self, mock_send_adb):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    resp = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK,
        generic=adb_pb2.AdbResponse.GenericResponse(output=b'google/pixel\n'),
    )
    mock_dev.execute_adb_call.return_value = resp
    state = state_lib.PlaygroundState()
    with mock.patch.object(
        device_runner.time, 'time', autospec=True, side_effect=[20.0, 20.05]
    ):
      device_runner._execute_single_adb_command(
          mock_dev, state, 'shell getprop ro.product.name'
      )
    mock_send_adb.assert_called_once()
    self.assertEqual(mock_send_adb.call_args[1]['status'], 'OK')
    self.assertEqual(mock_send_adb.call_args[1]['output'], 'google/pixel\n')
    self.assertEqual(mock_send_adb.call_args[1]['duration_ms'], 50.0)

  @mock.patch.object(
      device_runner.websocket, 'try_send_adb_response', autospec=True
  )
  def test_execute_single_adb_command_unrecognized_status(self, mock_send_adb):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    resp = adb_pb2.AdbResponse(
        status=typing.cast(typing.Any, 999),
        generic=adb_pb2.AdbResponse.GenericResponse(output=b''),
    )
    mock_dev.execute_adb_call.return_value = resp
    state = state_lib.PlaygroundState()
    with mock.patch.object(
        device_runner.time, 'time', autospec=True, side_effect=[30.0, 30.01]
    ):
      device_runner._execute_single_adb_command(mock_dev, state, 'adb devices')
    mock_send_adb.assert_called_once()
    self.assertEqual(mock_send_adb.call_args[1]['status'], '999')
    self.assertEqual(mock_send_adb.call_args[1]['duration_ms'], 10.0)

  @mock.patch.object(
      device_runner, '_execute_single_adb_command', autospec=True
  )
  def test_handle_adb_commands(self, mock_execute_cmd):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.adb_queue.put('adb devices')
    state.adb_queue.put('adb shell')
    device_runner._handle_adb_commands(mock_dev, state)
    self.assertEqual(mock_execute_cmd.call_count, 2)

  def test_setup_device_no_config_raises(self):
    state = state_lib.PlaygroundState()
    with self.assertRaises(device_runner.DeviceSetupError):
      device_runner.setup_device(state, None)

  @mock.patch.object(
      device_runner.android_device_loader,
      'load_android_device',
      autospec=True,
  )
  def test_setup_device_load_error_raises(self, mock_loader):
    mock_loader.side_effect = errors.AdbControllerError('ADB failed')
    state = state_lib.PlaygroundState()
    config = config_classes.AndroidDeviceConfig()
    with self.assertRaises(device_runner.DeviceSetupError):
      device_runner.setup_device(state, config)

  @mock.patch.object(
      device_runner.android_device_loader,
      'load_android_device',
      autospec=True,
  )
  def test_setup_device_missing_screenshot_raises(self, mock_loader):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    mock_dev.get_state.return_value = device_env_service_pb2.DeviceState()
    mock_loader.return_value = mock_dev
    state = state_lib.PlaygroundState()
    config = config_classes.AndroidDeviceConfig()
    with self.assertRaises(device_runner.DeviceSetupError):
      device_runner.setup_device(state, config)
    mock_dev.close.assert_called_once()

  @mock.patch.object(
      device_runner.android_device_loader,
      'load_android_device',
      autospec=True,
  )
  def test_setup_device_success(self, mock_loader):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    dev_state = device_env_service_pb2.DeviceState(orientation=1)
    sig = dev_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    sig.screenshot.decoded.raw_pixels = img.tobytes()
    sig.screenshot.decoded.width = 10
    sig.screenshot.decoded.height = 10
    mock_dev.get_state.return_value = dev_state
    mock_loader.return_value = mock_dev

    state = state_lib.PlaygroundState()
    config = config_classes.AndroidEnvConfig(
        device=config_classes.AndroidDeviceConfig()
    )

    dev, orientation, pixels = device_runner.setup_device(state, config)
    self.assertEqual(dev, mock_dev)
    self.assertEqual(orientation, 1)
    self.assertEqual(pixels.shape, (10, 10, 3))

  def test_setup_device_invalid_config_type(self):
    state = state_lib.PlaygroundState()
    with self.assertRaises(device_runner.DeviceSetupError):
      device_runner.setup_device(state, 'invalid_config_type')

  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(device_runner, '_send_client_actions', autospec=True)
  @mock.patch.object(device_runner, '_get_actions', autospec=True)
  def test_run_device_loop_with_actions(
      self, mock_get_actions, mock_send_actions, unused_mock_frame
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    act = actions_lib.ClientAction(
        action_type='touch_down',
        x=0.5,
        y=0.5,
        client_timestamp_ms=100.0,
        recv_timestamp_ms=105.0,
    )
    mock_get_actions.return_value = [act]
    pixels = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_send_actions.return_value = (np.array([5.0, 5.0]), pixels)

    def _stop_running(*unused_args, **unused_kwargs):
      state.running = False
      return np.array([5.0, 5.0]), pixels

    mock_send_actions.side_effect = _stop_running

    device_runner.run_device(mock_dev, 0, pixels, state)

    mock_send_actions.assert_called_once()

  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(device_runner, '_get_actions', autospec=True)
  def test_run_device_loop_idle(self, mock_get_actions, unused_mock_frame):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    dev_state = device_env_service_pb2.DeviceState(orientation=0)
    sig = dev_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    sig.screenshot.decoded.raw_pixels = img.tobytes()
    sig.screenshot.decoded.width = 10
    sig.screenshot.decoded.height = 10
    mock_dev.get_state.return_value = dev_state

    state = state_lib.PlaygroundState()
    mock_get_actions.return_value = []

    def _stop_running_on_get_state():
      state.running = False
      return dev_state

    mock_dev.get_state.side_effect = _stop_running_on_get_state
    pixels = np.zeros((10, 10, 3), dtype=np.uint8)

    device_runner.run_device(mock_dev, 0, pixels, state)

    mock_dev.get_state.assert_called_once()

  @mock.patch.object(device_runner.websocket, 'try_send_stats', autospec=True)
  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(device_runner, '_get_actions', autospec=True)
  def test_run_device_loop_stats_flush(
      self, mock_get_actions, unused_mock_frame, mock_send_stats
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    dev_state = device_env_service_pb2.DeviceState(orientation=0)
    sig = dev_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER
    sig.battery_power.level_percent = 90
    mock_dev.get_state.return_value = dev_state

    state = state_lib.PlaygroundState()
    state.add_stat('test_stat', 42.0)
    mock_get_actions.return_value = []

    iteration = [0]

    def _advance_and_stop():
      iteration[0] += 1
      if iteration[0] >= 2:
        state.running = False
      return dev_state

    mock_dev.get_state.side_effect = _advance_and_stop

    pixels = np.zeros((10, 10, 3), dtype=np.uint8)
    with mock.patch.object(
        device_runner.time,
        'time',
        side_effect=[0.0, 0.0, 0.1, 1.0, 1.0, 1.0, 1.0],
    ):
      device_runner.run_device(mock_dev, 0, pixels, state)

    mock_send_stats.assert_called_once()

  @mock.patch.object(device_runner.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(device_runner, '_load_task_proto', autospec=True)
  @mock.patch.object(
      device_runner, '_get_interpreter_for_device', autospec=True
  )
  def test_handle_task_reload_interpret_error(
      self, mock_get_interp, mock_load_proto, mock_send_status
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.set_reload('bad_task')
    task = task_pb2.Task()
    task.setup_steps.add()
    mock_load_proto.return_value = task
    mock_interp = mock.MagicMock()
    mock_interp.interpret.side_effect = RuntimeError('Setup step failed')
    mock_get_interp.return_value = mock_interp

    orientation_container = [0]
    res_task, pixels = device_runner._handle_task_reload(
        mock_dev, state, orientation_container, None
    )
    self.assertIsNone(res_task)
    self.assertIsNone(pixels)
    mock_send_status.assert_any_call(
        state, 'ERROR setting up task bad_task: Setup step failed'
    )

  @mock.patch.object(device_runner.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(device_runner, '_load_task_proto', autospec=True)
  @mock.patch.object(
      device_runner, '_get_interpreter_for_device', autospec=True
  )
  def test_handle_task_reload_get_state_error(
      self, mock_get_interp, mock_load_proto, mock_send_status
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.set_reload('task_id')
    task = task_pb2.Task()
    mock_load_proto.return_value = task
    mock_get_interp.return_value = mock.MagicMock()
    mock_dev.get_state.side_effect = RuntimeError('State error')

    orientation_container = [0]
    res_task, pixels = device_runner._handle_task_reload(
        mock_dev, state, orientation_container, None
    )
    self.assertEqual(res_task, task)
    self.assertIsNone(pixels)
    mock_send_status.assert_any_call(state, 'Ready! Task: task_id')

  @mock.patch.object(device_runner.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(
      device_runner, '_get_interpreter_for_device', autospec=True
  )
  def test_handle_episode_reset_interpret_error(
      self, mock_get_interp, mock_send_status
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.set_reset()
    task = task_pb2.Task()
    task.reset_steps.add()
    mock_interp = mock.MagicMock()
    mock_interp.interpret.side_effect = RuntimeError('Reset step failed')
    mock_get_interp.return_value = mock_interp

    orientation_container = [0]
    pixels = device_runner._handle_episode_reset(
        mock_dev, state, orientation_container, task
    )
    self.assertIsNone(pixels)
    mock_send_status.assert_any_call(
        state, 'ERROR resetting episode: Reset step failed'
    )

  @mock.patch.object(device_runner.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(
      device_runner, '_get_interpreter_for_device', autospec=True
  )
  def test_handle_episode_reset_get_state_error(
      self, mock_get_interp, mock_send_status
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    state.set_reset()
    mock_get_interp.return_value = mock.MagicMock()
    mock_dev.get_state.side_effect = RuntimeError('State error')

    orientation_container = [0]
    pixels = device_runner._handle_episode_reset(
        mock_dev, state, orientation_container, None
    )
    self.assertIsNone(pixels)
    mock_send_status.assert_any_call(
        state, 'ERROR resetting episode: State error'
    )

  @mock.patch.object(device_runner, '_handle_task_reload', autospec=True)
  @mock.patch.object(device_runner, '_handle_episode_reset', autospec=True)
  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(device_runner, '_get_actions', autospec=True)
  def test_run_device_loop_updates_pixels_on_reload_and_reset(
      self, mock_get_actions, unused_mock_frame, mock_reset, mock_reload
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    reload_pixels = np.ones((10, 10, 3), dtype=np.uint8)
    reset_pixels = np.full((10, 10, 3), 2, dtype=np.uint8)

    def _side_effect_reload(*unused_args, **unused_kwargs):
      return task_pb2.Task(), reload_pixels

    def _side_effect_reset(*unused_args, **unused_kwargs):
      state.running = False
      return reset_pixels

    mock_reload.side_effect = _side_effect_reload
    mock_reset.side_effect = _side_effect_reset
    mock_get_actions.return_value = []
    initial_pixels = np.zeros((10, 10, 3), dtype=np.uint8)

    device_runner.run_device(mock_dev, 0, initial_pixels, state)
    mock_reload.assert_called_once()
    mock_reset.assert_called_once()

  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(device_runner, '_get_actions', autospec=True)
  def test_run_device_loop_idle_error(
      self, mock_get_actions, unused_mock_frame
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    mock_get_actions.return_value = []

    def _stop_running(*unused_args, **unused_kwargs):
      state.running = False
      raise RuntimeError('Idle get_state failed')

    mock_dev.get_state.side_effect = _stop_running
    pixels = np.zeros((10, 10, 3), dtype=np.uint8)

    device_runner.run_device(mock_dev, 0, pixels, state)
    mock_dev.get_state.assert_called_once()

  @mock.patch.object(device_runner.websocket, 'try_send_stats', autospec=True)
  @mock.patch.object(device_runner, '_update_frame', autospec=True)
  @mock.patch.object(device_runner, '_get_actions', autospec=True)
  def test_run_device_loop_stats_error(
      self, mock_get_actions, unused_mock_frame, unused_mock_send_stats
  ):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    state = state_lib.PlaygroundState()
    mock_get_actions.return_value = []

    dev_state_idle = device_env_service_pb2.DeviceState(orientation=0)
    sig = dev_state_idle.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    img = np.zeros((10, 10, 3), dtype=np.uint8)
    sig.screenshot.decoded.raw_pixels = img.tobytes()
    sig.screenshot.decoded.width = 10
    sig.screenshot.decoded.height = 10

    call_count = [0]

    def _mock_get_state():
      call_count[0] += 1
      if call_count[0] == 1:
        return dev_state_idle
      state.running = False
      raise RuntimeError('Stats get_state error')

    mock_dev.get_state.side_effect = _mock_get_state

    pixels = np.zeros((10, 10, 3), dtype=np.uint8)
    with mock.patch.object(
        device_runner.time,
        'time',
        side_effect=[0.0, 0.0, 0.1, 1.0, 1.0, 1.0, 1.0],
    ):
      device_runner.run_device(mock_dev, 0, pixels, state)

    self.assertGreaterEqual(call_count[0], 2)


if __name__ == '__main__':
  absltest.main()
