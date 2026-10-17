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

"""First-class ergonomic handle to an Android device or emulator."""

from collections.abc import Callable, Sequence
import time
from typing import Any, Self

from absl import logging
from android_env.components import adb_call_parser as adb_parser
from android_env.components import device_connection
from android_env.components import errors
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2
import cv2
import numpy as np


class AndroidDevice:
  """Ergonomic handle to an Android device running the Core on-device server."""

  def __init__(
      self,
      connection: device_connection.DeviceConnection,
      adb_call_parser: adb_parser.AdbCallParser | None = None,
      on_close_callbacks: Sequence[Callable[[], None]] | None = None,
      on_error_callbacks: (
          Sequence[Callable[[Any, Any, Any], None]] | None
      ) = None,
  ):
    """Initializes the AndroidDevice handle.

    Args:
      connection: Low-level WebSocket transport connection to the device.
      adb_call_parser: Optional AdbCallParser instance for ADB calls.
      on_close_callbacks: Callbacks executed when close() is called.
      on_error_callbacks: Callbacks executed when exiting context manager with
        an error.
    """
    self._connection = connection
    self._adb_call_parser = adb_call_parser
    self._on_close_callbacks = list(on_close_callbacks or [])
    self._on_error_callbacks = list(on_error_callbacks or [])
    self._clock_offset_ms = 0
    self._sync_clock()

  def execute_adb_call(self, call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    """Executes an AdbRequest using the device's AdbCallParser."""
    if self._adb_call_parser is None:
      raise errors.AdbControllerError('ADB is not configured for this device.')
    return self._adb_call_parser.parse(call)

  def get_state(self) -> device_env_service_pb2.DeviceState:
    """Returns the latest device state (telemetry signals, decoded screenshot, etc.)."""
    state = self._connection.get_device_state()
    self._decode_screenshot_signals(state)
    return state

  def send_action(self, action: device_env_service_pb2.Action) -> None:
    """Sends an action (touch, key event, etc.) to the device."""
    req = device_env_service_pb2.InjectActionRequest(action=action)
    msg = device_env_service_pb2.ClientMessage(inject_action=req)
    self._connection.send_message(msg)

  def update_subscriptions(
      self, active_signals: set[device_env_service_pb2.DeviceSignal]
  ) -> None:
    """Updates active telemetry signal subscriptions on the device."""
    req = device_env_service_pb2.UpdateSubscriptionsRequest()
    req.active_signals.extend(active_signals)
    msg = device_env_service_pb2.ClientMessage(update_subscriptions=req)
    self._connection.send_message(msg)

  def close(self) -> None:
    """Closes the connection and runs all cleanup callbacks."""
    logging.info('Closing AndroidDevice...')
    self._connection.close()
    for cb in self._on_close_callbacks:
      cb()

  def __enter__(self) -> Self:
    return self

  def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
    if exc_type is not None:
      for cb in self._on_error_callbacks:
        cb(exc_type, exc_value, traceback)
    self.close()

  def _decode_screenshot_signals(
      self, state: device_env_service_pb2.DeviceState
  ) -> None:
    """Decodes compressed screenshot bytes into in-place decoded pixels."""
    for signal in state.signals:
      if (
          signal.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
          and signal.HasField('screenshot')
          and signal.screenshot.encoded_bytes
      ):
        img_bytes = signal.screenshot.encoded_bytes
        img_arr = np.frombuffer(img_bytes, dtype=np.uint8)
        frame = cv2.imdecode(img_arr, cv2.IMREAD_COLOR)
        if frame is not None:
          rgb_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
          h, w, _ = rgb_frame.shape
          signal.screenshot.decoded.raw_pixels = rgb_frame.tobytes()
          signal.screenshot.decoded.width = w
          signal.screenshot.decoded.height = h
        break

  def _sync_clock(self) -> None:
    """Synchronizes device wall clock offset."""
    t0 = time.time_ns() // 1_000_000
    try:
      state = self._connection.get_device_state()
    except (RuntimeError, ValueError) as e:
      logging.warning('Clock sync skipped: %s', e)
      return

    t1 = time.time_ns() // 1_000_000
    rtt = t1 - t0
    settings = self._get_device_settings(state)
    device_time_str = settings.get('device_time_ms')
    if device_time_str:
      t_device = int(device_time_str)
      self._clock_offset_ms = t_device - (t0 + rtt // 2)
      logging.info(
          'Clock sync: RTT=%dms, offset=%dms', rtt, self._clock_offset_ms
      )

  def _get_device_settings(
      self, state: device_env_service_pb2.DeviceState
  ) -> dict[str, str]:
    for signal in state.signals:
      if signal.type == device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS:
        return dict(signal.device_settings.entries)
    return {}
