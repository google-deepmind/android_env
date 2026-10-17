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

"""Manages low-level WebSocket connection to the on-device server."""

import socket
import threading

from absl import logging
from android_env.components import config_classes
from android_env.proto import device_env_service_pb2
import websocket


class DeviceConnection:
  """Manages low-level WebSocket connection to the on-device AndroidEnv server."""

  def __init__(self, config: config_classes.DeviceConnectionConfig):
    self._config = config
    self._url = f'ws://{self._config.host}:{self._config.websocket_port}'
    self._ws = None
    self._state_lock = threading.Lock()
    self._state_condition = threading.Condition(self._state_lock)
    self._send_lock = threading.Lock()
    self._latest_state: device_env_service_pb2.DeviceState | None = None
    self._latest_error: str | None = None
    self._running = False
    self._reader_thread: threading.Thread | None = None
    self.connect()

  def connect(self) -> None:
    """Establishes connection to the on-device WebSocket server."""
    try:
      self._ws = websocket.create_connection(self._url)
    except (websocket.WebSocketException, socket.error) as e:
      raise RuntimeError(
          f'Failed to connect to WebSocket at {self._url}: {e}'
      ) from e

    self._running = True
    self._reader_thread = threading.Thread(
        target=self._receive_loop, daemon=True
    )
    self._reader_thread.start()

  def _receive_loop(self) -> None:
    """Background loop to continuously read incoming WebSocket messages."""
    while self._running and self._ws:
      try:
        resp_bytes = self._ws.recv()
        if resp_bytes is None or not self._running:
          continue
        resp = device_env_service_pb2.ServerMessage()
        resp.ParseFromString(resp_bytes)

        with self._state_condition:
          if resp.HasField('error'):
            self._latest_error = f'Server error: {resp.error.message}'
            self._latest_state = None
          elif resp.HasField('state'):
            self._latest_state = resp.state
            self._latest_error = None
          else:
            self._latest_error = 'Server response missing state'
            self._latest_state = None
          self._state_condition.notify_all()
      except (websocket.WebSocketException, socket.error, AttributeError):
        logging.warning('WebSocket connection closed or error encountered.')
        break
      except (ValueError, TypeError):
        logging.exception('Error decoding ServerMessage.')

  def close(self) -> None:
    """Closes the WebSocket connection."""
    self._running = False
    if self._ws:
      try:
        self._ws.close()
      except (websocket.WebSocketException, socket.error):
        pass
      self._ws = None

  def send_message(self, msg: device_env_service_pb2.ClientMessage) -> None:
    """Sends a binary ClientMessage to the on-device server."""
    if not self._ws:
      raise RuntimeError('Not connected')
    with self._send_lock:
      self._ws.send_binary(msg.SerializeToString())

  def get_device_state(self) -> device_env_service_pb2.DeviceState:
    """Returns the latest raw device state received from the server."""
    if not self._ws:
      raise RuntimeError('Not connected')

    with self._state_condition:
      if self._latest_state is None and self._latest_error is None:
        req = device_env_service_pb2.GetStateRequest()
        msg = device_env_service_pb2.ClientMessage(get_state=req)
        self.send_message(msg)
        self._state_condition.wait(timeout=5.0)
      if self._latest_error:
        raise RuntimeError(self._latest_error)
      if self._latest_state is None:
        raise RuntimeError('Timed out waiting for initial device state')
      return self._latest_state
