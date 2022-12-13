# coding=utf-8
# Copyright 2022 DeepMind Technologies Limited.
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
from typing import List, Tuple

from absl import logging
from android_env.components import adb_controller
from android_env.components import errors
from android_env.components import log_stream
import numpy as np


def _print_logs_on_exception(func):
  """Decorator function for printing simulator logs upon any exception."""
  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except Exception as error:
      # Calls self.get_logs since self is the first arg.
      for line in args[0].get_logs().splitlines():
        logging.error(line)
      raise errors.SimulatorError(
          'Exception caught in simulator. Please see the simulator logs '
          'above for more details.') from error
  return wrapper


class BaseSimulator(metaclass=abc.ABCMeta):
  """An interface for communicating with an Android simulator."""

  def __init__(self, verbose_logs: bool = False):
    """Instantiates a BaseSimulator object.

    The simulator may be an emulator, virtual machine or even a physical device.
    Each simulator has its own AdbController that is used for internal
    bookkeeping.

    Args:
      verbose_logs: If true, the log stream of the simulator will be verbose.
    """

    self._verbose_logs = verbose_logs

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

  @_print_logs_on_exception
  def launch(self) -> None:
    """Starts the simulator."""

    self._num_launch_attempts += 1
    self._launch_impl()

  @abc.abstractmethod
  def _launch_impl(self) -> None:
    """Platform specific launch implementation."""

  @abc.abstractmethod
  def send_touch(self, touches: List[Tuple[int, int, bool, int]]) -> None:
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

  @abc.abstractmethod
  def save_or_load_local_snapshot(self) -> None:
    """Save or load from a snapshot."""

  @abc.abstractmethod
  def get_screenshot(self) -> np.ndarray:
    """Returns pixels representing the current screenshot of the simulator.

    The output numpy array should have shape [height, width, num_channels] and
    can be loaded into PIL using Image.fromarray(img, mode='RGB') and be saved
    as a PNG file using my_pil.save('/tmp/my_screenshot.png', 'PNG').
    """

  def close(self):
    """Frees up resources allocated by this object."""
