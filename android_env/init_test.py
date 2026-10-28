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

"""Tests for top-level android_env package exports."""

from absl.testing import absltest
import android_env
from android_env import env_interface
from android_env import loader
from android_env.components import android_device
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.rl import environment as rl_environment


class InitTest(absltest.TestCase):

  def test_version(self):
    self.assertEqual(android_env.__version__, '2.0.0')

  def test_public_exports(self):
    self.assertIs(
        android_env.AdbControllerConfig, config_classes.AdbControllerConfig
    )
    self.assertIs(android_env.AndroidDevice, android_device.AndroidDevice)
    self.assertIs(
        android_env.AndroidDeviceConfig, config_classes.AndroidDeviceConfig
    )
    self.assertIs(android_env.AndroidEnv, rl_environment.AndroidEnv)
    self.assertIs(android_env.AndroidEnvConfig, config_classes.AndroidEnvConfig)
    self.assertIs(
        android_env.AndroidEnvInterface, env_interface.AndroidEnvInterface
    )
    self.assertIs(
        android_env.DeviceConnectionConfig,
        config_classes.DeviceConnectionConfig,
    )
    self.assertIs(
        android_env.EmulatorLauncherConfig,
        config_classes.EmulatorLauncherConfig,
    )
    self.assertIs(
        android_env.FilesystemTaskConfig, config_classes.FilesystemTaskConfig
    )
    self.assertIs(android_env.TaskConfig, config_classes.TaskConfig)
    self.assertIs(android_env.load, loader.load)
    self.assertIs(
        android_env.load_android_device,
        android_device_loader.load_android_device,
    )

  def test_all_exports_present_on_module(self):
    for symbol in android_env.__all__:
      self.assertTrue(hasattr(android_env, symbol), msg=f'Missing {symbol}')


if __name__ == '__main__':
  absltest.main()
