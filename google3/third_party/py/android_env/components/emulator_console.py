"""A class that talks directly to the telnet console of the Android emulator."""

import os
import select
import telnetlib
import time
from typing import List, Optional
import uuid

from absl import logging
from android_env.components import errors
from android_env.proto import raw_observation_pb2

import numpy as np


class EmulatorConsole():
  """Handles communication with the emulator."""

  def __init__(self, console_port: int, auth_code: str, tmp_dir: str = '/tmp'):
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

  def close(self):
    self._connection.close()
    if self._pipe is not None:  # Close the pipe if it was open.
      os.close(self._pipe)
    if os.path.isfile(self._fifo):
      os.remove(self._fifo)

  def fetch_screenshot(self) -> Optional[List[np.ndarray]]:
    """Returns the observation using the telnet output pixels.

    This functionality is not present in the current emulator code. kenjitoyama@
    has a local git repo with the necessary modification. We eventually will
    push
    something like this to the emulator open source code, but it is not a
    priority
    now.

    This is much faster than fetching from the saved PNG file above and we
    expect
    a latency of around 3ms.

    Returns: Observation

    Raises:
      errors.ReadObservationError: if the observation could not be read.
      OSError: if any other problem occurs while reading the pipe.
    """
    # Ask the emulator for a screenshot.
    self._connection.write(b'screenrecord screenshot %s\n' %
                           self._fifo.encode('utf-8'))
    # Read the data from the pipe.
    encoded_obs = b''
    if self._pipe is None:
      self._pipe = os.open(self._fifo, os.O_RDONLY)

    start_time = time.time()
    timeout_sec = 5.0
    data = None
    while True:
      try:
        # Wait for up to 1 second for `pipe` to be ready to read, and then read
        # up to 2**17 bytes, which is a bit above the maximum when reading from
        # a pipe in linux (around 69k bytes, which is > 2**16).
        # If the pipe is still empty after 5 secs, something is wrong and we
        # raise an error.
        # NOTE: This timeout introduces a delay of around 20% on this os.read()
        #       call. As of 2019.06.05 in local benchmarks it was observed that
        #       this extra select() call increases the latency from ~1.8ms to
        #       ~1.5ms. We deemed this cost small for the added protection.
        r, _, _ = select.select([self._pipe], [], [], 1.0)
        if self._pipe in r:
          data = os.read(self._pipe, int(2**17))
      except OSError as err:
        raise err
      if data:
        encoded_obs += data
      elif time.time() - start_time > timeout_sec:
        logging.error('Timed out on reading observation.')
        # The pipe stayed empty passed the timeout time.
        raise errors.PipeTimedOutError()
      else:
        if encoded_obs:
          # We are done reading. Exiting the loop.
          break

    try:
      raw_obs = raw_observation_pb2.RawObservation.FromString(encoded_obs)
    except:
      raise errors.ObservationDecodingError()
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

    # The pipe to read in fetch_observation().
    self._pipe = None

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
