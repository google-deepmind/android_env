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

"""A base class for talking to different types of Android simulators."""

import abc
from collections.abc import Callable
import threading
import time

from absl import logging
from android_env.components import adb_controller
from android_env.components import config_classes
from android_env.components import errors
from android_env.components import log_stream
from android_env.proto import state_pb2
import numpy as np


class BaseSimulator(metaclass=abc.ABCMeta):
  """An interface for communicating with an Android simulator."""

  def __init__(self, config: config_classes.SimulatorConfig):
    """Instantiates a BaseSimulator object.

    The simulator may be an emulator, virtual machine or even a physical device.
    Each simulator has its own AdbController that is used for internal
    bookkeeping.

    Args:
      config: Settings for this simulator.
    """

    self._config = config
    self._interaction_thread: InteractionThread | None = None

    # An increasing number that tracks the attempt at launching the simulator.
    self._num_launch_attempts: int = 0

  def get_logs(self) -> str:
    """Returns logs recorded by the simulator (if provided)."""
    return 'No simulator logs provided.'

  @abc.abstractmethod
  def adb_device_name(self) -> str:
    """Returns the device name that the adb client will connect to."""

  @abc.abstractmethod
  def create_adb_controller(self) -> adb_controller.AdbController:
    """Returns an ADB controller which can communicate with this simulator."""

  @abc.abstractmethod
  def create_log_stream(self) -> log_stream.LogStream:
    """Creates a stream of logs from the simulator."""

  def launch(self) -> None:
    """Starts the simulator."""

    # Stop screenshot thread if it's enabled.
    if self._interaction_thread is not None:
      self._interaction_thread.stop()
      self._interaction_thread.join()

    self._num_launch_attempts += 1
    try:
      self._launch_impl()
    except Exception as error:
      for line in self.get_logs().splitlines():
        logging.error(line)
      raise errors.SimulatorError(
          'Exception caught in simulator. Please see the simulator logs '
          'above for more details.'
      ) from error

    # Start interaction thread.
    if self._config.interaction_rate_sec > 0:
      self._interaction_thread = InteractionThread(
          self._get_screenshot_impl, self._config.interaction_rate_sec
      )
      self._interaction_thread.start()

  @abc.abstractmethod
  def _launch_impl(self) -> None:
    """Platform specific launch implementation."""

  @abc.abstractmethod
  def send_touch(self, touches: list[tuple[int, int, bool, int]]) -> None:
    """Sends a touch event to be executed on the simulator.

    Args:
      touches: A list of touch events. Each element in the list corresponds to a
          single touch event. Each touch event tuple should have:
          0 x: The horizontal coordinate of this event.
          1 y: The vertical coordinate of this event.
          2 is_down: Whether the finger is touching or not the screen.
          3 identifier: Identifies a particular finger in a multitouch event.
    """

  @abc.abstractmethod
  def send_key(self, keycode: np.int32, event_type: str) -> None:
    """Sends a keyboard event.

    Args:
      keycode: Represents a specific keyboard key. This is platform and
        simulator-specific.
      event_type: Type of key event to be sent.
    """

  def load_state(
      self, request: state_pb2.LoadStateRequest
  ) -> state_pb2.LoadStateResponse:
    """Loads a state.

    Args:
      request: A `LoadStateRequest` containing any parameters necessary to
        specify how/what state to load.

    Returns:
      A `LoadStateResponse` containing the status, error message (if
      applicable), and any other relevant information.
    """
    raise NotImplementedError('This simulator does not support load_state()')

  def save_state(
      self, request: state_pb2.SaveStateRequest
  ) -> state_pb2.SaveStateResponse:
    """Saves a state.

    Args:
      request: A `SaveStateRequest` containing any parameters necessary to
        specify how/what state to save.

    Returns:
      A `SaveStateResponse` containing the status, error message (if
      applicable), and any other relevant information.
    """
    raise NotImplementedError('This simulator does not support save_state()')

  def get_screenshot(self) -> np.ndarray:
    """Returns pixels representing the current screenshot of the simulator."""

    if self._config.interaction_rate_sec > 0:
      assert self._interaction_thread is not None
      return self._interaction_thread.screenshot()  # Async mode.
    else:
      return self._get_screenshot_impl()  # Sync mode.

  @abc.abstractmethod
  def _get_screenshot_impl(self) -> np.ndarray:
    """Actual implementation of `get_screenshot()`.

    The output numpy array should have shape [height, width, num_channels] and
    can be loaded into PIL using Image.fromarray(img, mode='RGB') and be saved
    as a PNG file using my_pil.save('/tmp/my_screenshot.png', 'PNG').
    """

  def close(self):
    """Frees up resources allocated by this object."""

    if self._interaction_thread is not None:
      self._interaction_thread.stop()
      self._interaction_thread.join()


class InteractionThread(threading.Thread):
  """A thread that gets screenshot in the background."""

  def __init__(
      self,
      get_screenshot_fn: Callable[[], np.ndarray],
      interaction_rate_sec: float,
  ):
    super().__init__()
    self._get_screenshot_fn = get_screenshot_fn
    self._interaction_rate_sec = interaction_rate_sec
    self._should_stop = threading.Event()
    self._screenshot = self._get_screenshot_fn()

  def run(self):
    last_read = time.time()
    while not self._should_stop.is_set():
      self._screenshot = self._get_screenshot_fn()
      now = time.time()
      elapsed = now - last_read
      last_read = now
      sleep_time = self._interaction_rate_sec - elapsed
      if sleep_time > 0.0:
        time.sleep(sleep_time)
    logging.info('InteractionThread.run() finished.')

  def stop(self):
    logging.info('Stopping InteractionThread.')
    self._should_stop.set()

  def screenshot(self) -> np.ndarray:
    return self._screenshot
