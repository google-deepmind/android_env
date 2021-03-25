"""A base class for talking to all sorts of Android simulators."""

import abc
import tempfile
from typing import Optional, List, Dict, Tuple

from absl import logging
from android_env.components import action_type
from android_env.components import adb_controller
from android_env.components import utils

import numpy as np


def _orientation_onehot(orientation: int) -> Optional[np.ndarray]:
  """Returns a one-hot representation of `orientation`."""
  orientation_onehot = np.zeros([4], dtype=np.uint8)
  orientation_onehot[orientation] = 1
  return orientation_onehot


class BaseSimulator(metaclass=abc.ABCMeta):
  """An interface for any Android simulator.

  The actual simulator may actually be an emulator, a virtual machines or even
  a physical phone.
  """

  def __init__(self,
               adb_path: str,
               adb_server_port: int,
               prompt_regex: str,
               tmp_dir: str = '/tmp',
               show_touches: bool = True,
               pointer_location: bool = True,
               show_status_bar: bool = False,
               show_navigation_bar: bool = False,
               kvm_device: str = '/dev/kvm'):

    self._adb_path = adb_path
    self._adb_server_port = adb_server_port
    self._prompt_regex = prompt_regex
    self._show_touches = show_touches
    self._pointer_location = pointer_location
    self._show_status_bar = show_status_bar
    self._show_navigation_bar = show_navigation_bar
    self._kvm_device = kvm_device

    self._local_tmp_dir_handle = tempfile.TemporaryDirectory(dir=tmp_dir)
    self._local_tmp_dir = self._local_tmp_dir_handle.name
    logging.info('Simulator local_tmp_dir: %s', self._local_tmp_dir)

    self._adb_controller = None
    self._orientation = np.zeros(4, dtype=np.uint8)
    self._screen_dimensions = None
    self._last_obs_timestamp = 0
    self._launched = False

    self._init_own_adb_controller()

    logging.info('Initialized simulator with ADB server port %r.',
                 self._adb_server_port)

  def is_launched(self):
    return self._launched

  @abc.abstractmethod
  def adb_device_name(self) -> str:
    """Returns the device name that the adb client will connect to."""
    raise NotImplementedError

  @abc.abstractmethod
  def send_action(self, action: Dict[str, np.ndarray]) -> None:
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
    return adb_controller.AdbController(
        adb_path=self._adb_path,
        adb_server_port=self._adb_server_port,
        device_name=self.adb_device_name(),
        shell_prompt=self._prompt_regex)

  def _base_post_launch_setup(self):
    self._set_device_screen_dimensions()
    self._last_action = (0, 0, False)
    self._adb_controller.set_touch_indicators(
        show_touches=self._show_touches,
        pointer_location=self._pointer_location)
    self._adb_controller.set_bar_visibility(
        navigation=self._show_navigation_bar, status=self._show_status_bar)

  def launch(self) -> None:
    """Public interface for actually launching this BaseSimulator."""
    if not self._launched:
      self._launched = True
      self._launch_impl()
      self._base_post_launch_setup()
    else:
      self.restart()

  def restart(self) -> None:
    """Restart the simulator."""
    logging.info('Restarting the simulator...')
    self._base_close()
    self._restart_impl()
    self._base_post_launch_setup()
    logging.info('Done restarting the simulator.')

  @property
  def screen_dimensions(self) -> np.ndarray:
    """Returns the screen dimensions in pixels.

    IMPORTANT: This property is only valid after a successful launch() call.
    """
    assert self._screen_dimensions is not None, (
        'Screen dimension not available yet.')
    return self._screen_dimensions

  def get_observation(self) -> Dict[str, np.ndarray]:
    """Returns the environment observation.

    It calls the simulator implementation of _get_observation() and assembles
    the observation to be in the format expected by AndroidEnv, including
    passing a timestamp delta since the last observation (as opposed to the
    absolute timestamp) and appending the one-hot representation of the device
    orientation.
    """
    obs = self._get_observation()
    timestamp = obs[1]
    timestamp_delta = timestamp - self._last_obs_timestamp
    self._last_obs_timestamp = timestamp
    return {
        'pixels': obs[0],
        'timedelta': timestamp_delta,
        'orientation': self._orientation
    }

  def update_device_orientation(self) -> None:
    """Updates the current device orientation."""
    logging.info('Updating device orientation...')

    # Skip fetching the orientation if we already have it.
    if not np.all(self._orientation == np.zeros(4)):
      logging.info('self._orientation already set, not setting it again')
      return

    orientation = self._adb_controller.get_orientation()
    int_orientation = {'0': 0, '1': 1, '2': 2, '3': 3}.get(orientation, None)
    if int_orientation is None:
      logging.error('Got bad orientation: %r', orientation)
      return

    self._orientation = _orientation_onehot(int_orientation)

  def _base_close(self):
    if self._adb_controller is not None:
      self._adb_controller.close()

  def close(self):
    self._base_close()

  def _init_own_adb_controller(self):
    if self._adb_controller is not None:
      self._adb_controller.close()
    self._adb_controller = self.create_adb_controller()
    # The adb server daemon must be up before launching the simulator.
    self._adb_controller.init_server()

  def _set_device_screen_dimensions(self):
    """Gets the (height, width)-tuple representing a screen size in pixels."""
    self._screen_dimensions = np.array(
        self._adb_controller.get_screen_dimensions())

  def _prepare_action(
      self, action: Dict[str, np.ndarray]
  ) -> Tuple[int, int, bool]:
    """Convert a float action to int coordinates.

    The result of this function can be sent directly to the underlying simulator
    (e.g. the Android Emulator, Vanadium or a phone).

    Args:
      action: The action provided by an agent. The expected format is:
          [[ActionType], [x: float, y: float]].

    Returns:
      A tuple with the format (x: int, y: int , down/up: bool).
    """
    act_type = action['action_type'].item()
    if act_type == action_type.ActionType.LIFT:
      return (0, 0, False)
    elif act_type == action_type.ActionType.TOUCH:
      touch_position = action['touch_position']
      touch_pixels = utils.touch_position_to_pixel_position(
          touch_position, width_height=self._screen_dimensions[::-1])
      return (touch_pixels[0], touch_pixels[1], True)
    else:
      assert False, 'Unexpected act_type: %r' % act_type
