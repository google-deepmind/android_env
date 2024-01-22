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

"""Tests for loader."""

import builtins
import os
from unittest import mock

from absl.testing import absltest
from android_env import environment
from android_env import loader
from android_env.components import config_classes
from android_env.components import coordinator as coordinator_lib
from android_env.components import task_manager as task_manager_lib
from android_env.components.simulators.emulator import emulator_simulator
from android_env.proto import task_pb2


class LoaderTest(absltest.TestCase):

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(emulator_simulator, 'EmulatorSimulator', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_load(
      self, mock_open, mock_coordinator, mock_simulator_class, mock_task_manager
  ):

    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = ''

    env = loader.load(
        task_path='some/path/',
        avd_name='my_avd',
        android_avd_home='~/.android/avd',
        android_sdk_root='~/Android/Sdk',
        emulator_path='~/Android/Sdk/emulator/emulator',
        adb_path='~/Android/Sdk/platform-tools/adb',
        run_headless=False,
    )

    self.assertIsInstance(env, environment.AndroidEnv)
    mock_simulator_class.assert_called_with(
        emulator_launcher_config=config_classes.EmulatorLauncherConfig(
            avd_name='my_avd',
            android_avd_home=os.path.expanduser('~/.android/avd'),
            android_sdk_root=os.path.expanduser('~/Android/Sdk'),
            emulator_path=os.path.expanduser('~/Android/Sdk/emulator/emulator'),
            run_headless=False,
            gpu_mode='swiftshader_indirect',
        ),
        adb_controller_config=config_classes.AdbControllerConfig(
            adb_path=os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
            adb_server_port=5037,
        ),
    )
    mock_coordinator.assert_called_with(
        mock_simulator_class.return_value,
        mock_task_manager.return_value,
    )

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(emulator_simulator, 'EmulatorSimulator', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_load_existing_device(
      self, mock_open, mock_coordinator, mock_simulator_class, mock_task_manager
  ):
    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = ''

    env = loader.load(
        task_path='some/path/',
        console_port=5554,
        adb_path='~/Android/Sdk/platform-tools/adb',
    )

    self.assertIsInstance(env, environment.AndroidEnv)
    mock_simulator_class.assert_called_with(
        emulator_launcher_config=config_classes.EmulatorLauncherConfig(
            emulator_console_port=5554, adb_port=5555, grpc_port=8554
        ),
        adb_controller_config=config_classes.AdbControllerConfig(
            adb_path=os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
            adb_server_port=5037,
        ),
    )
    mock_coordinator.assert_called_with(
        mock_simulator_class.return_value,
        mock_task_manager.return_value,
    )

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(emulator_simulator, 'EmulatorSimulator', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_task(
      self, mock_open, mock_coordinator, mock_simulator, mock_task_manager
  ):
    del mock_coordinator, mock_simulator
    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = r'''
id: "fake_task"
name: "Fake Task"
description: "Task for testing loader."
max_episode_sec: 0
'''

    env = loader.load(
        task_path='some/path/',
        avd_name='my_avd',
    )

    expected_task = task_pb2.Task()
    expected_task.id = 'fake_task'
    expected_task.name = 'Fake Task'
    expected_task.description = 'Task for testing loader.'
    expected_task.max_episode_sec = 0

    mock_task_manager.assert_called_with(expected_task)
    assert isinstance(env, environment.AndroidEnv)


if __name__ == '__main__':
  absltest.main()
