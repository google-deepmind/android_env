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

"""Tests for loader."""

import builtins
import os
from unittest import mock

from absl.testing import absltest
from android_env import environment
from android_env import loader
from android_env.components import coordinator as coordinator_lib
from android_env.components import task_manager as task_manager_lib
from android_env.components.simulators.emulator import emulator_simulator
from android_env.proto import task_pb2


class LoaderTest(absltest.TestCase):

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(emulator_simulator, 'EmulatorSimulator', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_load(self, mock_open, coordinator, simulator, task_manager):

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
    simulator.assert_called_with(
        adb_controller_args=dict(
            adb_path=os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
            adb_server_port=5037,
        ),
        emulator_launcher_args=dict(
            avd_name='my_avd',
            android_avd_home=os.path.expanduser('~/.android/avd'),
            android_sdk_root=os.path.expanduser('~/Android/Sdk'),
            emulator_path=os.path.expanduser('~/Android/Sdk/emulator/emulator'),
            run_headless=False,
            gpu_mode='swiftshader_indirect'),
    )
    coordinator.assert_called_with(
        simulator.return_value,
        task_manager.return_value,
    )

  @mock.patch.object(task_manager_lib, 'TaskManager', autospec=True)
  @mock.patch.object(emulator_simulator, 'EmulatorSimulator', autospec=True)
  @mock.patch.object(coordinator_lib, 'Coordinator', autospec=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_task(self, mock_open, coordinator, simulator, task_manager):

    del coordinator, simulator
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

    task_manager.assert_called_with(expected_task)
    assert isinstance(env, environment.AndroidEnv)


if __name__ == '__main__':
  absltest.main()
