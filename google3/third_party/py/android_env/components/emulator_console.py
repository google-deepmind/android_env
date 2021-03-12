"""A class that talks directly to the telnet console of the Android emulator."""

import os
import signal
import telnetlib
import time
from typing import List, Optional
import uuid

from absl import logging
from android_env.components import errors
from android_env.proto import raw_observation_pb2

import numpy as np


def _alarm_handler(signum: int, frame):
  """A handler for the SIGALRM UNIX signal."""
  del frame
  logging.error('SIGALRM handler called! signum: %r', signum)
  raise errors.PipeTimedOutError('Pipe timed out')


class EmulatorConsole():
  """Handles communication with the emulator."""

  def __init__(self,
               console_port: int,
               auth_code: str = '',
               tmp_dir: str = '/tmp'):
    """Initializes this EmulatorConsole.

    Args:
      console_port: Integer
      auth_code: String
      tmp_dir: String
    """
    self._console_port = console_port
    self._tmp_dir = tmp_dir
    self._setup_fifo()
    self._connect()
    self._authenticate_to_console(auth_code)
    signal.signal(signal.SIGALRM, _alarm_handler)

  def close(self):
    self._connection.close()
    if os.path.isfile(self._fifo):
      os.remove(self._fifo)

  def fetch_screenshot(self) -> Optional[List[np.ndarray]]:
    """Returns the observation via telnet through a pipe.

    This makes use of a feature in the AndroidEmulator
    (https://android-review.googlesource.com/c/platform/external/qemu/+/891716)
    that saves screenshots as a binary protobuf instead of a compressed PNG,
    greatly improving the performance and latency.

    Returns: Observation

    Raises:
      errors.ReadObservationError: if the observation could not be read.
      OSError: if any other problem occurs while reading the pipe.
    """
    # Ask the emulator for a screenshot.
    self._connection.write(b'screenrecord screenshot %s\n' %
                           self._fifo.encode('utf-8'))
    # Read the data from the pipe.
    raw_obs = None
    with open(self._fifo, 'rb') as f:
      data = []
      # Read data from the pipe in chunks.
      while True:
        # The call `f.read()` may block forever for all sorts of reasons, and
        # unfortunately Python does not allow specifying a timeout. We use the
        # SIGALRM Unix signal to transfer control to another section of the code
        # to unblock it after 5 seconds (which is orders of magnitude longer
        # than the expected time to read a chunk from the pipe).
        signal.alarm(5)
        chunk = f.read()
        signal.alarm(0)
        if not chunk:  # Writer closed the pipe.
          break
        data.append(chunk)
      data = b''.join(data)  # Joining is much faster than string concatenation.
      try:
        raw_obs = raw_observation_pb2.RawObservation.FromString(data)
        if (raw_obs.screen.height <= 0 or raw_obs.screen.width <= 0 or
            raw_obs.screen.num_channels <= 0):
          raise errors.ObservationDecodingError(
              f'height: {raw_obs.screen.height} width: {raw_obs.screen.width} '
              f'num_channels: {raw_obs.screen.num_channels} '
              f'len(data): {len(data)}')
      except:
        raise errors.ObservationDecodingError(f'len(data): {len(data)}')

    img = np.frombuffer(
        raw_obs.screen.data, dtype=np.uint8, count=len(raw_obs.screen.data))
    img = np.reshape(img, [
        raw_obs.screen.height, raw_obs.screen.width, raw_obs.screen.num_channels
    ])
    # Delete the 'Alpha' channel along the 'num_channels' axis
    img = np.delete(img, 3, 2)
    return [img, np.int64(raw_obs.timestamp_us)]

  def send_mouse_action(self, x: str, y: str, down: bool = True) -> None:
    """Sends mouse events via the emulator telnet console connection.

    This functionality is already available in the emulator and is relatively
    fast. It sends a "one-finger" touch event to the screen (i.e. it does not
    support multitouch).
    kenjitoyama@ encountered some strange behavior when sending everything
    at once without sleeping for a little while, where the emulator's input
    queue
    would fill up and lots of events would be dropped.

    Args:
      x: Integer The absolute value for the x-coordinate.
      y: Integer The absolute value for the y-coordinate.
      down: Boolean Whether the button is down.
    Returns: None
    """
    self._connection.write(
        ('event mouse %s %s 0 %s\n' %
         (int(x), int(y), '1' if down else '0')).encode('utf-8'))

  def _setup_fifo(self):
    """Creates a named pipe for receiving images from the console."""
    self._fifo = os.path.join(self._tmp_dir,
                              'screenshot_pipe-%s.pb' % uuid.uuid4())
    if os.path.isfile(self._fifo):  # Remove it before trying to make a new one.
      os.remove(self._fifo)

    # The following call may raise OSError if it can't create the FIFO, but we
    # do not want to catch it because it may hide other more serious errors.
    # Because we're executing this at the start of the server, we prefer to fail
    # fast and loud.
    os.mkfifo(self._fifo)

  def _connect(self):
    """Connects to the emulator console."""
    logging.info('Connecting to Emulator console on port %s...',
                 self._console_port)
    num_connection_attempts = 3
    connected = False
    retries = 0
    while not connected:
      try:
        self._connection = telnetlib.Telnet('localhost', self._console_port)
        connected = True
      except ConnectionRefusedError:
        retries += 1
        if retries >= num_connection_attempts:
          raise errors.ConsoleConnectionError()
        logging.error('Console connection refused, retrying in 5 seconds.')
        time.sleep(5)
    logging.info('Done connecting to Emulator console on port %s.',
                 self._console_port)

  def _authenticate_to_console(self, auth_code):
    logging.info('Authenticating to console.')
    if not auth_code:
      with open(os.path.expanduser('~/.emulator_console_auth_token')) as f:
        auth_code = f.read()
    self._connection.write(b'auth %s\n' %
                           auth_code.encode('utf-8'))  # Authenticate session.
    self._connection.read_until(b'OK', timeout=5)  # Look for 'OK' for 5s.
