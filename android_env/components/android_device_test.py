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

"""Unit tests for android_device.AndroidDevice."""

import time
from unittest import mock

from absl.testing import absltest
from android_env.components import adb_call_parser
from android_env.components import android_device
from android_env.components import device_connection
from android_env.components import errors
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2
import cv2
import numpy as np


class AndroidDeviceTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._mock_connection = mock.create_autospec(
        device_connection.DeviceConnection, instance=True
    )
    self._mock_connection.get_device_state.return_value = (
        device_env_service_pb2.DeviceState()
    )

  def test_get_state_decodes_screenshot(self):
    img = np.zeros((50, 50, 3), dtype=np.uint8)
    img[5:15, 5:15] = [0, 255, 0]
    success, encoded_img = cv2.imencode('.png', img)
    self.assertTrue(success)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig.screenshot.encoded_bytes = encoded_img.tobytes()

    self._mock_connection.get_device_state.return_value = state
    device = android_device.AndroidDevice(connection=self._mock_connection)

    dev_state = device.get_state()
    screenshot_sig = dev_state.signals[0]
    decoded = screenshot_sig.screenshot.decoded
    pixels = np.frombuffer(decoded.raw_pixels, dtype=np.uint8).reshape(
        (decoded.height, decoded.width, 3)
    )
    expected_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    np.testing.assert_array_equal(pixels, expected_rgb)

  def test_decode_screenshot_invalid_image(self):
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig.screenshot.encoded_bytes = b'invalid_image_bytes'

    self._mock_connection.get_device_state.return_value = state
    device = android_device.AndroidDevice(connection=self._mock_connection)

    dev_state = device.get_state()
    screenshot_sig = dev_state.signals[0]
    self.assertFalse(screenshot_sig.screenshot.HasField('decoded'))

  @mock.patch.object(time, 'time_ns', autospec=True)
  def test_clock_sync_calculates_offset(self, mock_time):
    def make_time_func(t1_ns):
      times = [1_000_000_000, t1_ns]
      return lambda: times.pop(0) if times else 1_030_000_000

    for t1_ns, expected_offset in [
        (1_020_000_000, 3990),  # rtt = 20ms -> rtt//2 = 10ms -> offset = 3990ms
        (1_021_000_000, 3990),  # rtt = 21ms -> rtt//2 = 10ms -> offset = 3990ms
        (1_022_000_000, 3989),  # rtt = 22ms -> rtt//2 = 11ms -> offset = 3989ms
    ]:
      with self.subTest(t1_ns=t1_ns):
        mock_time.side_effect = make_time_func(t1_ns)
        state = device_env_service_pb2.DeviceState()
        sig = state.signals.add()
        sig.type = device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS
        sig.device_settings.entries['device_time_ms'] = '5000'

        self._mock_connection.get_device_state.return_value = state
        device = android_device.AndroidDevice(connection=self._mock_connection)

        self.assertEqual(device._clock_offset_ms, expected_offset)

  def test_clock_sync_handles_connection_error(self):
    self._mock_connection.get_device_state.side_effect = RuntimeError(
        'Connection error'
    )
    device = android_device.AndroidDevice(connection=self._mock_connection)
    self.assertEqual(device._clock_offset_ms, 0)

  def test_clock_sync_handles_value_error(self):
    self._mock_connection.get_device_state.side_effect = ValueError(
        'Value error'
    )
    device = android_device.AndroidDevice(connection=self._mock_connection)
    self.assertEqual(device._clock_offset_ms, 0)

  def test_clock_sync_missing_device_time_setting(self):
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS
    # entries lacks device_time_ms
    self._mock_connection.get_device_state.return_value = state
    device = android_device.AndroidDevice(connection=self._mock_connection)
    self.assertEqual(device._clock_offset_ms, 0)

  def test_send_action_sends_client_message(self):
    device = android_device.AndroidDevice(connection=self._mock_connection)
    self._mock_connection.send_message.reset_mock()

    action = device_env_service_pb2.Action()
    action.action_type = device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
    device.send_action(action)

    self._mock_connection.send_message.assert_called_once()
    sent_msg = self._mock_connection.send_message.call_args[0][0]
    self.assertTrue(sent_msg.HasField('inject_action'))
    self.assertEqual(sent_msg.inject_action.action, action)

  def test_update_subscriptions_sends_client_message(self):
    device = android_device.AndroidDevice(connection=self._mock_connection)
    self._mock_connection.send_message.reset_mock()

    signals = {device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT}
    device.update_subscriptions(signals)

    self._mock_connection.send_message.assert_called_once()
    sent_msg = self._mock_connection.send_message.call_args[0][0]
    self.assertTrue(sent_msg.HasField('update_subscriptions'))
    self.assertCountEqual(sent_msg.update_subscriptions.active_signals, signals)

  def test_close_runs_callbacks(self):
    cb1 = mock.MagicMock()
    cb2 = mock.MagicMock()
    device = android_device.AndroidDevice(
        connection=self._mock_connection,
        on_close_callbacks=[cb1, cb2],
    )
    device.close()

    self._mock_connection.close.assert_called_once()
    cb1.assert_called_once()
    cb2.assert_called_once()

  def test_context_manager_normal_exit(self):
    cb = mock.MagicMock()
    with android_device.AndroidDevice(
        connection=self._mock_connection,
        on_close_callbacks=[cb],
    ):
      pass

    self._mock_connection.close.assert_called_once()
    cb.assert_called_once()

  def test_context_manager_error_exit(self):
    on_close = mock.MagicMock()
    on_error = mock.MagicMock()
    try:
      with android_device.AndroidDevice(
          connection=self._mock_connection,
          on_close_callbacks=[on_close],
          on_error_callbacks=[on_error],
      ):
        raise ValueError('Test error')
    except ValueError:
      pass

    on_error.assert_called_once()
    on_close.assert_called_once()
    self._mock_connection.close.assert_called_once()

  def test_execute_adb_call_with_adb_call_parser(self):
    mock_parser = mock.create_autospec(
        adb_call_parser.AdbCallParser, instance=True
    )
    device = android_device.AndroidDevice(
        connection=self._mock_connection,
        adb_call_parser=mock_parser,
    )

    req = adb_pb2.AdbRequest(
        generic=adb_pb2.AdbRequest.GenericRequest(args=['shell', 'ls'])
    )
    mock_parser.parse.return_value = adb_pb2.AdbResponse()
    res = device.execute_adb_call(req)
    mock_parser.parse.assert_called_once_with(req)
    self.assertIsInstance(res, adb_pb2.AdbResponse)

  def test_execute_adb_call_without_adb_call_parser_raises(self):
    device = android_device.AndroidDevice(connection=self._mock_connection)

    req = adb_pb2.AdbRequest()
    with self.assertRaises(errors.AdbControllerError):
      device.execute_adb_call(req)


if __name__ == '__main__':
  absltest.main()
