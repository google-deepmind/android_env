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

"""A class that manages an Android Emulator."""

import os
import time
from typing import Any, Dict, List, Optional, Tuple

from absl import logging
from android_env.components import adb_controller
from android_env.components import adb_log_stream
from android_env.components import errors
from android_env.components import log_stream
from android_env.components.simulators import base_simulator
from android_env.components.simulators.emulator import emulator_launcher
import grpc
import numpy as np
import portpicker

from android_env.proto import emulator_controller_pb2
from android_env.proto import emulator_controller_pb2_grpc
from android_env.proto import snapshot_service_pb2
from android_env.proto import snapshot_service_pb2_grpc
from google.protobuf import empty_pb2

_LOCAL_SNAPSHOT_NAME = 'local_snapshot'


def is_existing_emulator_provided(launcher_args: Dict[str, Any]) -> bool:
  """Returns true if all necessary args were provided."""
  return bool(
      launcher_args.get('adb_port')
      and launcher_args.get('emulator_console_port')
      and launcher_args.get('grpc_port')
  )


def _pick_adb_port() -> int:
  """Tries to pick a port in the recommended range 5555-5585.

  If no such port can be found, will return a random unused port. More info:
  https://developer.android.com/studio/command-line/adb#howadbworks.

  Returns:
    port: an available port for adb.
  """
  for p in range(5555, 5587, 2):
    if portpicker.is_port_free(p):
      return p
  return portpicker.pick_unused_port()


def _pick_emulator_grpc_port() -> int:
  """Tries to pick the recommended port for grpc.

  If no such port can be found, will return a random unused port. More info:
  https://android.googlesource.com/platform/external/qemu/+/emu-master-dev/android/android-grpc/docs/.

  Returns:
    port: an available port for emulator grpc.
  """
  if portpicker.is_port_free(8554):
    return 8554
  else:
    return portpicker.pick_unused_port()


def _reconnect_on_grpc_error(func):
  """Decorator function for reconnecting to emulator upon grpc errors."""

  def wrapper(*args, **kwargs):
    try:
      return func(*args, **kwargs)
    except grpc.RpcError:
      logging.exception('RpcError caught. Reconnecting to emulator...')
      emu = args[0]  # The first arg of the function is "self"
      emu._emulator_stub, emu._snapshot_stub = emu._connect_to_emulator(  # pylint: disable=protected-access
          emu._grpc_port  # pylint: disable=protected-access
      )
      return func(*args, **kwargs)

  return wrapper


class EmulatorBootError(errors.SimulatorError):
  """Raised when an emulator failed to boot."""


class EmulatorCrashError(errors.SimulatorError):
  """Raised when a simulator crashed."""


