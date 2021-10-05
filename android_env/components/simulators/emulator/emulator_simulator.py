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

"""A class that manages an Android Emulator."""

import functools
import tempfile
from typing import Any, Dict, List, Optional

from absl import logging
from android_env.components import adb_controller
from android_env.components import adb_log_stream
from android_env.components import errors
from android_env.components import log_stream
from android_env.components.simulators import base_simulator
from android_env.components.simulators.emulator import emulator_launcher
import numpy as np
import portpicker

from android_env.proto import emulator_controller_pb2


def is_existing_emulator_provided(launcher_args: Dict[str, Any]) -> bool:
  """Returns true if all necessary args were provided."""
  return bool(launcher_args.get('adb_port') and
              launcher_args.get('emulator_console_port') and
              launcher_args.get('grpc_port'))


class EmulatorSimulator(base_simulator.BaseSimulator):
  """Controls an Android Emulator."""

  def __init__(self,
               emulator_launcher_args: Dict[str, Any],
               adb_controller_args: Dict[str, Any],
               tmp_dir: Optional[str] = None,
               **kwargs):

    # If adb_port, console_port and grpc_port are all already provided,
    # we assume the emulator already exists and there's no need to launch.
    if is_existing_emulator_provided(emulator_launcher_args):
      self._existing_emulator_provided = True
      self._adb_port = emulator_launcher_args['adb_port']
      self._console_port = emulator_launcher_args['emulator_console_port']
      self._grpc_port = emulator_launcher_args['grpc_port']
      logging.info('Connecting to existing emulator "%r"', self._adb_port)
    else:
      self._existing_emulator_provided = False
      self._adb_port = portpicker.pick_unused_port()
      self._console_port = portpicker.pick_unused_port()
      self._grpc_port = portpicker.pick_unused_port()

    self._emulator_stub = None
    self._image_format = None

    super().__init__(**kwargs)

    # Create directory for tmp files.
    self._tmp_dir = tmp_dir or tempfile.gettempdir()
    self._local_tmp_dir_handle = tempfile.TemporaryDirectory(dir=self._tmp_dir)
    self._local_tmp_dir = self._local_tmp_dir_handle.name
    logging.info('Simulator local_tmp_dir: %s', self._local_tmp_dir)

    # Initialize own ADB controller
    self._adb_controller_args = adb_controller_args
    self._adb_controller = self.create_adb_controller()
    self._adb_controller.init_server()
    logging.info('Initialized simulator with ADB server port %r.',
                 self._adb_controller_args['adb_server_port'])

    # Create EmulatorLauncher.
    emulator_launcher_args.update({
        'adb_port': self._adb_port,
        'adb_server_port': self._adb_controller_args['adb_server_port'],
        'emulator_console_port': self._console_port,
        'local_tmp_dir': self._local_tmp_dir,
        'grpc_port': self._grpc_port,
    })
    logging.info('emulator_launcher_args: %r', emulator_launcher_args)
    if not self._existing_emulator_provided:
      self._launcher = emulator_launcher.EmulatorLauncher(
          **emulator_launcher_args)
      self._get_emulator_stub = self._launcher.get_emulator_stub
    else:
      self._get_emulator_stub = functools.partial(
          emulator_launcher.EmulatorLauncher.create_emulator_stub,
          grpc_port=self._grpc_port)

  def adb_device_name(self) -> str:
    return 'emulator-%s' % (self._adb_port - 1)

  def create_adb_controller(self):
    """Returns an ADB controller which can communicate with this simulator."""
    return adb_controller.AdbController(
        device_name=self.adb_device_name(),
        **self._adb_controller_args)

  def _restart_impl(self) -> None:
    if not self._existing_emulator_provided:
      self._launcher.restart()

  def _launch_impl(self) -> None:
    try:
      if not self._existing_emulator_provided:
        self._launcher.launch()
    except errors.SimulatorCrashError:
      # If the simulator crashes on the initial launch, we try to restart once.
      self.restart()

  def _post_launch_setup(self):
    super()._post_launch_setup()
    self._emulator_stub = self._get_emulator_stub()
    self._image_format = emulator_controller_pb2.ImageFormat(
        format=emulator_controller_pb2.ImageFormat.ImgFormat.RGB888,
        height=self._screen_dimensions[0],
        width=self._screen_dimensions[1],
    )

  def send_action(self, action: Dict[str, np.ndarray]) -> None:
    """Sends touch events to the emulator."""
    assert self._emulator_stub, 'Emulator stub has not been initialized yet.'
    touches = []
    for i, finger_action in enumerate(self._split_action(action)):
      x, y, down = self._prepare_action(finger_action)
      touches.append(emulator_controller_pb2.Touch(
          x=x, y=y, pressure=int(down), identifier=i))
    self._emulator_stub.sendTouch(
        emulator_controller_pb2.TouchEvent(touches=touches))

  def _get_observation(self) -> Optional[List[np.ndarray]]:
    """Fetches the latest observation from the emulator."""
    assert self._emulator_stub, 'Emulator stub has not been initialized yet.'
    assert self._image_format, 'ImageFormat has not been initialized yet.'
    image_proto = self._emulator_stub.getScreenshot(self._image_format)
    h, w = image_proto.format.height, image_proto.format.width
    image = np.frombuffer(image_proto.image, dtype='uint8', count=h * w * 3)
    image.shape = (h, w, 3)
    return [image, np.int64(image_proto.timestampUs)]

  def _create_log_stream(self) -> log_stream.LogStream:
    return adb_log_stream.AdbLogStream(
        adb_command_prefix=self._adb_controller.command_prefix(),
        verbose=self._verbose_logs)

  def close(self):
    if hasattr(self, '_channel'):
      self._channel.close()
    if hasattr(self, '_emulator_stub'):
      del self._emulator_stub
    if hasattr(self, '_launcher') and not self._existing_emulator_provided:
      self._launcher.close()
    super().close()
