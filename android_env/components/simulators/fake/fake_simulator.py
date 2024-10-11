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

"""Fake Simulator for testing AndroidEnv infrastructure."""

import random
import threading
import time

from absl import logging
from android_env.components import adb_controller
from android_env.components import config_classes
from android_env.components import log_stream
from android_env.components.simulators import base_simulator
import numpy as np


class FakeStream:
  """This class simulates the logs coming from ADB."""

  def __init__(self):
    self._values = [
        '',
        self._make_stdout('reward: 0.5'),
        self._make_stdout('reward: 1.0'),
        self._make_stdout('extra: my_extra [1.0]'),
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
    super().__init__(verbose=False)
    self.stream = FakeStream()

  def _get_stream_output(self):
    return self.stream

  def stop_stream(self):
    self.stream.kill()


class FakeAdbController(adb_controller.AdbController):
  """Fake adb controller for FakeSimulator."""

  def execute_command(
      self,
      args: list[str],
      timeout: float | None = None,
      device_specific: bool = True,
  ) -> bytes:
    """Returns fake output for adb commands."""

    del timeout, device_specific

    # Fake "service is ready" output.
    if args[:3] == ['shell', 'service', 'check']:
      return f'Service {args[-1]}: found'.encode('utf-8')

    # Fake dumpsys output for getting orientation.
    if args == ['shell', 'dumpsys', 'input']:
      return b' SurfaceOrientation: 0'

    # app_screen_checker: fake_task expects 'fake_activity'.
    if args[:4] == ['shell', 'am', 'stack', 'list']:
      return (b'taskId=0 fake_activity visible=true '
              b'topActivity=ComponentInfo{fake_activity}')

    return b'fake output'


class FakeSimulator(base_simulator.BaseSimulator):
  """FakeSimulator class."""

  def __init__(self, config: config_classes.FakeSimulatorConfig):
    """FakeSimulator class that can replace EmulatorSimulator in AndroidEnv."""
    super().__init__(config)
    self._screen_dimensions = np.array(config.screen_dimensions)
    logging.info('Created FakeSimulator.')

  def get_logs(self) -> str:
    return 'FakeSimulator: fake logs'

  def adb_device_name(self) -> str:
    return 'fake_simulator'

  def create_adb_controller(self):
    return FakeAdbController(config_classes.AdbControllerConfig())

  def create_log_stream(self) -> log_stream.LogStream:
    return FakeLogStream()

  def _launch_impl(self) -> None:
    pass

  def send_touch(self, touches: list[tuple[int, int, bool, int]]) -> None:
    del touches

  def send_key(self, keycode: np.int32, event_type: str) -> None:
    del keycode, event_type

  def _get_screenshot_impl(self) -> np.ndarray:
    return np.random.randint(
        low=0, high=255, size=(*self._screen_dimensions, 3), dtype=np.uint8)
