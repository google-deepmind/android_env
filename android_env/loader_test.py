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

import builtins
import os
from unittest import mock

from absl.testing import absltest
from android_env import loader
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.proto import task_pb2
from android_env.rl import environment as rl_environment
from android_env.wrappers import task_wrapper


class LoaderTest(absltest.TestCase):

  @mock.patch.object(
      android_device_loader, 'load_android_device', autospec=True
  )
  @mock.patch.object(rl_environment, 'AndroidEnv', autospec=True)
  def test_load_android_device(self, mock_android_env, mock_loader):
    config = config_classes.AndroidEnvConfig(
        simulator=config_classes.AndroidDeviceConfig()
    )
    env = loader.load(config)
    mock_loader.assert_called_once_with(config.simulator)
    mock_android_env.assert_called_once_with(device=mock_loader.return_value)
    self.assertEqual(env, mock_android_env.return_value)

  @mock.patch.object(builtins, 'open', autospec=True)
  @mock.patch.object(
      android_device_loader, 'load_android_device', autospec=True
  )
  @mock.patch.object(rl_environment, 'AndroidEnv', autospec=True)
  @mock.patch.object(task_wrapper, 'TaskWrapper', autospec=True)
  def test_load_android_device_with_task(
      self, mock_task_wrapper, mock_android_env, mock_loader, mock_open
  ):
    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = 'id: "device_task"'
    config = config_classes.AndroidEnvConfig(
        task=config_classes.FilesystemTaskConfig(path='~/some/path.textproto'),
        simulator=config_classes.AndroidDeviceConfig(),
    )
    env = loader.load(config)
    mock_open.assert_any_call(os.path.expanduser('~/some/path.textproto'), 'r')
    mock_loader.assert_called_once_with(config.simulator)
    mock_android_env.assert_called_once_with(device=mock_loader.return_value)
    expected_task = task_pb2.Task(id='device_task')
    mock_task_wrapper.assert_called_once_with(
        mock_android_env.return_value,
        task=expected_task,
        config=config.task_manager,
    )
    self.assertEqual(env, mock_task_wrapper.return_value)

  def test_load_unsupported_simulator_raises(self):
    config = config_classes.AndroidEnvConfig(
        simulator=config_classes.SimulatorConfig()
    )
    with self.assertRaisesRegex(ValueError, 'Unsupported simulator config'):
      loader.load(config)


if __name__ == '__main__':
  absltest.main()
