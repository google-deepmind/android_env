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

"""Unit tests for task-free AndroidEnv in android_env.rl.environment."""

from unittest import mock
from absl.testing import absltest
from android_env.components import action_type
from android_env.components import android_device
from android_env.components import config_classes
from android_env.components import device_connection
from android_env.components import telemetry
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2
from android_env.rl import environment as android_device_env
import numpy as np


class FakeDeviceConnection(device_connection.DeviceConnection):

  def __init__(
      self, config: config_classes.DeviceConnectionConfig | None = None
  ):
    config = config or config_classes.DeviceConnectionConfig()
    self._config = config
    self._video_codec: str = 'h264'
    self._video_width: int = 640
    self._video_height: int = 480
    self.fake_frame: np.ndarray = np.ones((480, 640, 3), dtype=np.uint8)
    self.device_state: device_env_service_pb2.DeviceState = (
        device_env_service_pb2.DeviceState()
    )
    self.injected_actions: list[device_env_service_pb2.Action] = []
    self.subscriptions: set[int] = {
        device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    }
    self.closed: bool = False

  def connect(self):
    pass

  def get_video_metadata(self) -> tuple[str, int, int]:
    return self._video_codec, self._video_width, self._video_height

  def get_device_state(self) -> device_env_service_pb2.DeviceState:
    if device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT in self.subscriptions:
      if not any(
          sig.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
          for sig in self.device_state.signals
      ):
        h, w, _ = self.fake_frame.shape
        sig = self.device_state.signals.add()
        sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
        sig.screenshot.decoded.raw_pixels = self.fake_frame.tobytes()
        sig.screenshot.decoded.width = w
        sig.screenshot.decoded.height = h
    return self.device_state

  def inject_action(self, action: device_env_service_pb2.Action):
    self.injected_actions.append(action)

  def update_subscriptions(self, signals: set[int]):
    self.subscriptions = set(signals)

  def send_message(self, msg: device_env_service_pb2.ClientMessage):
    payload_type = msg.WhichOneof('payload')
    if payload_type == 'inject_action':
      self.injected_actions.append(msg.inject_action.action)
    elif payload_type == 'update_subscriptions':
      self.subscriptions = set(msg.update_subscriptions.active_signals)
    elif msg.HasField('inject_action'):
      self.injected_actions.append(msg.inject_action.action)
    elif msg.HasField('update_subscriptions'):
      self.subscriptions = set(msg.update_subscriptions.active_signals)

  def close(self):
    self.closed = True


def _make_env(
    fake_conn: FakeDeviceConnection,
    on_close_callbacks=None,
    on_error_callbacks=None,
) -> android_device_env.AndroidEnv:
  dev = android_device.AndroidDevice(
      connection=fake_conn,
      on_close_callbacks=on_close_callbacks,
      on_error_callbacks=on_error_callbacks,
  )
  return android_device_env.AndroidEnv(device=dev)


