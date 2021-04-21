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

"""Function for loading AndroidEnv."""

import os

from android_env import android_env
from android_env.components import coordinator as coordinator_lib
from android_env.components import emulator_simulator
from android_env.components import task_manager as task_manager_lib
from android_env.proto import task_pb2

from google.protobuf import text_format


def load(task_path: str,
         avd_name: str,
         android_avd_home: str = '~/.android/avd',
         android_sdk_root: str = '~/Android/Sdk',
         emulator_path: str = '~/Android/Sdk/emulator/emulator',
         adb_path: str = '~/Android/Sdk/platform-tools/adb',
         run_headless: bool = False) -> android_env.AndroidEnv:
  """Loads an AndroidEnv instance.

  Args:
    task_path: Path to the task textproto file.
    avd_name: Name of the AVD (Android Virtual Device).
    android_avd_home: Path to the AVD (Android Virtual Device).
    android_sdk_root: Root directory of the SDK.
    emulator_path: Path to the emulator binary.
    adb_path: Path to the ADB (Android Debug Bridge).
    run_headless: If True, the emulator display is turned off.
  Returns:
    env: An AndroidEnv instance.
  """

  # Create simulator.
  simulator = emulator_simulator.EmulatorSimulator(
      emulator_launcher_args=dict(
          avd_name=avd_name,
          android_avd_home=os.path.expanduser(android_avd_home),
          android_sdk_root=os.path.expanduser(android_sdk_root),
          emulator_path=os.path.expanduser(emulator_path),
          run_headless=run_headless,
          gpu_mode='swiftshader_indirect',
          grpc_port=-1,
      ),
      emulator_console_args={},
      adb_path=os.path.expanduser(adb_path),
      adb_server_port=5037,
      prompt_regex=r'\w*:\/ \$',
  )

  # Prepare task.
  task = task_pb2.Task()
  with open(task_path, 'r') as proto_file:
    text_format.Parse(proto_file.read(), task)

  task_manager = task_manager_lib.TaskManager(task)
  coordinator = coordinator_lib.Coordinator(simulator, task_manager)

  # Load environment.
  return android_env.AndroidEnv(
      simulator=simulator,
      task=task,
      task_manager=task_manager,
      coordinator=coordinator,
  )
