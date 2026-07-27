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

"""Task-Free AndroidDeviceEnv implementation connecting to on-device server."""

import time
from typing import Any, Self

from absl import logging
from android_env import env_interface
from android_env.components import action_type
from android_env.components import android_device
from android_env.components.specs import base_action_spec
from android_env.components.specs import base_observation_spec
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2
import dm_env
from dm_env import specs
import numpy as np


class AndroidDeviceEnv(env_interface.AndroidEnvInterface):
  """Task-Free AndroidDeviceEnv connected to a real device via WebSockets."""

  def __init__(self, device: android_device.AndroidDevice):
    """Initializes the AndroidDeviceEnv.

    Args:
      device: AndroidDevice handle instance.
    """
    self._device = device
    self._latest_observation_time = 0.0
    state = self._device.get_state()
    h, w = 1080, 1920
    for signal in state.signals:
      if (
          signal.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
          and signal.HasField('screenshot')
          and signal.screenshot.HasField('decoded')
      ):
        h = signal.screenshot.decoded.height or 1080
        w = signal.screenshot.decoded.width or 1920
        break
    self._pixel_shape = (h, w, 3)
    logging.info('Detected video resolution: %s', self._pixel_shape)

    self._active_signals = {
        device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
        device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE,
        device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS,
        device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
        device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS,
    }
    self._device.update_subscriptions(self._active_signals)
    self._latest_state = None
    self._latest_pixels = None
    self._is_touching = False
    self._last_touch_position = None
    self._last_non_touch_action = None

  def action_spec(self) -> dict[str, specs.Array]:
    return base_action_spec(num_fingers=1, enable_key_events=True)

  def observation_spec(self) -> dict[str, specs.Array]:
    return base_observation_spec(
        height=self._pixel_shape[0], width=self._pixel_shape[1]
    )

  def execute_adb_call(self, call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    """Executes an ADB call using the underlying AndroidDevice."""
    return self._device.execute_adb_call(call)

  def task_extras(self, latest_only: bool = True) -> dict[str, Any]:
    """Returns extras from the latest state signals."""
    extras: dict[str, Any] = {}
    if self._latest_state is not None:
      for sig in self._latest_state.signals:
        if sig.type == device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS:
          extras['logs'] = list(sig.system_logs.values)
        elif (
            sig.type
            == device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS
        ):
          extras['accessibility_events'] = list(sig.accessibility_events.events)
        elif (
            sig.type == device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
        ):
          extras['accessibility_tree'] = sig.accessibility_forest
    return extras

  def _build_observation(
      self, state: device_env_service_pb2.DeviceState, timedelta_us: int
  ) -> dict[str, Any]:
    pixels, active_package, audio, _ = self._parse_signals(state)
    if pixels is not None:
      self._latest_pixels = pixels
    else:
      pixels = (
          self._latest_pixels
          if self._latest_pixels is not None
          else np.zeros(self._pixel_shape, dtype=np.uint8)
      )

    orient_one_hot = np.zeros(4, dtype=np.uint8)
    orient_val = state.orientation
    if 0 <= orient_val < 4:
      orient_one_hot[orient_val] = 1
    else:
      orient_one_hot[0] = 1

    obs: dict[str, Any] = {
        'pixels': pixels,
        'timedelta': np.int64(timedelta_us),
        'active_package': active_package or '',
        'orientation': orient_one_hot,
    }
    if audio is not None:
      obs['audio'] = audio
    return obs

  def reset(self) -> dm_env.TimeStep:
    """Resets the environment."""
    logging.info('Resetting AndroidDeviceEnv...')
    self._latest_pixels = None
    self._latest_state = self._device.get_state()
    obs = self._build_observation(self._latest_state, timedelta_us=0)
    self._latest_observation_time = time.time()
    return dm_env.restart(obs)

  def step(self, action: dict[str, Any]) -> dm_env.TimeStep:
    """Takes a step in the environment by executing an action."""
    env_action_type = action.get('action_type')

    proto_action = device_env_service_pb2.Action()
    if env_action_type is not None:
      if env_action_type == action_type.ActionType.TOUCH:
        proto_action.action_type = device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
        pos = action.get('touch_position', [0.0, 0.0])
        proto_action.touch_position.x = float(pos[0])
        proto_action.touch_position.y = float(pos[1])
        self._is_touching = True
        self._last_touch_position = (float(pos[0]), float(pos[1]))
      elif env_action_type == action_type.ActionType.REPEAT:
        if self._is_touching:
          assert self._last_touch_position is not None
          proto_action.action_type = (
              device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE
          )
          proto_action.touch_position.x = self._last_touch_position[0]
          proto_action.touch_position.y = self._last_touch_position[1]
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
      self._device.send_action(proto_action)
    self._latest_state = self._device.get_state()

    now = time.time()
    timedelta_us = int((now - self._latest_observation_time) * 1e6)
    self._latest_observation_time = now

    obs = self._build_observation(self._latest_state, timedelta_us=timedelta_us)
    return dm_env.transition(reward=0.0, observation=obs)

  def _parse_signals(
      self, state: device_env_service_pb2.DeviceState | None
  ) -> tuple[
      np.ndarray | None,
      str | None,
      np.ndarray | None,
      list[str] | None,
  ]:
    if state is None:
      return None, None, None, None
    pixels = None
    active_package = None
    audio = None
    logs = None

    for sig in state.signals:
      if sig.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT:
        if sig.screenshot.HasField('decoded'):
          decoded = sig.screenshot.decoded
          pixels = np.frombuffer(decoded.raw_pixels, dtype=np.uint8).reshape(
              (decoded.height, decoded.width, 3)
          )
      elif sig.type == device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE:
        active_package = sig.active_package
      elif sig.type == device_env_service_pb2.DEVICE_SIGNAL_AUDIO_OUTPUT:
        raw_bytes = sig.audio_output.raw_bytes
        if raw_bytes:
          audio = np.frombuffer(raw_bytes, dtype=np.int16).reshape(-1, 2)
      elif sig.type == device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS:
        logs = list(sig.system_logs.values)

    return pixels, active_package, audio, logs

  def close(self) -> None:
    logging.info('Closing AndroidDeviceEnv...')
    self._device.close()

  def __enter__(self) -> Self:
    return self

  def __exit__(self, exc_type: Any, exc_value: Any, traceback: Any) -> None:
    self._device.__exit__(exc_type, exc_value, traceback)
