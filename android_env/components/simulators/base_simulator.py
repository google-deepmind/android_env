# coding=utf-8
# Copyright 2021 DeepMind Technologies Limited.
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

"""A base class for talking to different types of Android simulators."""

import abc
from typing import Optional, List, Dict, Tuple

from absl import logging
from android_env.components import action_type as action_type_lib
from android_env.components import log_stream
from android_env.components import utils

import numpy as np


class BaseSimulator(metaclass=abc.ABCMeta):
  """An interface for communicating with an Android simulator."""

  def __init__(self,
               num_fingers: int = 1,
               show_touches: bool = True,
               show_pointer_location: bool = True,
               show_status_bar: bool = False,
               show_navigation_bar: bool = False,
               verbose_logs: bool = False):
    """Instantiates a BaseSimulator object.

    The simulator may be an emulator, virtual machine or even a physical device.

    Args:
      num_fingers: Number of virtual fingers of the agent.
      show_touches: Whether to show circles on the screen indicating the
        position of the current touch.
      show_pointer_location: Whether to show blue lines on the screen
        indicating the position of the current touch.
      show_status_bar: Whether or not to show the status bar (at the top of the
        screen, displays battery life, time, notifications etc.).
      show_navigation_bar: Whether or not to show the navigation bar (at the
        bottom of the screen, displayes BACK and HOME buttons, etc.)
      verbose_logs: If true, the log stream of the simulator will be verbose.
    """

    self._num_fingers = num_fingers
    self._show_touches = show_touches
    self._show_pointer_location = show_pointer_location
    self._show_status_bar = show_status_bar
    self._show_navigation_bar = show_navigation_bar
    self._verbose_logs = verbose_logs

    self._orientation = np.zeros(4, dtype=np.uint8)
    self._screen_dimensions = None
    self._last_obs_timestamp = 0
    self._launched = False
    self._adb_controller = None
    self._log_stream = None

  def num_fingers(self) -> int:
    return self._num_fingers

  def is_launched(self) -> bool:
    return self._launched

  @abc.abstractmethod
  def adb_device_name(self) -> str:
    """Returns the device name that the adb client will connect to."""
    pass

  @abc.abstractmethod
  def create_adb_controller(self):
    """Returns an ADB controller which can communicate with this simulator."""
    pass

  @abc.abstractmethod
  def _restart_impl(self) -> None:
    """Platform specific restart implementation."""
    pass

  @abc.abstractmethod
  def _launch_impl(self) -> None:
    """Platform specific launch implementation."""
    pass

  @abc.abstractmethod
  def send_action(self, action: Dict[str, np.ndarray]) -> None:
    """Sends the action to be executed to the simulator."""
    pass

  @abc.abstractmethod
  def _get_observation(self) -> Optional[List[np.ndarray]]:
    """Implementation of the Android observation.

    We expect the following items to be present in the output:
      [0] (image): Numpy array. The screenshot of the simulator. The numpy array
          has shape [height, width, num_channels] and can be loaded into PIL
          using Image.fromarray(img, mode='RGB') and be saved as a PNG file
          using my_pil.save('/tmp/my_screenshot.png', 'PNG').
      [1] (timedelta): np.int64 The number of microseconds since Unix Epoch.
    """
    pass

  @abc.abstractmethod
  def _create_log_stream(self) -> log_stream.LogStream:
    """Creates a stream of logs from the simulator."""
    pass

  def launch(self) -> None:
    """Launches the simulator."""
    if not self._launched:
      self._launched = True
      self._launch_impl()
      self._post_launch_setup()
    else:
      self.restart()

  def restart(self) -> None:
    """Restarts the simulator."""
    logging.info('Restarting the simulator...')
    self._adb_controller.close()
    self._restart_impl()
    self._post_launch_setup()
    logging.info('Done restarting the simulator.')

  def _post_launch_setup(self) -> None:
    """Performs necessary steps after the simulator has been launched."""
    self._screen_dimensions = np.array(
        self._adb_controller.get_screen_dimensions())
    self._adb_controller.set_touch_indicators(
        show_touches=self._show_touches,
        pointer_location=self._show_pointer_location)
    self._adb_controller.set_bar_visibility(
        navigation=self._show_navigation_bar,
        status=self._show_status_bar)
    self._log_stream = self._create_log_stream()

  def screen_dimensions(self) -> np.ndarray:
    """Returns the screen dimensions in pixels.

    IMPORTANT: This value is only valid after a successful launch() call.
    """
    if self._screen_dimensions is None:
      raise AssertionError('Screen dimension not available yet.')
    return self._screen_dimensions

  def update_device_orientation(self) -> None:
    """Updates the current device orientation."""

    # Skip fetching the orientation if we already have it.
    if not np.all(self._orientation == np.zeros(4)):
      logging.info('self._orientation already set, not setting it again')
      return

    orientation = self._adb_controller.get_orientation()
    if orientation not in {'0', '1', '2', '3'}:
      logging.error('Got bad orientation: %r', orientation)
      return

    # Transform into one-hot format.
    orientation_onehot = np.zeros([4], dtype=np.uint8)
    orientation_onehot[int(orientation)] = 1
    self._orientation = orientation_onehot

  def _prepare_action(
      self, action: Dict[str, np.ndarray]
  ) -> Tuple[int, int, bool]:
    """Turns an AndroidEnv action into values that the simulator can interpret.

    Converts float-valued 'touch_position' to integer coordinates corresponding
    to specific pixels, and 'action_type' to booleans indicating whether the
    screen is touched at said location or not. The result of this function can
    be sent directly to the underlying simulator (e.g. the Android Emulator,
    virtual machine, or a phone).

    Args:
      action: An action containing 'action_type' and 'touch_position'.
    Returns:
      A tuple with the format (x: int, y: int, down/up: bool).
    """
    is_touch = action['action_type'].item() == action_type_lib.ActionType.TOUCH
    touch_position = action['touch_position']
    touch_pixels = utils.touch_position_to_pixel_position(
        touch_position, width_height=self._screen_dimensions[::-1])
    return (touch_pixels[0], touch_pixels[1], is_touch)

  def _split_action(
      self, action: Dict[str, np.ndarray]) -> List[Dict[str, np.ndarray]]:
    """Splits a multitouch action into a list of single-touch actions."""

    single_touch_actions = [{
        'action_type': action['action_type'],
        'touch_position': action['touch_position'],
    }]
    for i in range(2, self._num_fingers + 1):
      single_touch_actions.append({
          'action_type': action[f'action_type_{i}'],
          'touch_position': action[f'touch_position_{i}'],
      })
    return single_touch_actions

  def get_observation(self) -> Dict[str, np.ndarray]:
    """Returns the environment observation.

    It calls the simulator implementation of _get_observation() and assembles
    the observation to be in the format expected by AndroidEnv, including
    passing a timestamp delta since the last observation (as opposed to the
    absolute timestamp) and appending the one-hot representation of the device
    orientation.
    """
    pixels, timestamp = self._get_observation()
    timestamp_delta = timestamp - self._last_obs_timestamp
    self._last_obs_timestamp = timestamp
    return {
        'pixels': pixels,
        'timedelta': timestamp_delta,
        'orientation': self._orientation
    }

  def close(self):
    self._adb_controller.close()

  def get_log_stream(self):
    return self._log_stream