class EmulatorSimulator(base_simulator.BaseSimulator):
  """Controls an Android Emulator."""

  def __init__(
      self,
      emulator_launcher_args: Dict[str, Any],
      adb_controller_args: Dict[str, Any],
      tmp_dir: str = '/tmp/android_env/simulator',
      logfile_path: Optional[str] = None,
      launch_n_times_without_reboot: int = 1,
      launch_n_times_without_reinstall: int = 2,
      **kwargs,
  ):
    """Instantiates an EmulatorSimulator.

    Args:
      emulator_launcher_args: Arguments for EmulatorLauncher.
      adb_controller_args: Arguments for AdbController.
      tmp_dir: Temporary directory to hold simulator files.
      logfile_path: Path to file which holds emulator logs. If not provided, it
        will be determined by the EmulatorLauncher.
      launch_n_times_without_reboot: The number of times to try launching the
        emulator before rebooting (reboot on the n+1-st try).
      launch_n_times_without_reinstall: The number of times to try launching the
        emulator before reinstalling (reinstall on the n+1-st try).
      **kwargs: keyword arguments for base class.
    """

    # If adb_port, console_port and grpc_port are all already provided,
    # we assume the emulator already exists and there's no need to launch.
    if is_existing_emulator_provided(emulator_launcher_args):
      self._existing_emulator_provided = True
      self._adb_port = emulator_launcher_args['adb_port']
      self._console_port = emulator_launcher_args['emulator_console_port']
      self._grpc_port = emulator_launcher_args['grpc_port']
      logging.info(
          'Connecting to existing emulator "%r"', self.adb_device_name()
      )
    else:
      self._existing_emulator_provided = False
      self._adb_port = _pick_adb_port()
      self._console_port = portpicker.pick_unused_port()
      self._grpc_port = _pick_emulator_grpc_port()

    self._channel = None
    self._emulator_stub = None
    self._snapshot_stub = None
    # Set the image format to RGBA. The width and height of the returned
    # screenshots will use the device's width and height.
    self._image_format = emulator_controller_pb2.ImageFormat(
        format=emulator_controller_pb2.ImageFormat.ImgFormat.RGBA8888
    )

    if launch_n_times_without_reboot > launch_n_times_without_reinstall:
      raise ValueError(
          'Number of launch attempts before reboot '
          f'({launch_n_times_without_reboot}) should not be greater than '
          'number of launch attempts before reinstall '
          f'({launch_n_times_without_reinstall})'
      )
    self._launch_n_times_without_reboot = launch_n_times_without_reboot
    self._launch_n_times_without_reinstall = launch_n_times_without_reinstall

    super().__init__(**kwargs)

    # Initialize own ADB controller.
    self._adb_controller_args = adb_controller_args
    self._adb_controller = self.create_adb_controller()
    self._adb_controller.init_server()
    logging.info(
        'Initialized simulator with ADB server port %r.',
        self._adb_controller_args['adb_server_port'],
    )

    # If necessary, create EmulatorLauncher.
    if self._existing_emulator_provided:
      self._logfile_path = logfile_path or None
      self._launcher = None
    else:
      emulator_launcher_args.update({
          'adb_path': self._adb_controller_args['adb_path'],
          'adb_port': self._adb_port,
          'adb_server_port': self._adb_controller_args['adb_server_port'],
          'emulator_console_port': self._console_port,
          'grpc_port': self._grpc_port,
          'tmp_dir': tmp_dir,
      })
      self._emulator_launcher_args = emulator_launcher_args
      logging.info('emulator_launcher_args: %r', self._emulator_launcher_args)
      self._launcher = emulator_launcher.EmulatorLauncher(
          **self._emulator_launcher_args
      )
      self._logfile_path = logfile_path or self._launcher.logfile_path()

  def get_logs(self) -> str:
    """Returns logs recorded by the emulator."""
    if self._logfile_path and os.path.exists(self._logfile_path):
      with open(self._logfile_path, 'rb') as f:
        return f.read().decode('utf-8')
    else:
      return f'Logfile does not exist: {self._logfile_path}.'

  def adb_device_name(self) -> str:
    return 'emulator-%s' % (self._adb_port - 1)

  def create_adb_controller(self):
    """Returns an ADB controller which can communicate with this simulator."""
    return adb_controller.AdbController(
        device_name=self.adb_device_name(), **self._adb_controller_args
    )

  def create_log_stream(self) -> log_stream.LogStream:
    return adb_log_stream.AdbLogStream(
        adb_command_prefix=self._adb_controller.command_prefix(),
        verbose=self._verbose_logs,
    )

  def _launch_impl(self) -> None:
    """Prepares an Android Emulator for RL interaction.

    The behavior depends on `self._num_launch_attempts`'s value:
      * <= self._launch_n_times_without_reboot   -> Normal boot behavior.
      * > self._launch_n_times_without_reboot but <=
          self._launch_n_times_without_reinstall -> reboot (i.e. process is
          killed and started again).
      * > self._launch_n_times_without_reinstall -> reinstall (i.e. process is
          killed, emulator files are deleted and the process started again).
    """

    logging.info(
        'Attempt %r at launching the Android Emulator (%r)',
        self._num_launch_attempts,
        self.adb_device_name(),
    )

    if self._launcher is not None:
      # If not the first time, then shutdown the emulator first.
      if (
          self._emulator_stub is not None
          and self._num_launch_attempts > self._launch_n_times_without_reboot
      ):
        self._shutdown_emulator()
        # Subsequent attempts cause the emulator files to be reinstalled.
        if self._num_launch_attempts > self._launch_n_times_without_reinstall:
          logging.info('Closing emulator (%r)', self.adb_device_name())
          self._launcher.close()
          self._launcher = emulator_launcher.EmulatorLauncher(
              **self._emulator_launcher_args
          )
      self._launcher.launch_emulator_process()
    # Establish grpc connection to emulator process.
    self._emulator_stub, self._snapshot_stub = self._connect_to_emulator(
        self._grpc_port
    )

    # Confirm booted status.
    try:
      self._confirm_booted()
    except EmulatorCrashError:
      logging.exception('Failed to confirm booted status of emulator.')

    logging.info('Done booting the Android Emulator.')

  def save_or_load_local_snapshot(self) -> None:
    snapshot_list = self._snapshot_stub.ListSnapshots(
        snapshot_service_pb2.SnapshotFilter(
            statusFilter=snapshot_service_pb2.SnapshotFilter.LoadStatus.All
        )
    )
    if any(
        snapshot.snapshot_id == _LOCAL_SNAPSHOT_NAME
        for snapshot in snapshot_list.snapshots
    ):
      logging.info('Snapshot %s found; loading', _LOCAL_SNAPSHOT_NAME)
      snapshot_result = self._snapshot_stub.LoadSnapshot(
          snapshot_service_pb2.SnapshotPackage(snapshot_id=_LOCAL_SNAPSHOT_NAME)
      )
      logging.info(snapshot_result)
    else:
      logging.info('Snapshot %s not found; saving', _LOCAL_SNAPSHOT_NAME)
      snapshot_result = self._snapshot_stub.SaveSnapshot(
          snapshot_service_pb2.SnapshotPackage(snapshot_id=_LOCAL_SNAPSHOT_NAME)
      )
      logging.info(snapshot_result)

  def _connect_to_emulator(
      self,
      grpc_port: int,
      timeout_sec: int = 100,
  ) -> Tuple[
      emulator_controller_pb2_grpc.EmulatorControllerStub,
      snapshot_service_pb2_grpc.SnapshotServiceStub,
  ]:
    """Connects to an emulator and returns a corresponsing stub."""

    logging.info('Creating gRPC channel to the emulator on port %r', grpc_port)
    port = f'localhost:{grpc_port}'
    options = [
        ('grpc.max_send_message_length', -1),
        ('grpc.max_receive_message_length', -1),
    ]
    creds = grpc.local_channel_credentials()

    try:
      self._channel = grpc.secure_channel(port, creds, options=options)
      grpc.channel_ready_future(self._channel).result(timeout=timeout_sec)
    except (grpc.RpcError, grpc.FutureTimeoutError) as grpc_error:
      logging.exception('Failed to connect to the emulator.')
      raise EmulatorBootError(
          'Failed to connect to the emulator.'
      ) from grpc_error

    logging.info('Added gRPC channel for the Emulator on port %s', port)
    return emulator_controller_pb2_grpc.EmulatorControllerStub(
        self._channel
    ), snapshot_service_pb2_grpc.SnapshotServiceStub(self._channel)

  @_reconnect_on_grpc_error
  def _confirm_booted(self, startup_wait_time_sec: int = 300):
    """Waits until the emulator is fully booted."""

    start_time = time.time()
    deadline = start_time + startup_wait_time_sec
    success = False
    while time.time() < deadline:
      emu_status = self._emulator_stub.getStatus(empty_pb2.Empty())
      logging.info(
          'Waiting for emulator (%r) to start... (%rms)',
          self.adb_device_name(),
          emu_status.uptime,
      )
      if emu_status.booted:
        success = True
        break
      time.sleep(5.0)

    elapsed_time = time.time() - start_time
    if not success:
      raise EmulatorCrashError(
          f'The emulator failed to boot after {startup_wait_time_sec} seconds'
      )

    logging.info('Done booting the emulator (in %f seconds).', elapsed_time)
    logging.info('********** Emulator logs (last 20 lines) **********')
    for line in self.get_logs().splitlines()[-20:]:
      logging.info(line)
    logging.info('******* End of emulator logs *******')
    logging.info('See the full emulator logs at %r', self._logfile_path)

  @_reconnect_on_grpc_error
  def send_touch(self, touches: List[Tuple[int, int, bool, int]]) -> None:
    """Sends a touch event to be executed on the simulator.

    Args:
      touches: A list of touch events. Each element in the list corresponds to a
        single touch event. Each touch event tuple should have: 0 x: The
        horizontal coordinate of this event. 1 y: The vertical coordinate of
        this event. 2 is_down: Whether the finger is touching or not the screen.
        3 identifier: Identifies a particular finger in a multitouch event.
    """

    assert self._emulator_stub, 'Emulator stub has not been initialized yet.'
    touch_events = [
        emulator_controller_pb2.Touch(
            x=t[0], y=t[1], pressure=int(t[2]), identifier=t[3]
        )
        for t in touches
    ]
    self._emulator_stub.sendTouch(
        emulator_controller_pb2.TouchEvent(touches=touch_events)
    )

  @_reconnect_on_grpc_error
  def send_key(self, keycode: np.int32, event_type: str) -> None:
    """Sends a key event to the emulator.

    Args:
      keycode: Code representing the desired key press in XKB format. See the
        emulator_controller_pb2 for details.
      event_type: Type of key event to be sent.
    """
    event_types = emulator_controller_pb2.KeyboardEvent.KeyEventType.keys()
    if event_type not in event_types:
      raise ValueError(
          f'Event type must be one of {event_types} but is {event_type}.'
      )

    self._emulator_stub.sendKey(
        emulator_controller_pb2.KeyboardEvent(
            codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
            eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType.Value(
                event_type
            ),
            keyCode=np.int32(keycode),
        )
    )

  @_reconnect_on_grpc_error
  def get_screenshot(self) -> np.ndarray:
    """Fetches the latest screenshot from the emulator."""
    assert self._emulator_stub, 'Emulator stub has not been initialized yet.'
    assert self._image_format, 'ImageFormat has not been initialized yet.'
    image_proto = self._emulator_stub.getScreenshot(self._image_format)
    h, w = image_proto.format.height, image_proto.format.width
    image = np.frombuffer(image_proto.image, dtype='uint8', count=h * w * 4)
    image.shape = (h, w, 4)
    return image[:, :, :3]

  @_reconnect_on_grpc_error
  def _shutdown_emulator(self):
    """Sends a signal to trigger emulator shutdown."""

    if self._emulator_stub is None:
      logging.info('Emulator (%r) is not up.', self.adb_device_name())
      return

    logging.info('Shutting down the emulator (%r)...', self.adb_device_name())
    self._emulator_stub.setVmState(
        emulator_controller_pb2.VmRunState(
            state=emulator_controller_pb2.VmRunState.RunState.SHUTDOWN
        )
    )
    self._launcher.confirm_shutdown()

  def close(self):
    if self._launcher is not None:
      self._shutdown_emulator()
      logging.info('Closing emulator (%r)', self.adb_device_name())
      self._launcher.close()
    self._emulator_stub = None
    self._snapshot_stub = None
    if self._channel is not None:
      self._channel.close()
    super().close()
