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

"""A class that manages an Android Emulator."""

import os
import time
from typing import Any

from absl import logging
from android_env.components import adb_controller
from android_env.components import adb_log_stream
from android_env.components import config_classes
from android_env.components import errors
from android_env.components import log_stream
from android_env.components.simulators import base_simulator
from android_env.components.simulators.emulator import emulator_launcher
from android_env.proto import state_pb2
import grpc
import numpy as np
import portpicker

from android_env.proto import emulator_controller_pb2
from android_env.proto import emulator_controller_pb2_grpc
from android_env.proto import snapshot_service_pb2
from android_env.proto import snapshot_service_pb2_grpc
from google.protobuf import empty_pb2


_DEFAULT_SNAPSHOT_NAME: str = 'default_snapshot'


def _is_existing_emulator_provided(
    launcher_config: config_classes.EmulatorLauncherConfig,
) -> bool:
  """Returns true if all necessary args were provided."""

  return bool(
      launcher_config.adb_port
      and launcher_config.emulator_console_port
      and launcher_config.grpc_port
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


class EmulatorBootError(errors.SimulatorError):
  """Raised when an emulator failed to boot."""


class EmulatorCrashError(errors.SimulatorError):
  """Raised when a simulator crashed."""


class EmulatorSimulator(base_simulator.BaseSimulator):
  """Controls an Android Emulator."""

  def __init__(self, config: config_classes.EmulatorConfig):
    """Instantiates an EmulatorSimulator."""

    super().__init__(verbose_logs=config.verbose_logs)
    self._config = config

    # If adb_port, console_port and grpc_port are all already provided,
    # we assume the emulator already exists and there's no need to launch.
    if _is_existing_emulator_provided(self._config.emulator_launcher):
      self._existing_emulator_provided = True
      logging.info('Connecting to existing emulator "%r"',
                   self.adb_device_name())
    else:
      self._existing_emulator_provided = False
      self._config.emulator_launcher.adb_port = _pick_adb_port()
      self._config.emulator_launcher.emulator_console_port = (
          portpicker.pick_unused_port()
      )
      self._config.emulator_launcher.grpc_port = _pick_emulator_grpc_port()

    self._channel = None
    self._emulator_stub: emulator_controller_pb2_grpc.EmulatorControllerStub | None = (
        None
    )
    self._snapshot_stub = None
    # Set the image format to RGBA. The width and height of the returned
    # screenshots will use the device's width and height.
    self._image_format = emulator_controller_pb2.ImageFormat(
        format=emulator_controller_pb2.ImageFormat.ImgFormat.RGBA8888)

    if (
        self._config.launch_n_times_without_reboot
        > self._config.launch_n_times_without_reinstall
    ):
      raise ValueError(
          'Number of launch attempts before reboot'
          f' ({self._config.launch_n_times_without_reboot}) should not be'
          ' greater than number of launch attempts before reinstall'
          f' ({self._config.launch_n_times_without_reinstall})'
      )

    # Initialize own ADB controller.
    self._config.adb_controller.device_name = self.adb_device_name()
    self._adb_controller = self.create_adb_controller()
    self._adb_controller.init_server()
    logging.info(
        'Initialized simulator with ADB server port %r.',
        self._config.adb_controller.adb_server_port,
    )

    # If necessary, create EmulatorLauncher.
    if self._existing_emulator_provided:
      self._logfile_path = self._config.logfile_path or None
      self._launcher = None
    else:
      logging.info(
          'emulator_launcher config: %r', self._config.emulator_launcher
      )
      self._launcher = emulator_launcher.EmulatorLauncher(
          config=self._config.emulator_launcher,
          adb_controller_config=self._config.adb_controller,
      )
      self._logfile_path = (
          self._config.logfile_path or self._launcher.logfile_path()
      )

  def _reconnect_on_grpc_error(func):
    """Decorator function for reconnecting to emulator upon grpc errors."""

    def wrapper(self, *args, **kwargs):
      try:
        return func(self, *args, **kwargs)
      except grpc.RpcError:
        logging.exception('RpcError caught. Reconnecting to emulator...')
        self._emulator_stub, self._snapshot_stub = self._connect_to_emulator(
            self._config.emulator_launcher.grpc_port
        )
        return func(self, *args, **kwargs)

    return wrapper

  def get_logs(self) -> str:
    """Returns logs recorded by the emulator."""
    if self._logfile_path and os.path.exists(self._logfile_path):
      with open(self._logfile_path, 'rb') as f:
        return f.read().decode('utf-8')
    else:
      return f'Logfile does not exist: {self._logfile_path}.'

  def adb_device_name(self) -> str:
    return 'emulator-%s' % (self._config.emulator_launcher.adb_port - 1)

  def create_adb_controller(self):
    """Returns an ADB controller which can communicate with this simulator."""
    return adb_controller.AdbController(self._config.adb_controller)

  def create_log_stream(self) -> log_stream.LogStream:
    return adb_log_stream.AdbLogStream(
        adb_command_prefix=self._adb_controller.command_prefix(),
        verbose=self._verbose_logs)

  def _launch_impl(self) -> None:
    """Prepares an Android Emulator for RL interaction.

    The behavior depends on `self._num_launch_attempts`'s value:
      * <= self._config.launch_n_times_without_reboot   -> Normal boot behavior.
      * > self._config.launch_n_times_without_reboot but <=
          self._config.launch_n_times_without_reinstall -> reboot (i.e. process
          is killed and started again).
      * > self._config.launch_n_times_without_reinstall -> reinstall (i.e.
          process is killed, emulator files are deleted and the process started
          again).
    """

    logging.info('Attempt %r at launching the Android Emulator (%r)',
                 self._num_launch_attempts, self.adb_device_name())

    if self._launcher is not None:
      # If not the first time, then shutdown the emulator first.
      if (
          self._emulator_stub is not None
          and self._num_launch_attempts
          > self._config.launch_n_times_without_reboot
      ):
        self._shutdown_emulator()
        # Subsequent attempts cause the emulator files to be reinstalled.
        if (
            self._num_launch_attempts
            > self._config.launch_n_times_without_reinstall
        ):
          logging.info('Closing emulator (%r)', self.adb_device_name())
          self._launcher.close()
          self._launcher = emulator_launcher.EmulatorLauncher(
              config=self._config.emulator_launcher,
              adb_controller_config=self._config.adb_controller,
          )
      self._launcher.launch_emulator_process()
    # Establish grpc connection to emulator process.
    self._emulator_stub, self._snapshot_stub = self._connect_to_emulator(
        self._config.emulator_launcher.grpc_port
    )

    # Confirm booted status.
    try:
      self._confirm_booted()
    except EmulatorCrashError:
      logging.exception('Failed to confirm booted status of emulator.')

    logging.info('Done booting the Android Emulator.')

  def load_state(
      self, request: state_pb2.LoadStateRequest
  ) -> state_pb2.LoadStateResponse:
    """Loads a state using the emulator's snapshotting mechanism.

    Args:
      request: The `LoadStateRequest`. In this case, `args` should be a dict
        containing the key 'snapshot_name', representing the name of the
        snapshot to load. If `request.args.snapshot_name` is `None`, a default
        snapshot name is used.

    Returns:
      A response indicating whether the snapshot was successfully loaded.
      * If the snapshot was loaded successfully, the status will be `OK`.
      * If no snapshot of the given name was found, the status will be
        `NOT_FOUND`.
      * If an error occurred during the snapshot loading process, the status
        will be `ERROR` and the `error_message` field will be filled.
    """
    assert self._snapshot_stub is not None
    snapshot_name = request.args.get('snapshot_name', _DEFAULT_SNAPSHOT_NAME)
    snapshot_list = self._snapshot_stub.ListSnapshots(
        snapshot_service_pb2.SnapshotFilter(
            statusFilter=snapshot_service_pb2.SnapshotFilter.LoadStatus.All
        )
    )
    if any(
        snapshot.snapshot_id == snapshot_name
        for snapshot in snapshot_list.snapshots
    ):
      snapshot_result = self._snapshot_stub.LoadSnapshot(
          snapshot_service_pb2.SnapshotPackage(snapshot_id=snapshot_name)
      )
      if snapshot_result.success:
        return state_pb2.LoadStateResponse(
            status=state_pb2.LoadStateResponse.Status.OK
        )
      else:
        return state_pb2.LoadStateResponse(
            status=state_pb2.LoadStateResponse.Status.ERROR,
            error_message=snapshot_result.err.decode('utf-8'),
        )

    else:
      return state_pb2.LoadStateResponse(
          status=state_pb2.LoadStateResponse.Status.NOT_FOUND
      )

  def save_state(
      self, request: state_pb2.SaveStateRequest
  ) -> state_pb2.SaveStateResponse:
    """Saves a state using the emulator's snapshotting mechanism.

    Args:
      request: The `SaveStateRequest`. In this case, `args` should be a dict
        containing the key 'snapshot_name', representing the name of the
        snapshot to save. If `request.args.snapshot_name` is `None`, a default
        snapshot name is used.

    Returns:
      A response indicating whether the snapshot was successfully saved.
      * If the snapshot was saved successfully, the status will be `OK`.
      * If an error occurred during the snapshot saving process, the status
        will be `ERROR` and the `error_message` field will be filled.
    """
    assert self._snapshot_stub is not None
    snapshot_name = request.args.get('snapshot_name', _DEFAULT_SNAPSHOT_NAME)
    snapshot_result = self._snapshot_stub.SaveSnapshot(
        snapshot_service_pb2.SnapshotPackage(snapshot_id=snapshot_name)
    )
    if snapshot_result.success:
      return state_pb2.SaveStateResponse(
          status=state_pb2.SaveStateResponse.Status.OK
      )
    else:
      return state_pb2.SaveStateResponse(
          status=state_pb2.SaveStateResponse.Status.ERROR,
          error_message=snapshot_result.err.decode('utf-8'),
      )

  def _connect_to_emulator(
      self,
      grpc_port: int,
      timeout_sec: int = 100,
  ) -> tuple[
      emulator_controller_pb2_grpc.EmulatorControllerStub,
      snapshot_service_pb2_grpc.SnapshotServiceStub,
  ]:
    """Connects to an emulator and returns a corresponsing stub."""

    logging.info('Creating gRPC channel to the emulator on port %r', grpc_port)
    port = f'localhost:{grpc_port}'
    options = [('grpc.max_send_message_length', -1),
               ('grpc.max_receive_message_length', -1)]
    creds = grpc.local_channel_credentials()

    try:
      self._channel = grpc.secure_channel(port, creds, options=options)
      grpc.channel_ready_future(self._channel).result(timeout=timeout_sec)
    except (grpc.RpcError, grpc.FutureTimeoutError) as grpc_error:
      logging.exception('Failed to connect to the emulator.')
      raise EmulatorBootError(
          'Failed to connect to the emulator.') from grpc_error

    logging.info('Added gRPC channel for the Emulator on port %s', port)
    emulator_controller_stub = (
        emulator_controller_pb2_grpc.EmulatorControllerStub(self._channel)
    )
    snapshot_stub = snapshot_service_pb2_grpc.SnapshotServiceStub(self._channel)
    return emulator_controller_stub, snapshot_stub

  @_reconnect_on_grpc_error
  def _confirm_booted(self, startup_wait_time_sec: int = 300):
    """Waits until the emulator is fully booted."""

    assert (
        self._emulator_stub is not None
    ), 'Emulator stub has not been initialized yet.'
    start_time = time.time()
    deadline = start_time + startup_wait_time_sec
    success = False
    while time.time() < deadline:
      emu_status = self._emulator_stub.getStatus(empty_pb2.Empty())
      logging.info('Waiting for emulator (%r) to start... (%rms)',
                   self.adb_device_name(), emu_status.uptime)
      if emu_status.booted:
        success = True
        break
      time.sleep(5.0)

    elapsed_time = time.time() - start_time
    if not success:
      raise EmulatorCrashError(
          f'The emulator failed to boot after {startup_wait_time_sec} seconds')

    logging.info('Done booting the emulator (in %f seconds).', elapsed_time)
    logging.info('********** Emulator logs **********')
    for line in self.get_logs().splitlines():
      logging.info(line)
    logging.info('******* End of emulator logs *******')
    logging.info('See the full emulator logs at %r', self._logfile_path)

  @_reconnect_on_grpc_error
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

    assert (
        self._emulator_stub is not None
    ), 'Emulator stub has not been initialized yet.'
    touch_events = [
        emulator_controller_pb2.Touch(
            x=t[0], y=t[1], pressure=int(t[2]), identifier=t[3])
        for t in touches
    ]
    self._emulator_stub.sendTouch(
        emulator_controller_pb2.TouchEvent(touches=touch_events))

  @_reconnect_on_grpc_error
  def send_key(self, keycode: np.int32, event_type: str) -> None:
    """Sends a key event to the emulator.

    Args:
      keycode: Code representing the desired key press in XKB format.
        See the emulator_controller_pb2 for details.
      event_type: Type of key event to be sent.
    """

    event_types = emulator_controller_pb2.KeyboardEvent.KeyEventType.keys()
    if event_type not in event_types:
      raise ValueError(
          f'Event type must be one of {event_types} but is {event_type}.')

    assert (
        self._emulator_stub is not None
    ), 'Emulator stub has not been initialized yet.'
    self._emulator_stub.sendKey(
        emulator_controller_pb2.KeyboardEvent(
            codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
            eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType.Value(
                event_type
            ),
            keyCode=int(keycode),
        )
    )

  @_reconnect_on_grpc_error
  def get_screenshot(self) -> np.ndarray:
    """Fetches the latest screenshot from the emulator."""

    assert (
        self._emulator_stub is not None
    ), 'Emulator stub has not been initialized yet.'
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

    assert self._launcher is not None, 'Launcher is already down.'

    logging.info('Shutting down the emulator (%r)...', self.adb_device_name())
    self._emulator_stub.setVmState(
        emulator_controller_pb2.VmRunState(
            state=emulator_controller_pb2.VmRunState.RunState.SHUTDOWN))
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
