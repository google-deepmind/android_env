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

"""Tests for android_device_env, verifying dm_env API compliance."""

from unittest import mock
from absl.testing import absltest
from android_env import android_device_env
from android_env.components import action_type
from android_env.components import config_classes
from android_env.components import device_connection
from android_env.proto import device_env_service_pb2
import numpy as np


class FakeDeviceConnection(device_connection.DeviceConnection):
  """Fake DeviceConnection for unit tests without network side-effects."""

  def __init__(
      self,
      config: config_classes.DeviceConnectionConfig | None = None,
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
    self.subscriptions: set[int] = set()
    self.closed: bool = False

  def connect(self):
    pass

  def get_video_metadata(self) -> tuple[str, int, int]:
    return self._video_codec, self._video_width, self._video_height

  def get_device_state(self) -> device_env_service_pb2.DeviceState:
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

  def close(self):
    self.closed = True


class AndroidDeviceEnvTest(absltest.TestCase):

  def test_init(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    self.assertEqual(
        fake_conn.subscriptions,
        {
            device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
            device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE,
            device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS,
            device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
            device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS,
        },
    )
    self.assertEqual(env._pixel_shape, (480, 640, 3))

  def test_specs(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    action_spec = env.action_spec()
    self.assertIn('action_type', action_spec)
    self.assertIn('touch_position', action_spec)

    obs_spec = env.observation_spec()
    self.assertIn('pixels', obs_spec)
    self.assertIn('active_package', obs_spec)
    self.assertEqual(obs_spec['pixels'].shape, (480, 640, 3))

  def test_reset(self):
    fake_conn = FakeDeviceConnection()
    sig = fake_conn.device_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
    sig.active_package = 'com.test.app'

    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    timestep = env.reset()

    self.assertTrue(timestep.first())
    self.assertEqual(timestep.observation['active_package'], 'com.test.app')
    np.testing.assert_array_equal(
        timestep.observation['pixels'], fake_conn.fake_frame
    )

  def test_step(self):
    fake_conn = FakeDeviceConnection()
    sig = fake_conn.device_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
    sig.active_package = 'com.test.app.after'

    fake_frame_after = np.ones((480, 640, 3), dtype=np.uint8) * 2
    fake_conn.fake_frame = fake_frame_after

    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env.reset()

    action = {
        'action_type': np.array(0),  # TOUCH
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    }
    timestep = env.step(action)

    expected_proto_action = device_env_service_pb2.Action()
    expected_proto_action.action_type = (
        device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
    )
    expected_proto_action.touch_position.x = 0.5
    expected_proto_action.touch_position.y = 0.5
    self.assertEqual(fake_conn.injected_actions, [expected_proto_action])

    self.assertTrue(timestep.mid())
    self.assertEqual(
        timestep.observation['active_package'], 'com.test.app.after'
    )
    np.testing.assert_array_equal(
        timestep.observation['pixels'], fake_frame_after
    )
    self.assertEqual(timestep.reward, 0.0)

  def test_task_extras(self):
    fake_conn = FakeDeviceConnection()
    sig = fake_conn.device_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS
    sig.system_logs.values.extend(['log1', 'log2'])

    sig_tree = fake_conn.device_state.signals.add()
    sig_tree.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig_tree.accessibility_forest.windows.add()

    sig_events = fake_conn.device_state.signals.add()
    sig_events.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS
    ev = sig_events.accessibility_events.events.add()
    ev.event['event_type'] = 'TYPE_VIEW_CLICKED'

    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env.reset()  # populates _latest_state

    extras = env.task_extras()
    self.assertEqual(extras['logs'], ['log1', 'log2'])
    self.assertLen(extras['accessibility_events'], 1)
    self.assertEqual(
        extras['accessibility_events'][0].event['event_type'],
        'TYPE_VIEW_CLICKED',
    )
    self.assertIsNotNone(extras['accessibility_tree'])

  def test_audio_observation(self):
    fake_conn = FakeDeviceConnection()
    sig = fake_conn.device_state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT
    audio_data = np.array([[100, 200], [300, 400]], dtype=np.int16)
    sig.audio_output.raw_bytes = audio_data.tobytes()

    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env._active_signals.add(device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT)
    timestep = env.reset()
    self.assertIn('audio', timestep.observation)
    np.testing.assert_array_equal(timestep.observation['audio'], audio_data)

  def test_reset_orientation(self):
    for val, expected_arr in [
        (0, [1, 0, 0, 0]),
        (1, [0, 1, 0, 0]),
        (2, [0, 0, 1, 0]),
        (3, [0, 0, 0, 1]),
        (4, [1, 0, 0, 0]),
    ]:
      fake_conn = FakeDeviceConnection()
      fake_conn.device_state.orientation = val
      env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
      timestep = env.reset()
      np.testing.assert_array_equal(
          timestep.observation['orientation'],
          np.array(expected_arr, dtype=np.uint8),
      )

  def test_step_orientation(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env.reset()

    for val, expected_arr in [
        (0, [1, 0, 0, 0]),
        (1, [0, 1, 0, 0]),
        (2, [0, 0, 1, 0]),
        (3, [0, 0, 0, 1]),
        (4, [1, 0, 0, 0]),
    ]:
      fake_conn.device_state.orientation = val
      action = {
          'action_type': np.array(action_type.ActionType.TOUCH),
          'touch_position': np.array([0.5, 0.5], dtype=np.float32),
      }
      timestep = env.step(action)
      np.testing.assert_array_equal(
          timestep.observation['orientation'],
          np.array(expected_arr, dtype=np.uint8),
      )

  def test_step_repeat_touch(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env.reset()

    action_touch = {
        'action_type': np.array(action_type.ActionType.TOUCH),
        'touch_position': np.array([0.3, 0.7], dtype=np.float32),
    }
    env.step(action_touch)
    self.assertLen(fake_conn.injected_actions, 1)
    last_action = fake_conn.injected_actions[-1]
    self.assertEqual(
        last_action.action_type,
        device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN,
    )
    self.assertAlmostEqual(last_action.touch_position.x, 0.3)
    self.assertAlmostEqual(last_action.touch_position.y, 0.7)

    action_repeat = {
        'action_type': np.array(action_type.ActionType.REPEAT),
        'touch_position': np.array([0.0, 0.0], dtype=np.float32),
    }
    env.step(action_repeat)
    self.assertLen(fake_conn.injected_actions, 2)
    last_action = fake_conn.injected_actions[-1]
    self.assertEqual(
        last_action.action_type,
        device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE,
    )
    self.assertAlmostEqual(last_action.touch_position.x, 0.3)
    self.assertAlmostEqual(last_action.touch_position.y, 0.7)

  def test_step_keyup_clears_last_non_touch_action(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env.reset()

    action_keydown = {
        'action_type': np.array(action_type.ActionType.KEYDOWN),
        'keycode': np.array(66),
    }
    env.step(action_keydown)
    self.assertLen(fake_conn.injected_actions, 1)
    last_action = fake_conn.injected_actions[-1]
    self.assertEqual(
        last_action.action_type,
        device_env_service_pb2.ACTION_TYPE_KEY_EVENT,
    )
    self.assertEqual(last_action.keycode, 66)

    action_keyup = {
        'action_type': np.array(action_type.ActionType.KEYUP),
    }
    env.step(action_keyup)
    self.assertLen(fake_conn.injected_actions, 1)

    action_repeat = {
        'action_type': np.array(action_type.ActionType.REPEAT),
    }
    env.step(action_repeat)
    self.assertLen(fake_conn.injected_actions, 1)

  def test_close_callbacks(self):
    def dummy_cb():
      pass

    mock_close_cb = mock.create_autospec(dummy_cb)
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(
        connection=fake_conn, on_close_callbacks=[mock_close_cb]
    )
    env.close()
    mock_close_cb.assert_called_once()
    self.assertTrue(fake_conn.closed)

  def test_context_manager_calls_close(self):
    def dummy_cb():
      pass

    mock_close_cb = mock.create_autospec(dummy_cb)
    fake_conn = FakeDeviceConnection()
    with android_device_env.AndroidDeviceEnv(
        connection=fake_conn, on_close_callbacks=[mock_close_cb]
    ):
      pass
    mock_close_cb.assert_called_once()
    self.assertTrue(fake_conn.closed)

  def test_context_manager_calls_error_callbacks(self):
    def dummy_error_cb(exc_type, exc_value, traceback):
      del exc_type, exc_value, traceback

    mock_error_cb = mock.create_autospec(dummy_error_cb)

    def dummy_close_cb():
      pass

    mock_close_cb = mock.create_autospec(dummy_close_cb)
    fake_conn = FakeDeviceConnection()

    with self.assertRaises(ValueError):
      with android_device_env.AndroidDeviceEnv(
          connection=fake_conn,
          on_close_callbacks=[mock_close_cb],
          on_error_callbacks=[mock_error_cb],
      ):
        raise ValueError('Test error')

    mock_error_cb.assert_called_once_with(ValueError, mock.ANY, mock.ANY)
    mock_close_cb.assert_called_once()
    self.assertTrue(fake_conn.closed)

  def test_step_touch_up_transition(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env.reset()

    # Touch down
    env.step({
        'action_type': np.array(action_type.ActionType.TOUCH),
        'touch_position': np.array([0.4, 0.6], dtype=np.float32),
    })
    self.assertLen(fake_conn.injected_actions, 1)

    # Touch up / lift
    env.step({
        'action_type': np.array(action_type.ActionType.LIFT),
        'touch_position': np.array([0.4, 0.6], dtype=np.float32),
    })
    self.assertLen(fake_conn.injected_actions, 2)
    self.assertEqual(
        fake_conn.injected_actions[-1].action_type,
        device_env_service_pb2.ACTION_TYPE_TOUCH_UP,
    )

  def test_reset_without_screenshot_signal(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env._active_signals.remove(device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT)
    timestep = env.reset()
    np.testing.assert_array_equal(
        timestep.observation['pixels'], np.zeros((480, 640, 3), dtype=np.uint8)
    )

  def test_stats(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    self.assertEqual(env.stats(), {})

  def test_step_lift_without_explicit_touch_position(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    env.reset()

    # Touch down first to set last touch position
    env.step({
        'action_type': np.array(action_type.ActionType.TOUCH),
        'touch_position': np.array([0.4, 0.6], dtype=np.float32),
    })

    # LIFT without touch_position in action dict
    env.step({'action_type': np.array(action_type.ActionType.LIFT)})
    self.assertLen(fake_conn.injected_actions, 2)
    last_action = fake_conn.injected_actions[-1]
    self.assertEqual(
        last_action.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_UP
    )
    self.assertAlmostEqual(last_action.touch_position.x, 0.4)
    self.assertAlmostEqual(last_action.touch_position.y, 0.6)

  def test_parse_signals_with_none_state(self):
    fake_conn = FakeDeviceConnection()
    env = android_device_env.AndroidDeviceEnv(connection=fake_conn)
    pixels, active_pkg, audio = env._parse_signals(None)
    np.testing.assert_array_equal(
        pixels, np.zeros((480, 640, 3), dtype=np.uint8)
    )
    self.assertEqual(active_pkg, '')
    self.assertEqual(len(audio), 0)


if __name__ == '__main__':
  absltest.main()