class AndroidDeviceEnvTest(absltest.TestCase):

  def test_init(self):
    fake_conn = FakeDeviceConnection()
    _ = _make_env(fake_conn)
    self.assertEqual(
        fake_conn.subscriptions,
        {
            device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
            device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE,
            device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS,
            device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
            device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER,
        },
    )

  def test_task_extras_battery_power(self):
    fake_conn = FakeDeviceConnection()
    env = _make_env(fake_conn)
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER
    sig.battery_power.level_percent = 85
    sig.battery_power.current_now_ua = 450000
    sig.battery_power.voltage_mv = 4200
    sig.battery_power.power_mw = 1890.0
    sig.battery_power.temperature_celsius = 28.5
    sig.battery_power.status = 'DISCHARGING'
    sig.battery_power.plugged_source = 'UNPLUGGED'
    sig.battery_power.charge_counter_uah = 3000000
    sig.battery_power.thermal_status = 0
    sig.battery_power.energy_counter_nwh = 15000000000
    fake_conn.device_state = state
    env.reset()
    extras = env.task_extras()
    self.assertIn('battery_power', extras)
    bp = extras['battery_power']
    self.assertIsInstance(bp, telemetry.BatteryPowerMetrics)

    # Verify clean structured attribute access.
    self.assertEqual(bp.level_percent, 85)
    self.assertEqual(bp.current_now_ua, 450000)
    self.assertEqual(bp.voltage_mv, 4200)
    self.assertAlmostEqual(bp.power_mw, 1890.0)
    self.assertAlmostEqual(bp.temperature_celsius, 28.5)
    self.assertEqual(bp.status, 'DISCHARGING')
    self.assertEqual(bp.plugged_source, 'UNPLUGGED')
    self.assertEqual(bp.charge_counter_uah, 3000000)
    self.assertEqual(bp.thermal_status, 0)
    self.assertEqual(bp.energy_counter_nwh, 15000000000)

  def test_specs(self):
    fake_conn = FakeDeviceConnection()
    env = _make_env(fake_conn)
    action_spec = env.action_spec()
    self.assertIn('action_type', action_spec)
    self.assertIn('touch_position', action_spec)
    self.assertIn('keycode', action_spec)

    obs_spec = env.observation_spec()
    self.assertIn('pixels', obs_spec)
    self.assertIn('orientation', obs_spec)
    self.assertIn('timedelta', obs_spec)

  def test_reset(self):
    fake_conn = FakeDeviceConnection()
    env = _make_env(fake_conn)
    timestep = env.reset()
    self.assertTrue(timestep.first())
    self.assertIn('pixels', timestep.observation)

  def test_step_touch(self):
    fake_conn = FakeDeviceConnection()
    env = _make_env(fake_conn)
    _ = env.reset()
    action = {
        'action_type': np.array(action_type.ActionType.TOUCH, dtype=np.float32),
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    }
    timestep = env.step(action)
    self.assertTrue(timestep.mid())
    self.assertLen(fake_conn.injected_actions, 1)

  def test_close(self):
    fake_conn = FakeDeviceConnection()
    on_close = mock.MagicMock()
    env = _make_env(fake_conn, on_close_callbacks=[on_close])
    env.close()
    self.assertTrue(fake_conn.closed)
    on_close.assert_called_once()

  def test_video_resolution_detection_from_screenshot_signal(self):
    fake_conn = FakeDeviceConnection()
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig.screenshot.decoded.height = 480
    sig.screenshot.decoded.width = 640
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    obs_spec = env.observation_spec()
    self.assertEqual(obs_spec['pixels'].shape, (480, 640, 3))

  def test_video_resolution_fallback_default(self):
    fake_conn = FakeDeviceConnection()
    fake_conn.subscriptions = set()
    fake_conn.device_state = device_env_service_pb2.DeviceState()

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    obs_spec = env.observation_spec()
    self.assertEqual(obs_spec['pixels'].shape, (1080, 1920, 3))

  def test_build_observation_pixels_and_cached(self):
    fake_conn = FakeDeviceConnection()
    raw_pixels = np.ones((2, 2, 3), dtype=np.uint8)
    fake_conn.fake_frame = raw_pixels
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig.screenshot.decoded.width = 2
    sig.screenshot.decoded.height = 2
    sig.screenshot.decoded.raw_pixels = raw_pixels.tobytes()
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    ts = env.reset()
    np.testing.assert_array_equal(ts.observation['pixels'], raw_pixels)
    self.assertEqual(ts.observation['active_package'], '')

    # Next step with no new screenshot reuses cached pixels.
    fake_conn.device_state = device_env_service_pb2.DeviceState()
    ts = env.step({})
    np.testing.assert_array_equal(ts.observation['pixels'], raw_pixels)
    self.assertEqual(ts.observation['active_package'], '')

  def test_build_observation_orientation_bounds(self):
    fake_conn = FakeDeviceConnection()
    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)

    # Valid orientation 2 -> one-hot [0, 0, 1, 0]
    fake_conn.device_state.orientation = 2
    ts = env.step({})
    np.testing.assert_array_equal(
        ts.observation['orientation'], np.array([0, 0, 1, 0], dtype=np.uint8)
    )

    # Out-of-bounds orientation 99 -> fallback one-hot [1, 0, 0, 0]
    fake_conn.device_state.orientation = 99
    ts = env.step({})
    np.testing.assert_array_equal(
        ts.observation['orientation'], np.array([1, 0, 0, 0], dtype=np.uint8)
    )

  def test_task_extras(self):
    fake_conn = FakeDeviceConnection()
    state = device_env_service_pb2.DeviceState()
    sig1 = state.signals.add()
    sig1.type = device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS
    sig1.system_logs.values.append('log1')
    sig2 = state.signals.add()
    sig2.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS
    ev = sig2.accessibility_events.events.add()
    sig3 = state.signals.add()
    sig3.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    env.reset()
    extras = env.task_extras()
    self.assertEqual(extras['logs'], ['log1'])
    self.assertEqual(extras['accessibility_events'], [ev])
    self.assertEqual(extras['accessibility_tree'], sig3.accessibility_forest)

  def test_step_action_types(self):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    mock_dev.get_state.return_value = device_env_service_pb2.DeviceState()
    env = android_device_env.AndroidEnv(device=mock_dev)

    # 1. TOUCH
    env.step({
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': [0.2, 0.8],
    })
    self.assertTrue(mock_dev.send_action.called)
    last_act = mock_dev.send_action.call_args[0][0]
    self.assertEqual(
        last_act.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
    )
    self.assertAlmostEqual(last_act.touch_position.x, 0.2)
    self.assertAlmostEqual(last_act.touch_position.y, 0.8)

    # 2. REPEAT when touching
    mock_dev.send_action.reset_mock()
    env.step({'action_type': action_type.ActionType.REPEAT})
    last_act = mock_dev.send_action.call_args[0][0]
    self.assertEqual(
        last_act.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE
    )

    # 3. LIFT with position
    mock_dev.send_action.reset_mock()
    env.step({
        'action_type': action_type.ActionType.LIFT,
        'touch_position': [0.5, 0.5],
    })
    last_act = mock_dev.send_action.call_args[0][0]
    self.assertEqual(
        last_act.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_UP
    )

    # 4. REPEAT when not touching (no action sent)
    mock_dev.send_action.reset_mock()
    env.step({'action_type': action_type.ActionType.REPEAT})
    mock_dev.send_action.assert_not_called()

    # 5. KEYDOWN
    mock_dev.send_action.reset_mock()
    env.step({'action_type': action_type.ActionType.KEYDOWN, 'keycode': 66})
    last_act = mock_dev.send_action.call_args[0][0]
    self.assertEqual(
        last_act.action_type, device_env_service_pb2.ACTION_TYPE_KEY_EVENT
    )
    self.assertEqual(last_act.keycode, 66)

    # 6. KEYUP
    mock_dev.send_action.reset_mock()
    env.step({'action_type': action_type.ActionType.KEYUP})

    # 7. Unrecognized action type
    mock_dev.send_action.reset_mock()
    env.step({'action_type': 999})
    mock_dev.send_action.assert_not_called()

    # 8. TEXT action
    mock_dev.send_action.reset_mock()
    env.step(
        {'action_type': action_type.ActionType.TEXT, 'text': 'hello world'}
    )
    last_act = mock_dev.send_action.call_args[0][0]
    self.assertEqual(
        last_act.action_type, device_env_service_pb2.ACTION_TYPE_SET_TEXT
    )
    self.assertEqual(last_act.text, 'hello world')

  def test_parse_signals_extra_signals(self):
    fake_conn = FakeDeviceConnection()
    state = device_env_service_pb2.DeviceState()
    sig1 = state.signals.add()
    sig1.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
    sig1.active_package = 'com.example.app'
    sig2 = state.signals.add()
    sig2.type = device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT
    pcm = np.array([[10, 20]], dtype=np.int16)
    sig2.audio_output.raw_bytes = pcm.tobytes()
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    ts = env.reset()
    self.assertEqual(ts.observation['active_package'], 'com.example.app')
    np.testing.assert_array_equal(ts.observation['audio'], pcm)

  def test_parse_signals_none_state(self):
    fake_conn = FakeDeviceConnection()
    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    res = env._parse_signals(None)
    self.assertEqual(res, (None, None, None, None))

  def test_parse_signals_screenshot_undecoded(self):
    fake_conn = FakeDeviceConnection()
    fake_conn.subscriptions = set()
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig.screenshot.encoded_bytes = b'fake_compressed_jpeg_bytes'
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    pixels, _, _, _ = env._parse_signals(state)
    self.assertIsNone(pixels)
    self.assertTrue(sig.screenshot.HasField('encoded_bytes'))

  def test_parse_signals_system_logs(self):
    fake_conn = FakeDeviceConnection()
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS
    sig.system_logs.values.append('log line 1')
    sig.system_logs.values.append('log line 2')
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    _, _, _, logs = env._parse_signals(state)
    self.assertEqual(logs, ['log line 1', 'log line 2'])

  def test_parse_signals_screenshot_empty_signal(self):
    fake_conn = FakeDeviceConnection()
    fake_conn.subscriptions = set()
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    pixels, _, _, _ = env._parse_signals(state)
    self.assertIsNone(pixels)

  def test_parse_signals_logs_none_for_non_logs_signals(self):
    fake_conn = FakeDeviceConnection()
    state = device_env_service_pb2.DeviceState()
    sig1 = state.signals.add()
    sig1.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
    sig1.active_package = 'com.example.app'
    sig2 = state.signals.add()
    sig2.type = device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT
    fake_conn.device_state = state

    dev = android_device.AndroidDevice(connection=fake_conn)
    env = android_device_env.AndroidEnv(device=dev)
    _, _, _, logs = env._parse_signals(state)
    self.assertIsNone(logs)

  def test_context_manager(self):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    with android_device_env.AndroidEnv(device=mock_dev) as env:
      self.assertIsInstance(env, android_device_env.AndroidEnv)
    mock_dev.__exit__.assert_called_once()

  def test_execute_adb_call_delegates_to_device(self):
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    env = android_device_env.AndroidEnv(device=mock_dev)
    req = adb_pb2.AdbRequest()
    mock_dev.execute_adb_call.return_value = adb_pb2.AdbResponse()
    res = env.execute_adb_call(req)
    mock_dev.execute_adb_call.assert_called_once_with(req)
    self.assertIsInstance(res, adb_pb2.AdbResponse)


if __name__ == '__main__':
  absltest.main()
