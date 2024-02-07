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

"""Function for loading AndroidEnv."""

import os

from absl import logging
from android_env import environment
from android_env.components import config_classes
from android_env.components import coordinator as coordinator_lib
from android_env.components import task_manager as task_manager_lib
from android_env.components.simulators.emulator import emulator_simulator
from android_env.proto import task_pb2

from google.protobuf import text_format


def _load_task(task_config: config_classes.TaskConfig) -> task_pb2.Task:
  """Returns the task according to `task_config`."""

  task = task_pb2.Task()
  match task_config:
    case config_classes.FilesystemTaskConfig():
      with open(task_config.path, 'r') as proto_file:
        text_format.Parse(proto_file.read(), task)
    case _:
      logging.error('Unsupported TaskConfig: %r', task_config)

  return task


def load(
    task_path: str,
    avd_name: str | None = None,
    android_avd_home: str = '~/.android/avd',
    android_sdk_root: str = '~/Android/Sdk',
    emulator_path: str = '~/Android/Sdk/emulator/emulator',
    adb_path: str = '~/Android/Sdk/platform-tools/adb',
    run_headless: bool = False,
    console_port: int | None = None,
) -> environment.AndroidEnv:
  """Loads an AndroidEnv instance.

  Args:
    task_path: Path to the task textproto file.
    avd_name: Name of the AVD (Android Virtual Device).
    android_avd_home: Path to the AVD (Android Virtual Device).
    android_sdk_root: Root directory of the SDK.
    emulator_path: Path to the emulator binary.
    adb_path: Path to the ADB (Android Debug Bridge).
    run_headless: If True, the emulator display is turned off.
    console_port: The console port number; for connecting to an already running
      device/emulator.

  Returns:
    env: An AndroidEnv instance.
  """
  connect_to_existing_device = console_port is not None
  if not connect_to_existing_device and avd_name is None:
    raise ValueError('An avd name must be provided if launching an emulator.')

  if connect_to_existing_device:
    launcher_config = config_classes.EmulatorLauncherConfig(
        emulator_console_port=console_port,
        adb_port=console_port + 1,
        grpc_port=8554,
    )
  else:
    launcher_config = config_classes.EmulatorLauncherConfig(
        avd_name=avd_name,
        android_avd_home=os.path.expanduser(android_avd_home),
        android_sdk_root=os.path.expanduser(android_sdk_root),
        emulator_path=os.path.expanduser(emulator_path),
        run_headless=run_headless,
        gpu_mode='swiftshader_indirect',
    )

  # Create simulator.
  simulator = emulator_simulator.EmulatorSimulator(
      config=config_classes.EmulatorConfig(
          emulator_launcher=launcher_config,
          adb_controller=config_classes.AdbControllerConfig(
              adb_path=os.path.expanduser(adb_path),
              adb_server_port=5037,
          ),
      )
  )

  task = _load_task(config_classes.FilesystemTaskConfig(path=task_path))
  task_manager = task_manager_lib.TaskManager(task)
  coordinator = coordinator_lib.Coordinator(simulator, task_manager)
  return environment.AndroidEnv(coordinator=coordinator)
