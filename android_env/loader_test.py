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
from android_env import env_interface
from android_env import loader
from android_env.components import config_classes
from android_env.components import coordinator as coordinator_lib
from android_env.components import device_settings as device_settings_lib
from android_env.components import task_manager as task_manager_lib
from android_env.components.simulators.emulator import emulator_simulator
from android_env.components.simulators.fake import fake_simulator
from android_env.proto import task_pb2


class LoaderTest(absltest.TestCase):

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(emulator_simulator, 'EmulatorSimulator', autospec=True)
  @mock.patch.object(device_settings_lib, 'DeviceSettings', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_load_emulator(
      self,
      mock_open,
      mock_coordinator,
      mock_device_settings,
      mock_simulator_class,
      mock_task_manager,
  ):

    # Arrange.
    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = ''
    config = config_classes.AndroidEnvConfig(
        task=config_classes.FilesystemTaskConfig(path='some/path/'),
        simulator=config_classes.EmulatorConfig(
            emulator_launcher=config_classes.EmulatorLauncherConfig(
                avd_name='my_avd',
                android_avd_home='~/.android/avd',
                android_sdk_root='~/Android/Sdk',
                emulator_path='~/Android/Sdk/emulator/emulator',
                run_headless=False,
            ),
            adb_controller=config_classes.AdbControllerConfig(
                adb_path='~/Android/Sdk/platform-tools/adb',
            ),
        ),
    )

    # Act.
    env = loader.load(config)

    # Assert.
    self.assertIsInstance(env, env_interface.AndroidEnvInterface)
    mock_simulator_class.assert_called_with(
        config=config_classes.EmulatorConfig(
            emulator_launcher=config_classes.EmulatorLauncherConfig(
                avd_name='my_avd',
                android_avd_home=os.path.expanduser('~/.android/avd'),
                android_sdk_root=os.path.expanduser('~/Android/Sdk'),
                emulator_path=os.path.expanduser(
                    '~/Android/Sdk/emulator/emulator'
                ),
                run_headless=False,
                gpu_mode='swangle_indirect',
            ),
            adb_controller=config_classes.AdbControllerConfig(
                adb_path=os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
                adb_server_port=5037,
            ),
        )
    )
    mock_coordinator.assert_called_with(
        mock_simulator_class.return_value,
        mock_task_manager.return_value,
        mock_device_settings.return_value,
    )

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(fake_simulator, 'FakeSimulator', autospec=True)
  @mock.patch.object(device_settings_lib, 'DeviceSettings', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_load_fake_simulator(
      self,
      mock_open,
      mock_coordinator,
      mock_device_settings,
      mock_simulator_class,
      mock_task_manager,
  ):

    # Arrange.
    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = ''
    config = config_classes.AndroidEnvConfig(
        task=config_classes.FilesystemTaskConfig(path='some/path/'),
        simulator=config_classes.FakeSimulatorConfig(
            screen_dimensions=(1234, 5678)
        ),
    )

    # Act.
    env = loader.load(config)

    # Assert.
    self.assertIsInstance(env, env_interface.AndroidEnvInterface)
    mock_simulator_class.assert_called_with(
        config=config_classes.FakeSimulatorConfig(
            screen_dimensions=(1234, 5678)
        )
    )
    mock_coordinator.assert_called_with(
        mock_simulator_class.return_value,
        mock_task_manager.return_value,
        mock_device_settings.return_value,
    )

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(emulator_simulator, 'EmulatorSimulator', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_task(
      self, mock_open, mock_coordinator, mock_simulator, mock_task_manager
  ):

    # Arrange.
    del mock_coordinator, mock_simulator
    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = r'''
id: "fake_task"
name: "Fake Task"
description: "Task for testing loader."
max_episode_sec: 0
'''
    config = config_classes.AndroidEnvConfig(
        task=config_classes.FilesystemTaskConfig(path='some/path/'),
        simulator=config_classes.EmulatorConfig(
            emulator_launcher=config_classes.EmulatorLauncherConfig(
                avd_name='my_avd'
            ),
            adb_controller=config_classes.AdbControllerConfig(
                adb_path='~/Android/Sdk/platform-tools/adb',
            ),
        ),
    )

    # Act.
    env = loader.load(config)

    # Assert.
    expected_task = task_pb2.Task()
    expected_task.id = 'fake_task'
    expected_task.name = 'Fake Task'
    expected_task.description = 'Task for testing loader.'
    expected_task.max_episode_sec = 0

    mock_task_manager.assert_called_with(expected_task)
    self.assertIsInstance(env, env_interface.AndroidEnvInterface)


if __name__ == '__main__':
  absltest.main()
