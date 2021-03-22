"""A class that talks directly to the telnet console of the Android emulator."""

import os
import telnetlib
import threading
import time
from typing import List, Optional
import uuid

from absl import logging
from android_env.components import errors
from android_env.proto import raw_observation_pb2

import numpy as np


class _FifoReader(threading.Thread):
  """A thread which reads from a Unix pipe.

  This thread is meant to run indefinitely, consuming from `fifo` and providing
  observations via `latest_observation()`.

  Any exceptions that are caught in `run()` are forwarded to
  `latest_exception()` and then execution is terminated.

  Users of this thread may call `stop()` to set a signal on
  `self._terminate_event`, which is checked periodically by this thread to end
  execution, but the `f.read()` call below may get stuck indefinitely causing
  this thread to block until the whole process is terminated. In this case, no
  CPU will be used, but a file descriptor will be consumed (from the `open()`
  call) and threading state will linger until the process dies.

  This thread was designed to terminate when facing possibly recoverable errors
  allowing its caller thread to time out when waiting on `data_ready()`, then
  optionally spawning a new thread to continue the work.
  """

  def __init__(self, fifo=str):
    super(_FifoReader, self).__init__()
    self._fifo = fifo
    self._latest_observation = None
    self._latest_exception = None
    self._data_ready = threading.Condition()
    self._terminate_event = threading.Event()

  def stop(self) -> None:
    self._terminate_event.set()

  def data_ready(self) -> threading.Condition:
    """Returns a condition variable that protects shared state."""
    return self._data_ready

  def latest_observation(self) -> List[np.ndarray]:
    return self._latest_observation

  def latest_exception(self) -> Exception:
    return self._latest_exception

  def run(self):
    while True:
      # Check if the caller thread asked this thread to stop running.
      if self._terminate_event.is_set():
        self._terminate_event.clear()
        return

      # Read the data from the pipe.
      raw_obs = None
      with open(self._fifo, 'rb') as f:
        data = []
        # Read data from the pipe in chunks.
        while True:
          # The call `f.read()` may block forever for all sorts of reasons, and
          # unfortunately Python does not allow specifying a timeout and there's
          # no good way to clean up this thread. When that occurs, the client of
          # this thread will timeout when reading from `output`.
          try:
            chunk = f.read()
          except Exception as e:  # pylint: disable=broad-except
            # It's nearly impossible to be exhaustive here so we use a generic
            # Exception to catch all errors, not only known ones such as IOError
            # and OSError,
            with self._data_ready:
              self._latest_exception = e
              self._data_ready.notify()
            return
          if not chunk:  # Writer closed the pipe.
            break
          data.append(chunk)

        data = b''.join(
            data)  # Joining is much faster than string concatenation.
        if not data:
          # Not having data here is abnormal, so terminate execution.
          with self._data_ready:
            self._latest_exception = errors.ObservationDecodingError(
                'No data from pipe.')
            self._data_ready.notify()
          return

        try:
          raw_obs = raw_observation_pb2.RawObservation.FromString(data)
          if (raw_obs.screen.height <= 0 or raw_obs.screen.width <= 0 or
              raw_obs.screen.num_channels <= 0):
            with self._data_ready:
              self._latest_exception = errors.ObservationDecodingError(
                  f'height: {raw_obs.screen.height} '
                  f'width: {raw_obs.screen.width} '
                  f'num_channels: {raw_obs.screen.num_channels} '
                  f'len(data): {len(data)}')
              self._data_ready.notify()
            return
        except:  # pylint: disable=bare-except
          with self._data_ready:
            self._latest_exception = errors.ObservationDecodingError(
                f'len(data): {len(data)}')
            self._data_ready.notify()
          return

      if not raw_obs:
        with self._data_ready:
          self._latest_exception = errors.ObservationDecodingError(
              f'No data in {self._fifo}')
          self._data_ready.notify()
        return

      screen = raw_obs.screen
      img = np.frombuffer(screen.data, dtype=np.uint8, count=len(screen.data))
      img.shape = (screen.height, screen.width, screen.num_channels)
      # Delete the 'Alpha' channel along the 'num_channels' axis
      img = np.delete(img, 3, 2)
      obs = [img, np.int64(raw_obs.timestamp_us)]
      with self._data_ready:
        self._latest_observation = obs
        self._data_ready.notify()


class EmulatorConsole():
  """Handles communication with the emulator."""

  def __init__(self,
               console_port: int,
               auth_code: str = '',
               tmp_dir: str = '/tmp',
               pipe_read_timeout_sec: float = 20.0):
    """Initializes this EmulatorConsole.

    Args:
      console_port: Integer
      auth_code: String
      tmp_dir: String
      pipe_read_timeout_sec: Maximum amount of time in seconds to wait for
          reading data from a pipe.
    """
    self._console_port = console_port
    self._tmp_dir = tmp_dir
    self._pipe_read_timeout_sec = pipe_read_timeout_sec
    self._read_thread = None
    self._setup_fifo()
    self._connect()
    self._authenticate_to_console(auth_code)

    self._read_thread = _FifoReader(fifo=self._fifo)
    self._read_thread.daemon = True
    self._read_thread.start()

  def close(self):
    self._connection.close()
    self._read_thread.stop()
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
    """
    # Ask the emulator for a screenshot.
    self._connection.write(b'screenrecord screenshot %s\n' %
                           self._fifo.encode('utf-8'))

    with self._read_thread.data_ready():
      # Check for outstanding errors before waiting.
      if self._read_thread.latest_exception():
        raise self._read_thread.latest_exception()

      if self._read_thread.data_ready().wait(
          timeout=self._pipe_read_timeout_sec):
        # Check for errors while reading observations.
        if self._read_thread.latest_exception():
          raise self._read_thread.latest_exception()

        # Check if the observation was successfully read.
        if self._read_thread.latest_observation():
          return self._read_thread.latest_observation()
        else:
          raise errors.ObservationDecodingError(
              'No observation from reader thread.')
      else:  # Timed out.
        # _read_fifo is stuck, so we spawn a new thread.
        self._read_thread = _FifoReader(fifo=self._fifo)
        self._read_thread.daemon = True
        self._read_thread.start()
        raise errors.PipeTimedOutError()

  def send_mouse_action(self, x: str, y: str, down: bool = True) -> None:
    """Sends mouse events via the emulator telnet console connection.

    This functionality is already available in the emulator and is relatively
    fast. It sends a "one-finger" touch event to the screen (i.e. it does not
    support multitouch).

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
