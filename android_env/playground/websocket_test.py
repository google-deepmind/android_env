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

"""Tests for playground websocket."""

import http.server
import io
import socket
from unittest import mock
from absl.testing import absltest
from android_env.playground import state as state_lib
from android_env.playground import websocket


class WebsocketTest(absltest.TestCase):

  def test_recvall_complete(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.return_value = b'abcd'
    res = websocket._recvall(mock_rfile, 4)
    self.assertEqual(res, b'abcd')
    mock_rfile.read.assert_called_once_with(4)

  def test_recvall_eof(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.return_value = b'ab'
    res = websocket._recvall(mock_rfile, 4)
    self.assertIsNone(res)
    mock_rfile.read.assert_called_once_with(4)

  def test_recvall_oserror(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.side_effect = OSError('read failed')
    self.assertIsNone(websocket._recvall(mock_rfile, 4))

  def test_send_ws_binary_frame_small(self):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    websocket.send_ws_binary_frame(mock_sock, b'hello')
    mock_sock.sendall.assert_called_once_with(b'\x82\x05hello')

  def test_send_ws_binary_frame_medium(self):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    data = b'x' * 200
    websocket.send_ws_binary_frame(mock_sock, data)
    expected_header = b'\x82\x7e\x00\xc8'
    mock_sock.sendall.assert_called_once_with(expected_header + data)

  def test_send_ws_binary_frame_large(self):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    data = b'x' * 70000
    websocket.send_ws_binary_frame(mock_sock, data)
    expected_header = b'\x82\x7f\x00\x00\x00\x00\x00\x01\x11\x70'
    mock_sock.sendall.assert_called_once_with(expected_header + data)

  def test_send_ws_binary_frame_error(self):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    mock_sock.sendall.side_effect = OSError('send error')
    with self.assertRaises(OSError):
      websocket.send_ws_binary_frame(mock_sock, b'hello')

  def test_read_frame_text(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.side_effect = [
        b'\x81\x85',  # Header: FIN=1, Opcode=1 (Text), Mask=1, Length=5
        b'1234',  # Mask Key
        b'YW_X^',  # Masked Payload "hello" XOR "1234"
    ]
    res = websocket._read_frame(mock_rfile)
    self.assertEqual(res, (1, b'hello'))
    mock_rfile.read.assert_has_calls([
        mock.call(2),
        mock.call(4),
        mock.call(5),
    ])

  def test_read_frame_unmasked(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.return_value = b'\x81\x05'
    with mock.patch.object(websocket.logging, 'warning') as mock_warn:
      res = websocket._read_frame(mock_rfile)
      self.assertIsNone(res)
      mock_warn.assert_called_once()
    mock_rfile.read.assert_called_once_with(2)

  def test_read_frame_eof(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.return_value = b''
    res = websocket._read_frame(mock_rfile)
    self.assertIsNone(res)
    mock_rfile.read.assert_called_once_with(2)

  def test_read_frame_medium_payload(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    masked_payload = b'IJKL' * 50
    mock_rfile.read.side_effect = [
        b'\x81\xFE',  # Header
        b'\x00\xC8',  # Extra length bytes
        b'1234',  # Mask Key
        masked_payload,
    ]
    res = websocket._read_frame(mock_rfile)
    self.assertEqual(res, (1, b'x' * 200))
    mock_rfile.read.assert_has_calls([
        mock.call(2),
        mock.call(2),
        mock.call(4),
        mock.call(200),
    ])

  def test_read_frame_large_payload(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    masked_payload = b'IJKL' * 17500
    mock_rfile.read.side_effect = [
        b'\x81\xFF',  # Header
        b'\x00\x00\x00\x00\x00\x01\x11\x70',  # Extra length bytes
        b'1234',  # Mask Key
        masked_payload,
    ]
    res = websocket._read_frame(mock_rfile)
    self.assertEqual(res, (1, b'x' * 70000))
    mock_rfile.read.assert_has_calls([
        mock.call(2),
        mock.call(8),
        mock.call(4),
        mock.call(70000),
    ])

  def test_read_frame_127_eof_len_bytes(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.side_effect = [
        b'\x81\xFF',
        b'',
    ]
    self.assertIsNone(websocket._read_frame(mock_rfile))

  def test_read_frame_incomplete_header(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.return_value = b'\x81'
    res = websocket._read_frame(mock_rfile)
    self.assertIsNone(res)

  def test_read_frame_incomplete_extended_length(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.side_effect = [
        b'\x81\xFE',  # Header
        b'\x00',  # incomplete length
    ]
    res = websocket._read_frame(mock_rfile)
    self.assertIsNone(res)

  def test_read_frame_incomplete_mask(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.side_effect = [
        b'\x81\x85',  # Header (masked, len 5)
        b'123',  # incomplete mask
    ]
    res = websocket._read_frame(mock_rfile)
    self.assertIsNone(res)

  def test_read_frame_incomplete_payload(self):
    mock_rfile = mock.create_autospec(io.BufferedReader, instance=True)
    mock_rfile.read.side_effect = [
        b'\x81\x85',  # Header (masked, len 5)
        b'1234',  # Mask Key
        b'abcd',  # incomplete payload
    ]
    res = websocket._read_frame(mock_rfile)
    self.assertIsNone(res)

  def test_try_send_frame_success(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock
    with mock.patch.object(
        websocket.logging, 'warning', autospec=True
    ) as mock_warning:
      websocket.try_send_frame(state, b'frame_data')
      mock_warning.assert_not_called()
    expected_header = b'\x82\x0a'
    mock_sock.sendall.assert_called_once_with(expected_header + b'frame_data')
    self.assertTrue(state.waiting_for_ack)

  def test_try_send_frame_client_not_ready_backpressure(self):
    state = state_lib.PlaygroundState()
    state.active_ws = mock.create_autospec(socket.socket, instance=True)
    state.waiting_for_ack = True
    state.last_frame_sent_time = 100.0
    with mock.patch.object(websocket.time, 'time', return_value=100.1):
      websocket.try_send_frame(state, b'frame_data')
    state.active_ws.sendall.assert_not_called()
    self.assertTrue(state.waiting_for_ack)

  def test_try_send_frame_client_not_ready_exact_timeout_boundary(self):
    state = state_lib.PlaygroundState()
    state.active_ws = mock.create_autospec(socket.socket, instance=True)
    state.waiting_for_ack = True
    state.last_frame_sent_time = 0.0
    with mock.patch.object(websocket.time, 'time', return_value=0.2):
      websocket.try_send_frame(state, b'frame_data')
    state.active_ws.sendall.assert_not_called()
    self.assertTrue(state.waiting_for_ack)

  def test_try_send_frame_client_not_ready_timeout(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock
    state.waiting_for_ack = True
    state.last_frame_sent_time = 100.0
    with mock.patch.object(
        websocket.logging, 'warning', autospec=True
    ) as mock_warning:
      with mock.patch.object(websocket.time, 'time', return_value=100.21):
        websocket.try_send_frame(state, b'frame_data')
      mock_warning.assert_called_once_with(
          'ACK timeout, resetting waiting_for_ack'
      )
    expected_header = b'\x82\x0a'
    mock_sock.sendall.assert_called_once_with(expected_header + b'frame_data')
    self.assertTrue(state.waiting_for_ack)
    self.assertEqual(state.last_frame_sent_time, 100.21)

  def test_try_send_frame_reentrant_active_ws_lock(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock
    state.waiting_for_ack = True
    state.last_frame_sent_time = 100.0

    # Acquire lock in current thread to ensure reentrancy does not deadlock.
    with state.active_ws_lock:
      with mock.patch.object(websocket.time, 'time', return_value=102.0):
        websocket.try_send_frame(state, b'frame_data')

    expected_header = b'\x82\x0a'
    mock_sock.sendall.assert_called_once_with(expected_header + b'frame_data')
    self.assertTrue(state.waiting_for_ack)

  def test_try_send_frame_no_client(self):
    state = state_lib.PlaygroundState()
    state.active_ws = None
    websocket.try_send_frame(state, b'frame_data')

  def test_try_send_frame_send_error(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    mock_sock.sendall.side_effect = OSError('conn reset')
    state.active_ws = mock_sock
    state.waiting_for_ack = False
    with mock.patch.object(websocket.time, 'time', return_value=100.0):
      websocket.try_send_frame(state, b'frame_data')
    self.assertIsNone(state.active_ws)
    self.assertFalse(state.waiting_for_ack)

  def test_perform_handshake_success(self):
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.headers = {'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ=='}
    mock_handler.wfile = io.BytesIO()
    res = websocket._perform_handshake(mock_handler)
    self.assertTrue(res)
    expected_response = (
        b'HTTP/1.1 101 Switching Protocols\r\n'
        b'Upgrade: websocket\r\n'
        b'Connection: Upgrade\r\n'
        b'Sec-WebSocket-Accept: s3pPLMBiTxaQ9kYGzzhZRbK+xOo=\r\n\r\n'
    )
    self.assertEqual(mock_handler.wfile.getvalue(), expected_response)

  def test_perform_handshake_missing_key(self):
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.headers = {}
    res = websocket._perform_handshake(mock_handler)
    self.assertFalse(res)
    mock_handler.send_error.assert_called_once_with(
        400, 'Missing Sec-WebSocket-Key'
    )

  def test_perform_handshake_write_failed(self):
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.headers = {'Sec-WebSocket-Key': 'dGhlIHNhbXBsZSBub25jZQ=='}
    mock_wfile = mock.create_autospec(io.BufferedWriter, instance=True)
    mock_wfile.write.side_effect = OSError('write error')
    mock_handler.wfile = mock_wfile
    with mock.patch.object(websocket.logging, 'warning') as mock_warn:
      res = websocket._perform_handshake(mock_handler)
      self.assertFalse(res)
      mock_warn.assert_called_once()

  def test_handle_message_ack(self):
    state = state_lib.PlaygroundState()
    state.waiting_for_ack = True
    state.last_frame_sent_time = 100.0
    with mock.patch.object(websocket.time, 'time', return_value=100.5):
      websocket._handle_message('ack', state)
    self.assertFalse(state.waiting_for_ack)
    self.assertEqual(state.pending_stats['ack_latency'], [500.0])

  def test_handle_message_action(self):
    state = state_lib.PlaygroundState()
    msg = 'touch_down,0.5,0.6,123456789.0'
    with mock.patch.object(websocket.time, 'time', return_value=1700000000.0):
      websocket._handle_message(msg, state)
    self.assertEqual(state.action_queue.qsize(), 1)
    act = state.action_queue.get()
    self.assertEqual(act.action_type, 'touch_down')
    self.assertEqual(act.x, 0.5)
    self.assertEqual(act.y, 0.6)
    self.assertEqual(act.client_timestamp_ms, 123456789.0)
    self.assertEqual(act.recv_timestamp_ms, 1700000000000.0)

  def test_handle_message_text(self):
    state = state_lib.PlaygroundState()
    msg = 'text,hello world,123456789.0'
    with mock.patch.object(websocket.time, 'time', return_value=1700000000.0):
      websocket._handle_message(msg, state)
    self.assertEqual(state.action_queue.qsize(), 1)
    act = state.action_queue.get()
    self.assertEqual(act.action_type, 'text')
    self.assertEqual(act.text, 'hello world')
    self.assertEqual(act.client_timestamp_ms, 123456789.0)

  def test_handle_message_text_invalid_timestamp(self):
    state = state_lib.PlaygroundState()
    msg = 'text,hello world,not_a_number'
    with mock.patch.object(websocket.time, 'time', return_value=1700000000.0):
      websocket._handle_message(msg, state)
    self.assertEqual(state.action_queue.qsize(), 1)
    act = state.action_queue.get()
    self.assertEqual(act.action_type, 'text')
    self.assertEqual(act.client_timestamp_ms, 1700000000000.0)

  def test_handle_message_keydown(self):
    state = state_lib.PlaygroundState()
    msg = 'keydown,66,123456789.0'
    with mock.patch.object(websocket.time, 'time', return_value=1700000000.0):
      websocket._handle_message(msg, state)
    self.assertEqual(state.action_queue.qsize(), 1)
    act = state.action_queue.get()
    self.assertEqual(act.action_type, 'keydown')
    self.assertEqual(act.keycode, 66)
    self.assertEqual(act.client_timestamp_ms, 123456789.0)
    self.assertEqual(act.recv_timestamp_ms, 1700000000000.0)

  def test_handle_message_set_selection(self):
    state = state_lib.PlaygroundState()
    msg = 'set_selection,2,5,123456789.0'
    with mock.patch.object(websocket.time, 'time', return_value=1700000000.0):
      websocket._handle_message(msg, state)
    self.assertEqual(state.action_queue.qsize(), 1)
    act = state.action_queue.get()
    self.assertEqual(act.action_type, 'set_selection')
    self.assertEqual(act.selection, (2, 5))
    self.assertEqual(act.client_timestamp_ms, 123456789.0)
    self.assertEqual(act.recv_timestamp_ms, 1700000000000.0)

  def test_handle_message_clipboard(self):
    for clip_act in ('cut', 'copy', 'paste'):
      state = state_lib.PlaygroundState()
      msg = f'{clip_act},123456789.0'
      with mock.patch.object(websocket.time, 'time', return_value=1700000000.0):
        websocket._handle_message(msg, state)
      self.assertEqual(state.action_queue.qsize(), 1)
      act = state.action_queue.get()
      self.assertEqual(act.action_type, clip_act)
      self.assertEqual(act.client_timestamp_ms, 123456789.0)
      self.assertEqual(act.recv_timestamp_ms, 1700000000000.0)

  def test_handle_message_load_task(self):
    state = state_lib.PlaygroundState()
    msg = 'load_task,classic_2048'
    websocket._handle_message(msg, state)
    self.assertEqual(state.get_reload(), 'classic_2048')

  def test_handle_message_load_task_empty_id(self):
    for msg in ('load_task,', 'load_task,   '):
      state = state_lib.PlaygroundState()
      websocket._handle_message(msg, state)
      self.assertIsNone(state.get_reload())

  def test_handle_message_load_task_whitespace(self):
    state = state_lib.PlaygroundState()
    msg = 'load_task, classic_2048 '
    websocket._handle_message(msg, state)
    self.assertEqual(state.get_reload(), 'classic_2048')

  def test_handle_message_load_task_invalid(self):
    state = state_lib.PlaygroundState()
    websocket._handle_message('load_task', state)
    self.assertIsNone(state.get_reload())

  def test_handle_message_invalid(self):
    state = state_lib.PlaygroundState()
    for msg in (
        'invalid,msg',
        'touch_down,not_a_float,0.5,123.0',
        'keydown,not_an_int,123.0',
        'keydown,66',  # Incomplete keydown (2 parts instead of 3)
        'unknown,1,2',  # 3 parts, but not keydown
        'set_selection,a,b,123.0',
        'set_selection,1,2',  # 3 parts instead of 4
        'set_selection,1,2,3,4',  # 5 parts instead of 4
        'unknown,1,2,3,4',  # 5 parts, not set_selection
        'cut,not_a_float',
    ):
      websocket._handle_message(msg, state)
      self.assertEqual(state.action_queue.qsize(), 0)

  @mock.patch.object(websocket, '_perform_handshake', return_value=True)
  @mock.patch.object(websocket, '_read_frame')
  @mock.patch.object(websocket, '_handle_message')
  def test_handle_websocket_loop(
      self, mock_handle_msg, mock_read_frame, mock_handshake
  ):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.request = mock_sock
    mock_handler.rfile = io.BytesIO()
    state = state_lib.PlaygroundState()
    state.set_status('Connected')
    state.current_frame = b'init_frame'
    mock_read_frame.side_effect = [
        (1, b'msg1'),
        (8, b''),
    ]
    websocket.handle_websocket(mock_handler, state)
    mock_handshake.assert_called_once_with(mock_handler)
    mock_sock.setsockopt.assert_called_once_with(
        socket.IPPROTO_TCP, socket.TCP_NODELAY, 1
    )
    self.assertIsNone(state.active_ws)
    self.assertEqual(mock_sock.sendall.call_count, 2)
    self.assertIn(b'Connected', mock_sock.sendall.call_args_list[0][0][0])
    expected_header = b'\x82\x0a'
    self.assertEqual(
        mock_sock.sendall.call_args_list[1][0][0],
        expected_header + b'init_frame',
    )
    self.assertEqual(mock_read_frame.call_count, 2)
    mock_handle_msg.assert_called_once_with('msg1', state)
    self.assertTrue(mock_handler.close_connection)

  @mock.patch.object(websocket, '_perform_handshake', return_value=True)
  @mock.patch.object(websocket, '_read_frame', return_value=None)
  def test_handle_websocket_supersedes_old_connection(
      self, mock_read_frame, mock_handshake
  ):
    mock_old_sock = mock.create_autospec(socket.socket, instance=True)
    mock_new_sock = mock.create_autospec(socket.socket, instance=True)
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.request = mock_new_sock
    mock_handler.rfile = io.BytesIO()
    state = state_lib.PlaygroundState()
    state.set_active_ws(mock_old_sock)
    websocket.handle_websocket(mock_handler, state)
    mock_old_sock.shutdown.assert_called_once_with(socket.SHUT_RDWR)
    mock_old_sock.close.assert_called_once()
    mock_handshake.assert_called_once_with(mock_handler)
    mock_read_frame.assert_called_once()

  @mock.patch.object(websocket, '_perform_handshake', return_value=True)
  @mock.patch.object(websocket, '_read_frame')
  def test_handle_websocket_loop_exits_when_superseded(
      self, mock_read_frame, mock_handshake
  ):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.request = mock_sock
    mock_handler.rfile = io.BytesIO()
    state = state_lib.PlaygroundState()

    def change_state(*_):
      state.set_active_ws(mock.create_autospec(socket.socket, instance=True))
      return (1, b'dummy')

    mock_read_frame.side_effect = change_state
    websocket.handle_websocket(mock_handler, state)
    mock_read_frame.assert_called_once()
    self.assertIsNotNone(state.get_active_ws())
    self.assertNotEqual(state.get_active_ws(), mock_sock)
    mock_handshake.assert_called_once_with(mock_handler)

  @mock.patch.object(websocket, '_perform_handshake', return_value=False)
  def test_handle_websocket_handshake_fails(self, mock_handshake):
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    state = state_lib.PlaygroundState()
    websocket.handle_websocket(mock_handler, state)
    mock_handshake.assert_called_once_with(mock_handler)
    self.assertIsNone(state.get_active_ws())

  @mock.patch.object(websocket, '_perform_handshake', return_value=True)
  @mock.patch.object(websocket, '_read_frame', return_value=None)
  def test_handle_websocket_setsockopt_and_shutdown_oserror(
      self, mock_read_frame, mock_handshake
  ):
    mock_old_sock = mock.create_autospec(socket.socket, instance=True)
    mock_old_sock.shutdown.side_effect = OSError('shutdown failed')
    mock_new_sock = mock.create_autospec(socket.socket, instance=True)
    mock_new_sock.setsockopt.side_effect = OSError('nodelay failed')
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.request = mock_new_sock
    mock_handler.rfile = io.BytesIO()
    state = state_lib.PlaygroundState()
    state.set_active_ws(mock_old_sock)
    websocket.handle_websocket(mock_handler, state)
    mock_handshake.assert_called_once_with(mock_handler)
    mock_read_frame.assert_called_once()
    self.assertIsNone(state.get_active_ws())

  @mock.patch.object(websocket, '_perform_handshake', return_value=True)
  @mock.patch.object(websocket, '_read_frame')
  def test_handle_websocket_sends_logs_history_and_handles_unexpected_opcode(
      self, mock_read_frame, mock_handshake
  ):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.request = mock_sock
    mock_handler.rfile = io.BytesIO()
    state = state_lib.PlaygroundState()
    state.add_log({'message': 'hello log', 'level': 'INFO', 'timestamp': 100.0})
    mock_read_frame.side_effect = [
        (2, b'binary data'),  # unexpected opcode
        (8, b''),  # close frame
    ]
    websocket.handle_websocket(mock_handler, state)
    mock_handshake.assert_called_once_with(mock_handler)
    self.assertEqual(mock_read_frame.call_count, 2)

  @mock.patch.object(websocket, '_perform_handshake', return_value=True)
  @mock.patch.object(
      websocket, '_read_frame', side_effect=OSError('read error')
  )
  def test_handle_websocket_catches_read_error(
      self, mock_read_frame, mock_handshake
  ):
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    mock_handler = mock.create_autospec(
        http.server.BaseHTTPRequestHandler, instance=True
    )
    mock_handler.request = mock_sock
    mock_handler.rfile = io.BytesIO()
    state = state_lib.PlaygroundState()
    websocket.handle_websocket(mock_handler, state)
    mock_handshake.assert_called_once_with(mock_handler)
    mock_read_frame.assert_called_once()
    self.assertIsNone(state.get_active_ws())

  def test_try_send_status_persists_without_client(self):
    state = state_lib.PlaygroundState()
    websocket.try_send_status(state, 'Starting environment...')
    self.assertEqual(state.get_status(), 'Starting environment...')

  def test_try_send_logs(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock

    logs = [{'message': 'log1'}, {'message': 'log2'}]
    websocket.try_send_logs(state, logs)

    mock_sock.sendall.assert_called_once()
    sent_data = mock_sock.sendall.call_args[0][0]
    self.assertIn(b'log1', sent_data)
    self.assertIn(b'log2', sent_data)

  def test_try_send_stats_battery_power(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock

    stats = {
        'ack_latency': 10.0,
        'battery_power': {
            'level_percent': 85,
            'power_mw': 1500.0,
        },
    }
    websocket.try_send_stats(state, stats)

    mock_sock.sendall.assert_called_once()
    sent_data = mock_sock.sendall.call_args[0][0]
    self.assertIn(b'85', sent_data)
    self.assertIn(b'1500.0', sent_data)

  def test_build_ws_frame_boundaries(self):
    self.assertEqual(
        websocket._build_ws_frame(0x81, b'a' * 125)[:2], b'\x81\x7d'
    )
    self.assertEqual(
        websocket._build_ws_frame(0x81, b'a' * 126)[:4], b'\x81\x7e\x00\x7e'
    )
    self.assertEqual(
        websocket._build_ws_frame(0x81, b'a' * 65535)[:4], b'\x81\x7e\xff\xff'
    )
    self.assertEqual(
        websocket._build_ws_frame(0x81, b'a' * 65536)[:10],
        b'\x81\x7f\x00\x00\x00\x00\x00\x01\x00\x00',
    )

  def test_try_send_json_send_error_clears_active_ws(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    mock_sock.sendall.side_effect = OSError('broken pipe')
    state.active_ws = mock_sock

    websocket.try_send_status(state, 'Connected')

    self.assertIsNone(state.active_ws)
    self.assertEqual(state.get_status(), 'Connected')

  def test_try_send_adb_response(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock

    websocket.try_send_adb_response(
        state,
        command='shell wm size',
        status='OK',
        output='Physical size: 1080x1920',
        error='',
        duration_ms=4.5,
    )

    mock_sock.sendall.assert_called_once()
    sent_data = mock_sock.sendall.call_args[0][0]
    self.assertIn(b'adb_response', sent_data)
    self.assertIn(b'shell wm size', sent_data)
    self.assertIn(b'Physical size: 1080x1920', sent_data)

  def test_handle_message_reset(self):
    state = state_lib.PlaygroundState()
    self.assertFalse(state.get_reset())
    websocket._handle_message('reset', state)
    self.assertTrue(state.get_reset())

  def test_handle_message_adb(self):
    state = state_lib.PlaygroundState()
    websocket._handle_message('adb, shell dumpsys battery ', state)
    self.assertEqual(state.adb_queue.qsize(), 1)
    self.assertEqual(state.adb_queue.get(), 'shell dumpsys battery')

  def test_handle_message_adb_empty(self):
    state = state_lib.PlaygroundState()
    websocket._handle_message('adb,   ', state)
    self.assertTrue(state.adb_queue.empty())


if __name__ == '__main__':
  absltest.main()
