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

"""Tests for device_connection, verifying pure WebSocket transport."""

from unittest import mock

from absl.testing import absltest
from android_env.components import config_classes
from android_env.components import device_connection
from android_env.proto import device_env_service_pb2
import websocket


class DeviceConnectionTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._mock_ws_create = mock.patch.object(
        websocket, 'create_connection', autospec=True
    ).start()
    self._mock_ws = self._mock_ws_create.return_value
    self._set_mock_state_response()

  def tearDown(self):
    mock.patch.stopall()
    super().tearDown()

  def _set_mock_state_response(self):
    msg = device_env_service_pb2.ServerMessage()
    sig = msg.state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
    sig.active_package = 'com.example.app'
    self._mock_ws.recv.return_value = msg.SerializeToString()

  def test_init_success(self):
    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)

    self._mock_ws_create.assert_called_once_with('ws://localhost:8000')
    conn.close()

  def test_init_failure_raises_error(self):
    self._mock_ws_create.side_effect = websocket.WebSocketException(
        'WS Connection failed'
    )

    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    with self.assertRaises(RuntimeError) as context:
      device_connection.DeviceConnection(config=config)

    self.assertIn('Failed to connect to WebSocket', str(context.exception))

  def test_send_message(self):
    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)
    self._mock_ws.send_binary.reset_mock()

    msg = device_env_service_pb2.ClientMessage()
    msg.get_state.SetInParent()
    conn.send_message(msg)

    self._mock_ws.send_binary.assert_called_once_with(msg.SerializeToString())
    conn.close()

  def test_get_device_state(self):
    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)
    state = conn.get_device_state()

    self.assertLen(state.signals, 1)
    self.assertEqual(
        state.signals[0].type,
        device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE,
    )
    conn.close()

  def test_get_device_state_sends_request_when_state_is_none(self):
    self._mock_ws.recv.side_effect = websocket.WebSocketException('No state')

    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)
    self._mock_ws.send_binary.reset_mock()

    def mock_send_binary(data):
      sent_msg = device_env_service_pb2.ClientMessage()
      sent_msg.ParseFromString(data)
      self.assertTrue(sent_msg.HasField('get_state'))
      state = device_env_service_pb2.DeviceState()
      sig = state.signals.add()
      sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
      sig.active_package = 'com.test.app'
      conn._latest_state = state

    self._mock_ws.send_binary.side_effect = mock_send_binary

    state = conn.get_device_state()

    self.assertEqual(state.signals[0].active_package, 'com.test.app')
    self._mock_ws.send_binary.assert_called_once()
    conn.close()

  def test_get_device_state_raises_server_error(self):
    msg = device_env_service_pb2.ServerMessage()
    msg.error.message = 'Internal server error'
    self._mock_ws.recv.return_value = msg.SerializeToString()

    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)

    with self.assertRaisesRegex(
        RuntimeError, 'Server error: Internal server error'
    ):
      conn.get_device_state()

    conn.close()

  def test_get_device_state_raises_when_missing_state_or_error(self):
    msg = device_env_service_pb2.ServerMessage()
    self._mock_ws.recv.return_value = msg.SerializeToString()

    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)

    with self.assertRaisesRegex(RuntimeError, 'Server response missing state'):
      conn.get_device_state()

    conn.close()

  def test_get_device_state_timeout(self):
    self._mock_ws.recv.side_effect = websocket.WebSocketException('No state')

    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)

    def mock_wait(*args, **kwargs):
      del args, kwargs

    with mock.patch.object(
        conn._state_condition, 'wait', side_effect=mock_wait
    ):
      with self.assertRaisesRegex(
          RuntimeError, 'Timed out waiting for initial device state'
      ):
        conn.get_device_state()

    conn.close()

  def test_not_connected_raises_error(self):
    config = config_classes.DeviceConnectionConfig(
        host='localhost', websocket_port=8000
    )
    conn = device_connection.DeviceConnection(config=config)
    conn.close()

    with self.assertRaisesRegex(RuntimeError, 'Not connected'):
      conn.get_device_state()

    with self.assertRaisesRegex(RuntimeError, 'Not connected'):
      conn.send_message(device_env_service_pb2.ClientMessage())


if __name__ == '__main__':
  absltest.main()
