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
from android_env.components import device_settings as device_settings_lib
from android_env.components import task_manager as task_manager_lib
from android_env.components.simulators.emulator import emulator_simulator
from android_env.components.simulators.fake import fake_simulator
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


def load(config: config_classes.AndroidEnvConfig) -> environment.AndroidEnv:
  """Loads an AndroidEnv instance."""

  task = _load_task(config.task)
  task_manager = task_manager_lib.TaskManager(task)

  match config.simulator:
    case config_classes.EmulatorConfig():
      _process_emulator_launcher_config(config.simulator)
      simulator = emulator_simulator.EmulatorSimulator(config=config.simulator)
    case config_classes.FakeSimulatorConfig():
      simulator = fake_simulator.FakeSimulator(config=config.simulator)
    case _:
      raise ValueError('Unsupported simulator config: {config.simulator}')

  device_settings = device_settings_lib.DeviceSettings(simulator)
  coordinator = coordinator_lib.Coordinator(
      simulator, task_manager, device_settings
  )
  return environment.AndroidEnv(
      simulator=simulator, coordinator=coordinator, task_manager=task_manager
  )


def _process_emulator_launcher_config(
    emulator_config: config_classes.EmulatorConfig,
) -> None:
  """Adjusts the configuration of the emulator depending on some conditions."""

  # Expand the user directory if specified.
  launcher_config = emulator_config.emulator_launcher
  launcher_config.android_avd_home = os.path.expanduser(
      launcher_config.android_avd_home
  )
  launcher_config.android_sdk_root = os.path.expanduser(
      launcher_config.android_sdk_root
  )
  launcher_config.emulator_path = os.path.expanduser(
      launcher_config.emulator_path
  )
  emulator_config.adb_controller.adb_path = os.path.expanduser(
      emulator_config.adb_controller.adb_path
  )
