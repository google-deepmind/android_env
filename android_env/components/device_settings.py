# coding=utf-8
# Copyright 2024 DeepMind Technologies Limited.
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

"""Sets and gets some global settings on an Android device."""

from typing import Final
from unittest import mock

from absl import logging
from android_env.components import adb_call_parser
from android_env.components import config_classes
from android_env.components.simulators import base_simulator
from android_env.proto import adb_pb2
import numpy as np


# The internal `AdbCallParser` instance is lazily instantiated within
# `DeviceSettings`. If we make it optional (i.e. `| None`), pytype will think
# that it could be `None`, requiring either explicit runtime checks or escape
# hatches in every actual call, even if it's never actually `None` if reached
# via the public API.
# The trick here is to create this dummy instance of the right type that's used
# as a sentinel to indicate that it hasn't been initialized yet.
_PLACEHOLDER_ADB_CALL_PARSER: Final[adb_call_parser.AdbCallParser] = (
    mock.create_autospec(adb_call_parser.AdbCallParser)
)


class DeviceSettings:
  """An abstraction for general properties and settings of an Android device."""

  def __init__(self, simulator: base_simulator.BaseSimulator):
    self._simulator = simulator
    self._adb_call_parser = _PLACEHOLDER_ADB_CALL_PARSER

    # The size of the device screen in pixels.
    self._screen_width: int = 0
    self._screen_height: int = 0
    # The device orientation.
    self._orientation = np.zeros(4, dtype=np.uint8)

  def update(self, config: config_classes.DeviceSettingsConfig) -> None:
    """Sets the configuration of the device according to `config`."""

    if self._adb_call_parser is _PLACEHOLDER_ADB_CALL_PARSER:
      self._adb_call_parser = adb_call_parser.AdbCallParser(
          adb_controller=self._simulator.create_adb_controller()
      )

    self._update_screen_size()
    self._set_show_touches(config.show_touches)
    self._set_show_pointer_location(config.show_pointer_location)
    self._set_status_navigation_bars(
        config.show_navigation_bar, config.show_status_bar
    )

  def screen_width(self) -> int:
    """The screen width in pixels. Only valid after `update()` is called."""

    return self._screen_width

  def screen_height(self) -> int:
    """The screen height in pixels. Only valid after `update()` is called."""

    return self._screen_height

  def get_orientation(self) -> np.ndarray:
    """Returns the device orientation. Please see specs.py for details."""

    if self._adb_call_parser is _PLACEHOLDER_ADB_CALL_PARSER:
      self._adb_call_parser = adb_call_parser.AdbCallParser(
          adb_controller=self._simulator.create_adb_controller()
      )

    self._update_orientation()
    return self._orientation

  def _update_screen_size(self) -> None:
    """Sets the screen size from a screenshot ignoring the color channel."""

    screenshot = self._simulator.get_screenshot()
    self._screen_height = screenshot.shape[0]
    self._screen_width = screenshot.shape[1]

  def _set_show_touches(self, show: bool) -> None:
    """Whether to display circles indicating the touch position."""

    self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='show_touches', value='1' if show else '0'
                ),
            )
        )
    )

  def _set_show_pointer_location(self, show: bool) -> None:
    """Whether to display blue lines on the screen indicating touch position."""

    self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='pointer_location', value='1' if show else '0'
                ),
            )
        )
    )

  def _set_status_navigation_bars(
      self, show_navigation: bool, show_status: bool
  ) -> None:
    """Whether to display the status (top) and navigation (bottom) bars."""

    if show_navigation and show_status:
      policy_control_value = 'null*'
    elif show_navigation and not show_status:
      policy_control_value = 'immersive.status=*'
    elif not show_navigation and show_status:
      policy_control_value = 'immersive.navigation=*'
    else:
      policy_control_value = 'immersive.full=*'

    self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='policy_control', value=policy_control_value
                ),
            )
        )
    )

  def _update_orientation(self) -> None:
    """Updates the current device orientation."""

    # Skip fetching the orientation if we already have it.
    if not np.all(self._orientation == np.zeros(4)):
      return

    orientation_response = self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            get_orientation=adb_pb2.AdbRequest.GetOrientationRequest()
        )
    )
    if orientation_response.status != adb_pb2.AdbResponse.Status.OK:
      logging.error('Got bad orientation: %r', orientation_response)
      return

    orientation = orientation_response.get_orientation.orientation
    if orientation not in {0, 1, 2, 3}:
      logging.error('Got bad orientation: %r', orientation)
      return

    # Transform into one-hot format.
    orientation_onehot = np.zeros([4], dtype=np.uint8)
    orientation_onehot[orientation] = 1
    self._orientation = orientation_onehot
