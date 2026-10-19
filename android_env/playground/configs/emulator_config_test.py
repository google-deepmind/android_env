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

"""Unit tests verifying open-source emulator configuration and environment variables."""

from unittest import mock

from absl.testing import absltest
from android_env.components import config_classes
from android_env.playground.configs import emulator_config


class EmulatorConfigTest(absltest.TestCase):

  def test_get_config_default(self):
    config = emulator_config.get_config()
    self.assertIsInstance(config, config_classes.AndroidDeviceConfig)
    self.assertIsNotNone(config.emulator_launcher)
    self.assertEqual(config.emulator_launcher.avd_name, 'androidworld_avd')
    self.assertTrue(config.emulator_launcher.run_headless)

  def test_get_config_custom_avd(self):
    config = emulator_config.get_config(avd_name='custom_test_avd')
    self.assertIsInstance(config, config_classes.AndroidDeviceConfig)
    self.assertIsNotNone(config.emulator_launcher)
    self.assertEqual(config.emulator_launcher.avd_name, 'custom_test_avd')

  def test_get_config_environment_variables(self):
    with mock.patch.dict(
        emulator_config.os.environ,
        {
            'ANDROID_HOME': '/custom/android/home',
            'ANDROID_AVD_HOME': '/custom/avd/home',
        },
    ):
      config = emulator_config.get_config()
      self.assertIsInstance(config, config_classes.AndroidDeviceConfig)
      self.assertIsNotNone(config.emulator_launcher)
      self.assertIsNotNone(config.adb_controller)
      launcher = config.emulator_launcher
      self.assertEqual(launcher.android_sdk_root, '/custom/android/home')
      self.assertEqual(launcher.android_avd_home, '/custom/avd/home')
      self.assertEqual(
          launcher.emulator_path, '/custom/android/home/emulator/emulator'
      )
      self.assertEqual(
          config.adb_controller.adb_path,
          '/custom/android/home/platform-tools/adb',
      )


if __name__ == '__main__':
  absltest.main()
