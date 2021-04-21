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

from typing import Any, Dict, Optional, List

from absl import logging
from android_env.components import base_simulator
from android_env.components import emulator_console
from android_env.components import emulator_launcher
from android_env.components import errors
from android_env.proto import emulator_controller_pb2
from android_env.proto import emulator_controller_pb2_grpc

import grpc
import numpy as np
import portpicker


def is_existing_emulator_provided(launcher_args: Dict[str, Any]) -> bool:
  """Returns true if all necessary args were provided."""
  return bool(launcher_args.get('adb_port') and
              launcher_args.get('emulator_console_port') and
              launcher_args.get('grpc_port'))


class EmulatorSimulator(base_simulator.BaseSimulator):
  """Controls an Android Emulator."""

  def __init__(self,
               emulator_launcher_args: Dict[str, Any],
               emulator_console_args: Dict[str, Any],
               **kwargs):

    # If adb_port and console_port are both already provided,
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
      self._grpc_port = emulator_launcher_args.get(
          'grpc_port', portpicker.pick_unused_port())

    super().__init__(**kwargs)

    self._emulator_stub = None
    self._image_format = None

    # Create EmulatorLauncher.
    emulator_launcher_args.update({
        'adb_port': self._adb_port,
        'adb_server_port': self._adb_server_port,
        'emulator_console_port': self._console_port,
        'local_tmp_dir': self._local_tmp_dir,
        'kvm_device': self._kvm_device,
        'grpc_port': self._grpc_port,
    })
    logging.info('emulator_launcher_args: %r', emulator_launcher_args)
    if not self._existing_emulator_provided:
      self._launcher = emulator_launcher.EmulatorLauncher(
          **emulator_launcher_args)

   # Prepare EmulatorConsole.
    emulator_console_args.update({
        'console_port': self._console_port,
        'tmp_dir': self._local_tmp_dir,
    })
    logging.info('emulator_console_args: %r', emulator_console_args)
    self._emulator_console_args = emulator_console_args
    self._console = None

  def adb_device_name(self) -> str:
    return 'emulator-%s' % (self._adb_port - 1)

  def _start_console(self) -> None:
    self._console = emulator_console.EmulatorConsole(
        **self._emulator_console_args)

  def _restart_impl(self) -> None:
    if self._console is not None:
      self._console.close()
    if not self._existing_emulator_provided:
      self._launcher.restart()
    if self._grpc_port < 0:
      self._start_console()

  def _launch_impl(self) -> None:
    try:
      if not self._existing_emulator_provided:
        self._launcher.launch()
      if self._grpc_port < 0:
        self._start_console()
    except errors.SimulatorCrashError:
      # If the simulator crashes on the initial launch, we try to restart once.
      self.restart()

  def _post_launch_setup(self):
    super()._post_launch_setup()
    if self._grpc_port >= 0:
      self._emulator_stub = self._create_emulator_stub()
      self._image_format = emulator_controller_pb2.ImageFormat(
          format=emulator_controller_pb2.ImageFormat.ImgFormat.RGB888,
          height=self._screen_dimensions[0],
          width=self._screen_dimensions[1],
      )

  def _create_emulator_stub(self, use_async: bool = False):
    """Returns a stub to the EmulatorController service."""
    port = f'localhost:{self._grpc_port}'
    options = [('grpc.max_send_message_length', -1),
               ('grpc.max_receive_message_length', -1)]
    if use_async:
      self._channel = grpc.aio.insecure_channel(port, options=options)
    else:
      self._channel = grpc.insecure_channel(port, options=options)
    logging.info('Added gRPC channel for the Emulator on port %s', port)
    return emulator_controller_pb2_grpc.EmulatorControllerStub(self._channel)

  def send_action(self, action: Dict[str, np.ndarray]) -> None:
    """Sends a touch event to the emulator."""
    if self._grpc_port < 0:
      # Use the Emulator Console
      assert self._console, 'Console has not been initialized yet.'
      action = self._prepare_action(action)
      self._console.send_mouse_action(*action)
    else:
      # Use gRPC connection
      assert self._emulator_stub, 'Emulator stub has not been initialized yet.'
      x, y, down = self._prepare_action(action)
      self._emulator_stub.sendTouch(
          emulator_controller_pb2.TouchEvent(touches=[
              emulator_controller_pb2.Touch(x=x, y=y, pressure=int(down))]))

  def _get_observation(self) -> Optional[List[np.ndarray]]:
    """Fetches the latest observation from the emulator."""
    if self._grpc_port < 0:
      assert self._console, 'Console has not been initialized yet.'
      return self._console.fetch_screenshot()
    else:
      assert self._emulator_stub, 'Emulator stub has not been initialized yet.'
      assert self._image_format, 'ImageFormat has not been initialized yet.'
      image_proto = self._emulator_stub.getScreenshot(self._image_format)
      h, w = image_proto.format.height, image_proto.format.width
      image = np.frombuffer(image_proto.image, dtype='uint8', count=h*w*3)
      image.shape = (h, w, 3)
      return [image, np.int64(image_proto.timestampUs)]

  def close(self):
    if self._console is not None:
      self._console.close()
    if hasattr(self, '_channel'):
      self._channel.close()
    if hasattr(self, '_emulator_stub'):
      del self._emulator_stub
    if hasattr(self, '_launcher') and not self._existing_emulator_provided:
      self._launcher.close()
    super().close()
