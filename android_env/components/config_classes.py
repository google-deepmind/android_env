# coding=utf-8
# Copyright 2026 DeepMind Technologies Limited.
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

"""Dataclass definitions used for instantiating AndroidEnv components."""

import dataclasses
import enum


@dataclasses.dataclass
class AdbControllerConfig:
  """Settings for instatiating an `AdbController` instance."""

  # Filesystem path to the `adb` binary.
  # NOTE: This must be a full path and must not contain environment variables
  # or user folder shorthands (e.g. `~/some/path/to/adb`) since they will not be
  # expanded internally by AndroidEnv.
  adb_path: str = '~/Android/Sdk/platform-tools/adb'
  # Port for adb server.
  adb_server_port: int = 5037
  # Default timeout in seconds for internal commands.
  default_timeout: float = 120.0
  # Name of the device to communicate with.
  device_name: str = ''
  # Whether to use adb server port set in OS Environment variables.
  # When True, adb will use the ANDROID_ADB_SERVER_PORT OS environment variable
  # for selecting its server port if available (or the default 5037 if not set).
  # When False, the ANDROID_ADB_SERVER_PORT OS environment var will be unset
  # and adb_server_port will be used and supplied as an argument to all adb
  # commands.
  use_adb_server_port_from_os_env: bool = False


@enum.unique
class GPUMode(enum.Enum):
  """Emulator GPU Mode."""

  HOST = 'host'
  SWANGLE_INDIRECT = 'swangle_indirect'
  SWIFTSHADER_INDIRECT = 'swiftshader_indirect'


@dataclasses.dataclass
class EmulatorLauncherConfig:
  """Config class for EmulatorLauncher."""

  # Filesystem path to the `emulator` binary.
  emulator_path: str = '~/Android/Sdk/emulator/emulator'
  # Filesystem path to the Android SDK root.
  android_sdk_root: str = '~/Android/Sdk'
  # Name of the AVD.
  avd_name: str = ''
  # Local directory for AVDs.
  android_avd_home: str = '~/.android/avd'
  # Name of the snapshot to load.
  snapshot_name: str = ''
  # Path to the KVM device.
  kvm_device: str = '/dev/kvm'
  # Path to directory which will hold temporary files.
  tmp_dir: str = '/tmp/android_env/emulator/'
  # GPU mode override.
  # Please see
  # https://developer.android.com/studio/run/emulator-acceleration#accel-graphics.
  gpu_mode: str = GPUMode.SWANGLE_INDIRECT.value
  # Whether to run in headless mode (i.e. without a graphical window).
  run_headless: bool = True
  # Whether to restrict network access.
  # If True, will disable networking on the device. This option is only
  # available for emulator version > 31.3.9 (June 2022).
  restrict_network: bool = False
  # Whether to set `SHOW_PERF_STATS=1` when launching the emulator to display
  # performance and memory statistics.
  show_perf_stats: bool = False

  # ADB port for the Android device.
  adb_port: int = 0
  # Port for telnet communication with the emulator.
  emulator_console_port: int = 0
  # Port for gRPC communication with the emulator.
  grpc_port: int = 0
  # Whether to connect to an existing emulator.
  # If True, we connect to the emulator at the specified ports and do not
  # launch.
  # If False, we launch a new emulator (ports must be pre-allocated).
  connect_to_existing: bool = False


@dataclasses.dataclass
class DeviceConnectionConfig:
  """Configuration for network connection to the on-device AndroidEnv server.

  Attributes:
    host: Hostname or IP address where the AndroidEnv server runs (e.g.
      'localhost' when port-forwarded via ADB, or remote device IP).
    websocket_port: Port for the WebSocket control channel served by the device.
      The Python client connects to `ws://<host>:<websocket_port>`.
      Payloads: Binary Protobuf `ClientMessage` and `ServerMessage` for action
        injection, subscription updates, video frames, and device
        state/metadata.
  """

  host: str = 'localhost'
  websocket_port: int = 8000


@dataclasses.dataclass
class AndroidDeviceConfig:
  """Config class for AndroidDevice (on-device Core server)."""

  device_connection: DeviceConnectionConfig = dataclasses.field(
      default_factory=DeviceConnectionConfig
  )
  adb_path: str = 'adb'
  serial: str = ''
  auto_setup: bool = True
  # Optional filesystem path to `android_env_server.apk`. If empty,
  # `load_android_device` uses the bundled APK when `auto_setup` is True.
  server_apk_path: str = ''
  # Optional launcher config. If set, loader will launch emulator.
  emulator_launcher: EmulatorLauncherConfig | None = None
  adb_controller: AdbControllerConfig | None = None


@dataclasses.dataclass
class TaskManagerConfig:
  """Config class for TaskManager."""

  # If max_bad_states episodes finish in a bad state in a row, restart
  # the simulation.
  max_bad_states: int = 3
  # The frequency to check for the current activity and view hierarchy.
  # The unit is raw observation (i.e. each call to AndroidEnv.step()).
  dumpsys_check_frequency: int = 150
  # The maximum number of tries for extracting the current activity before
  # forcing the episode to restart.
  max_failed_current_activity: int = 10
  # The maximum number of extras elements to store. If this number is exceeded,
  # elements are dropped in the order they were received.
  extras_max_buffer_size: int = 100


@dataclasses.dataclass
class TaskConfig:
  """Base config class for loading tasks."""

  # The directory for temporary task-related resources.
  tmp_dir: str = ''


@dataclasses.dataclass
class FilesystemTaskConfig(TaskConfig):
  """Config for protobuf files stored in the local filesystem."""

  # Filesystem path to `.binarypb` or `.textproto` protobuf Task.
  path: str = ''


@dataclasses.dataclass
class AndroidEnvConfig:
  """Config class for AndroidEnv."""

  # Configs for main components.
  task: TaskConfig = dataclasses.field(default_factory=TaskConfig)
  task_manager: TaskManagerConfig = dataclasses.field(
      default_factory=TaskManagerConfig
  )
  simulator: AndroidDeviceConfig = dataclasses.field(
      default_factory=AndroidDeviceConfig
  )
