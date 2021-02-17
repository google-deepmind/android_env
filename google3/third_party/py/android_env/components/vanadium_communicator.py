"""A class that talks to the Vanadium VM running Android via ADB."""

import io
import os
from typing import Optional

from absl import logging
from android_env.components import adb_controller
from android_env.components import errors

import numpy as np
import pexpect
import PIL


_BIN_DIR = '/data/bin/'


class VanadiumCommunicator():
  """Handles communication with the VMM."""

  def __init__(
      self,
      adb_control_sendevent: adb_controller.AdbController,
      adb_control_screencap: adb_controller.AdbController,
      communication_binaries_path: str = '',
  ):

    self._adb_control_sendevent = adb_control_sendevent
    self._adb_control_sendevent.install_binary(
        os.path.join(communication_binaries_path, 'sendevents'), _BIN_DIR)
    self._adb_control_sendevent.sendevents(bin_dir=_BIN_DIR,
                                           target='/dev/input/event3')

    self._adb_control_screencap = adb_control_screencap
    self._adb_control_screencap.install_binary(
        os.path.join(communication_binaries_path, 'screencaps'), _BIN_DIR)
    self._adb_control_screencap.screencaps(bin_dir=_BIN_DIR)

    logging.info('Done initializing Vanadium communicator.')

  def fetch_screenshot(self) -> Optional[np.ndarray]:
    """Returns the observation using ADB shell."""
    success = False
    n_tries = 0
    max_tries = 3
    while not success and n_tries < max_tries:
      n_tries += 1
      if n_tries > 1:
        logging.info('fetch_screenshot try %d', n_tries)
      sendline_output = self._adb_control_screencap.fetch_screenshot()
      if not sendline_output:
        logging.error('No sendline output.')
        continue
      logging.log_every_n(logging.INFO, 'Sendline len: %d', 100,
                          len(sendline_output))
      screencap_output = sendline_output.replace(b'\r\n', b'\n')
      # Removing the first line return (echo from sendline).
      screencap_output = screencap_output[1:]
      try:
        img = PIL.Image.open(io.BytesIO(screencap_output))
        img = np.array(img)
        if img.ndim != 3 or img.shape[-1] < 3:
          logging.error('Image has a wrong shape %s.', str(img.shape))
          logging.error('Sendline output: %s', sendline_output)
          continue
        success = True
      except PIL.UnidentifiedImageError as e:
        logging.error(e)
        logging.error('Screencap output: %s', screencap_output)
        logging.error('Sendline output: %s', sendline_output)
        continue
    if not success:
      raise errors.ReadObservationError('Unable to fetch image.')
    return img[:, :, :3]

  def send_mouse_action(self, x: int, y: int, down: bool = True) -> None:
    """Sends mouse events.

    The linux input event is in the form of `device type code value`.
    The device with name 'remote-touchpad' handles touching on the screen.

    Currently this method handles events as follows:
    type            code                    value
    EV_ABS (0x03)   ABS_X (0x00)            x coordinate, min = 0, max = width
                    ABS_Y (0x01)            y coordinate, min = 0, max = height
    EV_KEY (0x01)   BTN_TOUCH (0x14a==330)  1 for down, 0 for up
    EV_SYN (0x00)   SYN_REPORT (0)          0 to synchronize

    Note that the sendevent command requires every input to be in decimal rather
    than hexadecimal.

    Args:
      x: Integer The absolute value for the x-coordinate.
      y: Integer The absolute value for the y-coordinate.
      down: Boolean Whether the button is down.
    Returns: None
    """
    if down:
      # If we are touching, we move first then touch (move will be drag if
      # previous action was also a touch)
      events = [
          '3,0,{}'.format(str(x)),  # x coordinate
          '3,1,{}'.format(str(y)),  # y coordinate
          '0,0,0',  # Synchronization
          '1,330,1',  # Touch screen
          '0,0,0',  # Synchronization
      ]
    else:
      # If we are lifting, we lift the finger first then change x,y
      events = [
          '1,330,0',  # Lift from screen
          '0,0,0',  # Synchronization
          '3,0,{}'.format(str(x)),  # x coordinate
          '3,1,{}'.format(str(y)),  # y coordinate
          '0,0,0',  # Synchronization
      ]
    event_str = os.linesep.join(events)
    try:
      self._adb_control_sendevent.send_mouse_event(event_str)
    except pexpect.exceptions.TIMEOUT as e:
      raise errors.SendActionError('Sendevent timed out: %s' % e)

  def close(self):
    logging.info('Closing communicator')
    self._adb_control_sendevent.close()
    self._adb_control_screencap.close()


# These methods do not work properly, but we keep them for reference while we
# compare options for communication.
#
#   def fetch_screenshot(self) -> Optional[np.ndarray]:
#     screenshot = self._vm.TakeScreenshotAsPNG()
#     img = Image.open(io.BytesIO(screenshot))
#     img = np.array(img)
#     logging.info('img shape: %r', img.shape)
#     return img
#
#   def send_mouse_action(self, x: int, y: int, down: bool = True):
#     """Send a mouse event to a scriptable head backend to the VM."""
#     motion_request = scripting_service_pb2.MouseEventRequest()
#     motion_request.event_type = (
#         scripting_service_pb2.MouseEventRequest.MOTION_ABSOLUTE)
#     motion_request.x_data = x
#     motion_request.y_data = y
#     self._vm.SendMouseEvent(motion_request)
#
#     button_request = scripting_service_pb2.MouseEventRequest()
#     if down:
#       button_request.event_type = (
#           scripting_service_pb2.MouseEventRequest.BUTTON_DOWN)
#     else:
#       button_request.event_type = (
#           scripting_service_pb2.MouseEventRequest.BUTTON_UP)
#    button_request.button = (
#        scripting_service_pb2.MouseEventRequest.BUTTON_LEFT)
#     self._vm.SendMouseEvent(button_request)
