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

"""Dataclass definitions used for instantiating AndroidEnv components."""

import dataclasses


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


@dataclasses.dataclass
class DeviceSettingsConfig:
  """Config class for DeviceSettings."""

  # Whether to show circles on the screen indicating touch position.
  show_touches: bool = True
  # Whether to show blue lines on the screen indicating touch position.
  show_pointer_location: bool = True
  # Whether or not to show the status (top) bar.
  show_status_bar: bool = False
  # Whether or not to show the navigation (bottom) bar.
  show_navigation_bar: bool = False


@dataclasses.dataclass
class CoordinatorConfig:
  """Config class for Coordinator."""

  # Number of virtual "fingers" of the agent.
  num_fingers: int = 1
  # Whether to enable keyboard key events.
  enable_key_events: bool = False
  # Time between periodic restarts in minutes. If > 0, will trigger
  # a simulator restart at the beginning of the next episode once the time has
  # been reached.
  periodic_restart_time_min: float = 0.0
  # General Android settings.
  device_settings: DeviceSettingsConfig = dataclasses.field(
      default_factory=DeviceSettingsConfig
  )


@dataclasses.dataclass
class SimulatorConfig:
  """Base class for all simulator configs."""

  # If true, the log stream of the simulator will be verbose.
  verbose_logs: bool = False
  # How often to (asynchronously) grab the screenshot from the simulator.
  # If <= 0, stepping the environment blocks on fetching the screenshot (the
  # environment is synchronous).
  interaction_rate_sec: float = 0.0


@dataclasses.dataclass
class EmulatorLauncherConfig:
  """Config class for EmulatorLauncher."""

  # NOTE: If `adb_port`, `emulator_console_port` and `grpc_port` are defined
  # (i.e. not all equal to 0), it is assumed that the emulator they point to
  # exists already and EmulatorLauncher will be skipped.

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
  tmp_dir: str = '/tmp/android_env/simulator/'
  # GPU mode override.
  # Please see
  # https://developer.android.com/studio/run/emulator-acceleration#accel-graphics.
  gpu_mode: str = 'swangle_indirect'  # Alternative: swiftshader_indirect, host
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


@dataclasses.dataclass
class EmulatorConfig(SimulatorConfig):
  """Config class for EmulatorSimulator."""

  # Configuration for launching the Android Emulator.
  emulator_launcher: EmulatorLauncherConfig = dataclasses.field(
      default_factory=EmulatorLauncherConfig
  )
  # Configuration for talking to adb.
  adb_controller: AdbControllerConfig = dataclasses.field(
      default_factory=AdbControllerConfig
  )
  # Path to file which holds emulator logs. If not provided, it will be
  # determined by the EmulatorLauncher.
  logfile_path: str = ''
  # The number of times to try launching the emulator before rebooting (reboot
  # on the n+1-st try).
  launch_n_times_without_reboot: int = 1
  # The number of times to try launching the emulator before reinstalling
  # (reinstall on the n+1-st try).
  launch_n_times_without_reinstall: int = 2


@dataclasses.dataclass
class FakeSimulatorConfig(SimulatorConfig):
  """Config class for FakeSimulator."""

  # The dimensions in pixels of the device screen (HxW).
  screen_dimensions: tuple[int, int] = (0, 0)


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
  coordinator: CoordinatorConfig = dataclasses.field(
      default_factory=CoordinatorConfig
  )
  simulator: SimulatorConfig = dataclasses.field(default_factory=EmulatorConfig)
