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

"""WebSocket handler for AndroidEnv Playground."""

import base64
import hashlib
import http.server
import json
import socket
import time
from typing import Any

from absl import logging
from android_env.playground import actions as actions_lib
from android_env.playground import state as state_lib


def _build_ws_frame(first_byte: int, payload: bytes) -> bytes:
  """Builds a WebSocket frame with the given first byte (FIN + opcode)."""
  length = len(payload)
  header = bytearray([first_byte])
  if length < 126:
    header.append(length)
  elif length < 65536:
    header.append(126)
    header.extend(length.to_bytes(2, byteorder='big'))
  else:
    header.append(127)
    header.extend(length.to_bytes(8, byteorder='big'))
  return bytes(header) + payload


def send_ws_binary_frame(sock: socket.socket, data: bytes):
  """Sends a binary WebSocket frame to the client."""
  # 0x82: FIN bit is set (0x80) to indicate this is the final fragment, and
  # opcode is set to 2 (0x02) for a binary frame.
  frame = _build_ws_frame(0x82, data)
  sock.sendall(frame)


def send_ws_text_frame(sock: socket.socket, data: str):
  """Sends a text WebSocket frame to the client."""
  # 0x81: FIN bit is set (0x80) and opcode is 1 (0x01) for text frame.
  frame = _build_ws_frame(0x81, data.encode('utf-8'))
  sock.sendall(frame)


def _try_send_json(state: state_lib.PlaygroundState, payload: dict[str, Any]):
  """Serializes payload as JSON and sends it to the active WebSocket client."""
  msg = json.dumps(payload)
  with state.active_ws_lock:
    ws_sock = state.active_ws
    if ws_sock is None:
      return
    try:
      send_ws_text_frame(ws_sock, msg)
    except OSError:
      state.active_ws = None


def try_send_status(state: state_lib.PlaygroundState, status_text: str):
  """Records and sends status text to the client."""
  state.set_status(status_text)
  _try_send_json(state, {'type': 'status', 'message': status_text})


def try_send_stats(state: state_lib.PlaygroundState, stats: dict[str, Any]):
  """Sends stats to the client."""
  _try_send_json(state, {'type': 'stats', 'stats': stats})


def try_send_logs(state: state_lib.PlaygroundState, logs: list[dict[str, Any]]):
  """Sends log history or real-time log entries to the client."""
  _try_send_json(state, {'type': 'logs', 'logs': logs})


def try_send_adb_response(
    state: state_lib.PlaygroundState,
    command: str,
    status: str,
    output: str,
    error: str = '',
    duration_ms: float = 0.0,
):
  """Sends an ADB command response to the client."""
  _try_send_json(
      state,
      {
          'type': 'adb_response',
          'command': command,
          'status': status,
          'output': output,
          'error': error,
          'duration_ms': duration_ms,
      },
  )


def try_send_frame(state: state_lib.PlaygroundState, jpeg_bytes: bytes):
  """Sends a frame if client is ready, enforcing backpressure."""
  ack_timed_out = False
  with state.active_ws_lock:
    if state.waiting_for_ack:
      if time.time() - state.last_frame_sent_time > 1.0:
        ack_timed_out = True
        state.waiting_for_ack = False
      else:
        return
    ws_sock = state.active_ws
    if ws_sock is None:
      return
    state.waiting_for_ack = True
    state.last_frame_sent_time = time.time()
    try:
      send_ws_binary_frame(ws_sock, jpeg_bytes)
    except OSError:
      state.active_ws = None
      state.waiting_for_ack = False

  if ack_timed_out:
    logging.warning('ACK timeout, resetting waiting_for_ack')


def _recvall(rfile, n: int) -> bytes | None:
  """Receives exactly n bytes from the rfile reader."""
  try:
    data = rfile.read(n)
    if len(data) < n:
      return None  # EOF or incomplete read
    return data
  except OSError:
    return None


