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

"""Task-Free AndroidEnv implementation connecting to on-device server."""

from collections.abc import Callable, Sequence
import time
from typing import Any
from absl import logging
from android_env import env_interface
from android_env.components import action_type
from android_env.components import device_connection
from android_env.proto import device_env_service_pb2
import dm_env
from dm_env import specs
import numpy as np


class AndroidDeviceEnv(env_interface.AndroidEnvInterface):
  """Task-Free AndroidEnv connected to a real device via WebSockets."""

  def __init__(
      self,
      connection: device_connection.DeviceConnection,
      on_close_callbacks: Sequence[Callable[[], None]] | None = None,
      on_error_callbacks: (
          Sequence[Callable[[Any, Any, Any], None]] | None
      ) = None,
  ):
    """Initializes the AndroidDeviceEnv.

    Args:
      connection: Connection to the on-device server.
      on_close_callbacks: Callbacks to run when close() is called. Callbacks
        must not raise exceptions.
      on_error_callbacks: Callbacks to run when exiting the context manager with
        an error. Callbacks must not raise exceptions.
    """
    self._connection = connection
    self._on_close_callbacks = on_close_callbacks or []
    self._on_error_callbacks = on_error_callbacks or []
    self._latest_observation_time = 0.0
    logging.info('Querying video stream metadata from device...')
    codec, w, h = self._connection.get_video_metadata()
    self._pixel_shape = (h, w, 3)
    logging.info('Detected video resolution: %s (%s)', self._pixel_shape, codec)

    self._active_signals = {
        device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
        device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE,
        device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS,
        device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
        device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS,
    }
    self._connection.update_subscriptions(self._active_signals)
    self._latest_state = None
    self._latest_pixels = None
    self._is_touching = False
    self._last_touch_position = None
    self._last_non_touch_action = None

  def action_spec(self) -> dict[str, specs.Array]:
    return {
        'action_type': specs.DiscreteArray(
            num_values=len(device_env_service_pb2.ActionType.DESCRIPTOR.values),
            name='action_type',
        ),
        'touch_position': specs.BoundedArray(
            shape=(2,),
            dtype=np.float32,
            minimum=[0.0, 0.0],
            maximum=[1.0, 1.0],
            name='touch_position',
        ),
    }

  def observation_spec(self) -> dict[str, specs.Array]:
    spec = {
        'pixels': specs.BoundedArray(
            shape=self._pixel_shape,
            dtype=np.uint8,
            minimum=0,
            maximum=255,
            name='pixels',
        ),
        'active_package': specs.Array(
            shape=(), dtype=object, name='active_package'
        ),
        'timedelta': specs.Array(shape=(), dtype=np.int64, name='timedelta'),
        'orientation': specs.BoundedArray(
            shape=np.array([4]),
            dtype=np.uint8,
            name='orientation',
            minimum=0,
            maximum=1,
        ),
    }
    if (
        device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT
        in self._active_signals
    ):
      spec['audio'] = specs.Array(shape=(0, 2), dtype=np.int16, name='audio')
    return spec

  def reset(self) -> dm_env.TimeStep:
    self._latest_state = self._connection.get_device_state()
    pixels, active_package, audio = self._parse_signals(self._latest_state)

    orientation = np.array([1, 0, 0, 0], dtype=np.uint8)  # Portrait default
    if self._latest_state:
      orientation_val = self._latest_state.orientation
      if 0 <= orientation_val < 4:
        orientation = np.zeros(4, dtype=np.uint8)
        orientation[orientation_val] = 1

    self._latest_observation_time = time.time()

    obs = {
        'pixels': pixels,
        'active_package': active_package,
        'timedelta': np.array(0, dtype=np.int64),
        'orientation': orientation,
    }
    if (
        device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT
        in self._active_signals
    ):
      audio = np.zeros((0, 2), dtype=np.int16)
      if self._latest_state:
        for sig in self._latest_state.signals:
          if sig.type == device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT:
            raw_bytes = sig.audio_output.raw_bytes
            if raw_bytes:
              audio = np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, 2)
            break
      obs['audio'] = audio
    return dm_env.restart(obs)

  def step(self, action: dict[str, np.ndarray]) -> dm_env.TimeStep:
    # Convert numpy action to proto Action
    env_action_type = action_type.ActionType(int(action['action_type']))
    proto_action = device_env_service_pb2.Action()

    if env_action_type == action_type.ActionType.REPEAT:
      if self._is_touching and self._last_touch_position is not None:
        proto_action.action_type = device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE
        proto_action.touch_position.x = self._last_touch_position[0]
        proto_action.touch_position.y = self._last_touch_position[1]
      elif self._last_non_touch_action is not None:
        proto_action.CopyFrom(self._last_non_touch_action)
      else:
        proto_action.action_type = (
            device_env_service_pb2.ACTION_TYPE_UNSPECIFIED
        )
    else:
      if env_action_type == action_type.ActionType.TOUCH:
        if self._is_touching:
          proto_action.action_type = (
              device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE
          )
        else:
          proto_action.action_type = (
              device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
          )
          self._is_touching = True
        if 'touch_position' in action:
          pos = action['touch_position']
          proto_action.touch_position.x = float(pos[0])
          proto_action.touch_position.y = float(pos[1])
          self._last_touch_position = (
              proto_action.touch_position.x,
              proto_action.touch_position.y,
          )
      elif env_action_type == action_type.ActionType.LIFT:
        proto_action.action_type = device_env_service_pb2.ACTION_TYPE_TOUCH_UP
        if 'touch_position' in action:
          pos = action['touch_position']
          proto_action.touch_position.x = float(pos[0])
          proto_action.touch_position.y = float(pos[1])
        elif self._last_touch_position is not None:
          proto_action.touch_position.x = self._last_touch_position[0]
          proto_action.touch_position.y = self._last_touch_position[1]
        self._is_touching = False
        self._last_touch_position = None
      elif env_action_type == action_type.ActionType.KEYDOWN:
        proto_action.action_type = device_env_service_pb2.ACTION_TYPE_KEY_EVENT
        if 'keycode' in action:
          proto_action.keycode = int(action['keycode'])
        self._last_non_touch_action = device_env_service_pb2.Action()
        self._last_non_touch_action.CopyFrom(proto_action)
      elif env_action_type == action_type.ActionType.KEYUP:
        proto_action.action_type = (
            device_env_service_pb2.ACTION_TYPE_UNSPECIFIED
        )
        self._last_non_touch_action = None
      else:
        proto_action.action_type = (
            device_env_service_pb2.ACTION_TYPE_UNSPECIFIED
        )

    if (
        proto_action.action_type
        != device_env_service_pb2.ACTION_TYPE_UNSPECIFIED
    ):
      self._connection.inject_action(proto_action)
    self._latest_state = self._connection.get_device_state()
    pixels, active_package, audio = self._parse_signals(self._latest_state)

    # Calculate timedelta
    now = time.time()
    timedelta_us = int((now - self._latest_observation_time) * 1e6)
    self._latest_observation_time = now

    orientation = np.array([1, 0, 0, 0], dtype=np.uint8)  # Portrait default
    if self._latest_state:
      orientation_val = self._latest_state.orientation
      if 0 <= orientation_val < 4:
        orientation = np.zeros(4, dtype=np.uint8)
        orientation[orientation_val] = 1

    obs = {
        'pixels': pixels,
        'active_package': active_package,
        'timedelta': np.array(timedelta_us, dtype=np.int64),
        'orientation': orientation,
    }
    if (
        device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT
        in self._active_signals
    ):
      obs['audio'] = audio

    return dm_env.transition(reward=0.0, observation=obs)

  def task_extras(self, latest_only: bool = True) -> dict[str, Any]:
    extras: dict[str, Any] = {
        'logs': [],
        'accessibility_events': [],
        'accessibility_tree': None,
    }
    if self._latest_state:
      for sig in self._latest_state.signals:
        if sig.type == device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS:
          extras['logs'].extend(sig.system_logs.values)
        elif (
            sig.type
            == device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS
        ):
          extras['accessibility_events'].extend(sig.accessibility_events.events)
          extras['accessibility_tree'] = sig.accessibility_forest
    return extras

  def _parse_signals(
      self, state: device_env_service_pb2.DeviceState | None
  ) -> tuple[np.ndarray, str, np.ndarray]:
    """Parses DeviceState in a single pass into (pixels, active_package, audio)."""
    if self._latest_pixels is None:
      self._latest_pixels = np.zeros(self._pixel_shape, dtype=np.uint8)

    pixels = self._latest_pixels
    active_package = ''
    audio = np.zeros((0, 2), dtype=np.int16)
    if not state:
      return pixels, active_package, audio

    has_screenshot_sub = (
        device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT in self._active_signals
    )

    for sig in state.signals:
      if (
          has_screenshot_sub
          and sig.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
          and sig.HasField('screenshot')
          and sig.screenshot.HasField('decoded')
      ):
        decoded = sig.screenshot.decoded
        self._latest_pixels = np.frombuffer(
            decoded.raw_pixels, dtype=np.uint8
        ).reshape((decoded.height, decoded.width, 3))
        pixels = self._latest_pixels
      elif sig.type == device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE:
        active_package = sig.active_package
      elif sig.type == device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT:
        raw_bytes = sig.audio_output.raw_bytes
        if raw_bytes:
          audio = np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, 2)

    return pixels, active_package, audio

  def close(self):
    logging.info('Closing AndroidDeviceEnv...')
    self._connection.close()
    for cb in self._on_close_callbacks:
      cb()

  def __enter__(self) -> 'AndroidDeviceEnv':
    return self

  def __exit__(self, exc_type, exc_value, traceback) -> None:
    if exc_type is not None:
      for cb in self._on_error_callbacks:
        cb(exc_type, exc_value, traceback)
    self.close()
