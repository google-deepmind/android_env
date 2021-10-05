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

"""Fake Simulator for testing AndroidEnv infrastructure."""

import random
import threading
import time
from typing import Dict, List, Optional, Tuple

from absl import logging
from android_env.components import adb_controller
from android_env.components import log_stream
from android_env.components.simulators import base_simulator
import numpy as np


class FakeStream():
  """This class simulates the logs coming from ADB."""

  def __init__(self):
    self._values = [
        '',
        self._make_stdout('reward: 0.5'),
        self._make_stdout('reward: 1.0'),
        self._make_stdout('extra: my_extra: [1.0]'),
        self._make_stdout('episode end'),
    ]
    self._kill = False
    self._lock = threading.Lock()

  def _make_stdout(self, data):
    """Returns a valid log output with given data as message."""
    return f'         1553110400.424  5583  5658 D Tag: {data}'

  def kill(self):
    self._kill = True

  def __iter__(self):
    while True:
      if self._kill:
        return
      else:
        with self._lock:
          next_value = random.choices(
              self._values, weights=[0.49, 0.15, 0.15, 0.15, 0.01], k=1)[0]
          time.sleep(0.1)
        yield next_value


class FakeLogStream(log_stream.LogStream):
  """FakeLogStream class that wraps a FakeStream."""

  def __init__(self):
    self.stream = FakeStream()
    self.stream_is_alive = True
    self._verbose = False

  def _get_stream_output(self):
    return self.stream

  def stop_stream(self):
    self.stream_is_alive = False
    self.stream.kill()


class FakeAdbController(adb_controller.AdbController):
  """Fake adb controller for FakeSimulator."""

  def __init__(self,
               screen_dimensions: Tuple[int, int],
               fake_activity: str,
               *args, **kwargs):
    super().__init__(*args, **kwargs)
    self._screen_dimensions = screen_dimensions
    self._fake_activity = fake_activity

  def _execute_command(
      self,
      args: List[str],
      timeout: Optional[float] = None) -> Optional[bytes]:
    del args, timeout
    return bytes('fake output', 'utf-8')

  def _wait_for_device(
      self,
      max_tries: int = 20,
      sleep_time: float = 1.0,
      timeout: Optional[float] = None) -> None:
    """Fake adb controller does not have to wait for a device."""
    pass

  def get_screen_dimensions(
      self, timeout: Optional[float] = None) -> Tuple[int, int]:
    return self._screen_dimensions

  def get_current_activity(
      self, timeout: Optional[float] = None) -> Optional[str]:
    return self._fake_activity

  def is_package_installed(
      self, package_name: str, timeout: Optional[float] = None) -> bool:
    return True

  def start_screen_pinning(
      self, full_activity: str, timeout: Optional[float] = None):
    pass


class FakeSimulator(base_simulator.BaseSimulator):
  """FakeSimulator class."""

  def __init__(self,
               screen_dimensions: Tuple[int, int] = (480, 320),
               fake_activity: str = '',
               **kwargs):
    """FakeSimulator class that can replace EmulatorSimulator in AndroidEnv.

    Args:
      screen_dimensions: desired screen dimensions in pixels.
      fake_activity: if FakeSimulator is used in combination with a
        task_pb2.Task() that has an expected_activity, we can mock an
        activity here. If this activity does not match the expected_activity,
        an error will be raised.
      **kwargs: other keyword arguments for the base class.
    """
    super().__init__(**kwargs)
    self._screen_dimensions = screen_dimensions
    self._fake_activity = fake_activity
    self._adb_controller = self.create_adb_controller()
    logging.info('Created FakeSimulator.')

  def adb_device_name(self) -> str:
    return 'fake_simulator'

  def create_adb_controller(self):
    return FakeAdbController(
        screen_dimensions=self._screen_dimensions,
        fake_activity=self._fake_activity)

  def _restart_impl(self) -> None:
    pass

  def _launch_impl(self) -> None:
    pass

  def send_action(self, action: Dict[str, np.ndarray]) -> None:
    del action

  def _get_observation(self) -> Optional[List[np.ndarray]]:
    image = np.zeros(shape=(*self._screen_dimensions, 3), dtype=np.uint8)
    timestamp = np.random.randint(100, dtype=np.int64)
    return [image, timestamp]

  def _create_log_stream(self) -> log_stream.LogStream:
    return FakeLogStream()