def _perform_handshake(handler: http.server.BaseHTTPRequestHandler) -> bool:
  """Performs the WebSocket handshake.

  Args:
    handler: The HTTP request handler.

  Returns:
    True if handshake succeeded, False otherwise.
  """
  key = handler.headers.get('Sec-WebSocket-Key')
  if not key:
    handler.send_error(400, 'Missing Sec-WebSocket-Key')
    return False

  # Globally unique identifier (GUID) defined in RFC 6455 Sec 1.3 for the
  # WebSocket handshake. It is appended to the Sec-WebSocket-Key, SHA-1 hashed,
  # and base64 encoded to produce the Sec-WebSocket-Accept response header.
  guid = '258EAFA5-E914-47DA-95CA-C5AB0DC85B11'
  accept = base64.b64encode(
      hashlib.sha1((key + guid).encode('utf-8')).digest()
  ).decode('utf-8')

  # Send handshake response directly to bypass http.server header formatting
  response = (
      b'HTTP/1.1 101 Switching Protocols\r\n'
      b'Upgrade: websocket\r\n'
      b'Connection: Upgrade\r\n'
      b'Sec-WebSocket-Accept: '
      + accept.encode('utf-8')
      + b'\r\n\r\n'
  )
  try:
    handler.wfile.write(response)
    handler.wfile.flush()
    return True
  except OSError as e:
    logging.warning('Handshake write failed: %s', e)
    return False


def _read_frame(rfile) -> tuple[int, bytes] | None:
  """Reads a single WebSocket frame from the rfile reader.

  Args:
    rfile: The file-like object to read from.

  Returns:
    A tuple of (opcode, payload_bytes) if a frame was successfully read and
    parsed, or None on error or EOF.
  """
  # Byte 0 contains: FIN bit (1 bit), RSV1-3 (3 bits), Opcode (4 bits)
  header = _recvall(rfile, 2)
  if not header:
    return None

  fin_opcode = header[0]
  mask_payload = header[1]

  # Extract the 4-bit opcode (lower 4 bits of the first byte)
  opcode = fin_opcode & 0x0F

  has_mask = (mask_payload & 0x80) != 0
  if not has_mask:
    logging.warning('WebSocket received unmasked frame.')
    return None

  payload_len = mask_payload & 0x7F

  if payload_len == 126:
    len_bytes = _recvall(rfile, 2)
    if not len_bytes:
      return None
    payload_len = int.from_bytes(len_bytes, byteorder='big')
  elif payload_len == 127:
    len_bytes = _recvall(rfile, 8)
    if not len_bytes:
      return None
    payload_len = int.from_bytes(len_bytes, byteorder='big')

  mask_key = _recvall(rfile, 4)
  if not mask_key:
    return None

  payload = _recvall(rfile, payload_len)
  if payload is None:
    return None

  # Client-to-server frames MUST be masked. Unmask the payload by XORing
  # each byte with the corresponding byte of the 4-byte mask key (cycling).
  unmasked = bytearray(payload_len)
  for i in range(payload_len):
    unmasked[i] = payload[i] ^ mask_key[i % 4]

  return opcode, bytes(unmasked)


