# coding=utf-8
# Copyright 2023 DeepMind Technologies Limited.
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
  adb_path: str = 'adb'
  # Port for adb server.
  adb_server_port: int = 5037
  # Default timeout in seconds for internal commands.
  default_timeout: float = 120.0
  # Name of the device to communicate with.
  device_name: str = ''


@dataclasses.dataclass
class CoordinatorConfig:
  """Config class for Coordinator."""

  # Number of virtual "fingers" of the agent.
  num_fingers: int = 1
  # How often to (asynchronously) grab the screenshot from the simulator.
  # If <= 0, stepping the environment blocks on fetching the screenshot (the
  # environment is synchronous).
  interaction_rate_sec: float = 0.0
  # Whether to enable keyboard key events.
  enable_key_events: bool = False
  # Whether to show circles on the screen indicating touch position.
  show_touches: bool = True
  # Whether to show blue lines on the screen indicating touch position.
  show_pointer_location: bool = True
  # Whether or not to show the status (top) bar.
  show_status_bar: bool = False
  # Whether or not to show the navigation (bottom) bar.
  show_navigation_bar: bool = False
  # Time between periodic restarts in minutes. If > 0, will trigger
  # a simulator restart at the beginning of the next episode once the time has
  # been reached.
  periodic_restart_time_min: float = 0.0
  # The target directory that will contain coordinator related files.
  tmp_dir: str = ''


@dataclasses.dataclass
class SimulatorConfig:
  """Base class for all simulator configs."""

  # If true, the log stream of the simulator will be verbose.
  verbose_logs: bool = False


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
