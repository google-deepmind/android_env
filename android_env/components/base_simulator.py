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
import tempfile
from typing import Optional, List, Dict, Tuple

from absl import logging
from android_env.components import action_type as action_type_lib
from android_env.components import adb_controller
from android_env.components import utils

import numpy as np


class BaseSimulator(metaclass=abc.ABCMeta):
  """An interface for communicating with an Android simulator."""

  def __init__(self,
               adb_path: str,
               adb_server_port: int,
               prompt_regex: str,
               tmp_dir: str = '/tmp',
               kvm_device: str = '/dev/kvm',
               show_touches: bool = True,
               show_pointer_location: bool = True,
               show_status_bar: bool = False,
               show_navigation_bar: bool = False):
    """Instantiates a BaseSimulator object.

    The simulator may be an emulator, virtual machine or even a physical device.

    Args:
      adb_path: Path to the adb binary.
      adb_server_port: Port for adb server.
      prompt_regex: Shell prompt for pexpect in ADB controller.
      tmp_dir: Directory for temporary files.
      kvm_device: Path to the KVM device.
      show_touches: Whether to show circles on the screen indicating the
        position of the current touch.
      show_pointer_location: Whether to show blue lines on the screen
        indicating the position of the current touch.
      show_status_bar: Whether or not to show the status bar (at the top of the
        screen, displays battery life, time, notifications etc.).
      show_navigation_bar: Whether or not to show the navigation bar (at the
        bottom of the screen, displayes BACK and HOME buttons, etc.)
    """

    self._adb_path = adb_path
    self._adb_server_port = adb_server_port
    self._prompt_regex = prompt_regex
    self._kvm_device = kvm_device
    self._show_touches = show_touches
    self._show_pointer_location = show_pointer_location
    self._show_status_bar = show_status_bar
    self._show_navigation_bar = show_navigation_bar

    self._local_tmp_dir_handle = tempfile.TemporaryDirectory(dir=tmp_dir)
    self._local_tmp_dir = self._local_tmp_dir_handle.name
    logging.info('Simulator local_tmp_dir: %s', self._local_tmp_dir)

    self._orientation = np.zeros(4, dtype=np.uint8)
    self._screen_dimensions = None
    self._last_obs_timestamp = 0
    self._launched = False

    # Initialize own ADB controller
    self._adb_controller = self.create_adb_controller()
    self._adb_controller.init_server()
    logging.info('Initialized simulator with ADB server port %r.',
                 self._adb_server_port)

  def is_launched(self):
    return self._launched

  @abc.abstractmethod
  def adb_device_name(self) -> str:
    """Returns the device name that the adb client will connect to."""
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

  def create_adb_controller(self):
    """Returns an ADB controller which can communicate with this simulator."""
    return adb_controller.AdbController(
        adb_path=self._adb_path,
        adb_server_port=self._adb_server_port,
        device_name=self.adb_device_name(),
        shell_prompt=self._prompt_regex)

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
    action_type = action['action_type'].item()
    if action_type == action_type_lib.ActionType.LIFT:
      return (0, 0, False)
    elif action_type == action_type_lib.ActionType.TOUCH:
      touch_position = action['touch_position']
      touch_pixels = utils.touch_position_to_pixel_position(
          touch_position, width_height=self._screen_dimensions[::-1])
      return (touch_pixels[0], touch_pixels[1], True)
    else:
      raise ValueError('Unexpected action_type: %r' % action_type)

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