def _handle_message(msg: str, state: state_lib.PlaygroundState):
  """Handles a decoded WebSocket message."""
  if msg == 'ack':
    with state.active_ws_lock:
      state.waiting_for_ack = False
      ack_latency = (time.time() - state.last_frame_sent_time) * 1000
    logging.vlog(1, 'ACK received in %.2f ms', ack_latency)
    state.add_stat('ack_latency', ack_latency)
    return

  if msg == 'reset':
    logging.info('Received episode reset request.')
    state.set_reset()
    return

  if msg.startswith('adb,'):
    cmd = msg[4:].strip()
    if cmd:
      logging.info('Received ADB command request: %s', cmd)
      state.adb_queue.put(cmd)
    else:
      logging.warning('Received empty ADB command request.')
    return

  parts = msg.split(',')
  if len(parts) == 2 and parts[0] == 'load_task':
    task_id = parts[1].strip()
    if task_id:
      logging.info('Received reload task request for: %s', task_id)
      state.set_reload(task_id)
    else:
      logging.warning('Received load_task request with empty task_id.')
    return

  if parts[0] in ('touch_down', 'touch_move', 'touch_up') and len(parts) == 4:
    act_type, x_str, y_str, ts_str = parts
    recv_ts = time.time() * 1000
    try:
      x = float(x_str)
      y = float(y_str)
      client_ts = float(ts_str)
    except ValueError:
      logging.warning('Failed to parse %s message: %s', act_type, msg)
      return
    state.action_queue.put(
        actions_lib.ClientAction(
            action_type=act_type,
            x=x,
            y=y,
            client_timestamp_ms=client_ts,
            recv_timestamp_ms=recv_ts,
        )
    )
    return

  if parts[0] == 'text':
    recv_ts = time.time() * 1000
    prefix = 'text,'
    payload = msg[len(prefix) :]
    last_comma = payload.rfind(',')
    if last_comma != -1:
      text_str = payload[:last_comma]
      ts_str = payload[last_comma + 1 :]
      try:
        client_ts = float(ts_str)
      except ValueError:
        client_ts = recv_ts
      state.action_queue.put(
          actions_lib.ClientAction(
              action_type='text',
              x=0.0,
              y=0.0,
              client_timestamp_ms=client_ts,
              recv_timestamp_ms=recv_ts,
              text=text_str,
          )
      )
    return

  if parts[0] == 'keydown' and len(parts) == 3:
    recv_ts = time.time() * 1000
    try:
      keycode = int(parts[1])
      client_ts = float(parts[2])
      state.action_queue.put(
          actions_lib.ClientAction(
              action_type='keydown',
              x=0.0,
              y=0.0,
              client_timestamp_ms=client_ts,
              recv_timestamp_ms=recv_ts,
              keycode=keycode,
          )
      )
    except ValueError:
      logging.warning('Failed to parse keydown message: %s', msg)
    return

  if parts[0] == 'set_selection' and len(parts) == 4:
    recv_ts = time.time() * 1000
    try:
      start = int(parts[1])
      end = int(parts[2])
      client_ts = float(parts[3])
      state.action_queue.put(
          actions_lib.ClientAction(
              action_type='set_selection',
              x=0.0,
              y=0.0,
              client_timestamp_ms=client_ts,
              recv_timestamp_ms=recv_ts,
              selection=(start, end),
          )
      )
    except ValueError:
      logging.warning('Failed to parse set_selection message: %s', msg)
    return

  if parts[0] in ('cut', 'copy', 'paste') and len(parts) == 2:
    recv_ts = time.time() * 1000
    try:
      act_type = parts[0]
      client_ts = float(parts[1])
      state.action_queue.put(
          actions_lib.ClientAction(
              action_type=act_type,
              x=0.0,
              y=0.0,
              client_timestamp_ms=client_ts,
              recv_timestamp_ms=recv_ts,
          )
      )
    except ValueError:
      logging.warning('Failed to parse %s message: %s', parts[0], msg)
    return


def handle_websocket(
    handler: http.server.BaseHTTPRequestHandler,
    state: state_lib.PlaygroundState,
):
  """Handles a WebSocket handshake and frame reading loop."""
  if not _perform_handshake(handler):
    return

  sock = handler.request
  sock.setblocking(True)

  # Disable Nagle's algorithm for low latency
  try:
    sock.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
  except OSError as e:
    logging.warning('Failed to set TCP_NODELAY: %s', e)

  logging.info('WebSocket connection established')

  # Close any existing active connection to prevent multiple active clients.
  old_sock = state.get_active_ws()
  if old_sock and old_sock != sock:
    logging.info('Closing old connection')
    try:
      old_sock.shutdown(socket.SHUT_RDWR)
      old_sock.close()
    except OSError as e:
      logging.warning('Failed to close old socket: %s', e)

  state.set_active_ws(sock)
  with state.active_ws_lock:
    state.waiting_for_ack = False

  # Send current status if available
  current_status = state.get_status()
  if current_status is not None:
    try_send_status(state, current_status)

  # Send log history if available
  logs_history = state.get_logs()
  if logs_history:
    try_send_logs(state, logs_history)

  # Send initial frame if available to show current status/screen immediately
  with state.frame_lock:
    init_frame = state.current_frame
  if init_frame is not None:
    try_send_frame(state, init_frame)

  rfile = handler.rfile
  try:
    while state.running:
      # Ensure this thread is still handling the active connection.
      if state.get_active_ws() != sock:
        logging.info('Connection superseded, exiting loop.')
        break

      frame = _read_frame(rfile)
      if frame is None:
        break

      opcode, payload = frame
      if opcode == 8:  # Close frame
        logging.info('WebSocket close frame received')
        break

      if opcode == 1:  # Text frame
        msg = payload.decode('utf-8')
        _handle_message(msg, state)
      else:
        logging.warning('Unexpected WebSocket opcode: %d', opcode)

  except (OSError, UnicodeDecodeError, ValueError) as e:
    logging.warning('WebSocket error: %s', e)
  finally:
    logging.info('WebSocket connection closed')
    with state.active_ws_lock:
      if state.active_ws == sock:
        state.active_ws = None
        state.waiting_for_ack = False
