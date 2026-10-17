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

"""Sample open-source emulator configuration for AndroidEnv Playground."""

import os
from android_env.components import config_classes


def get_config(
    avd_name: str = 'androidworld_avd',
) -> config_classes.AndroidDeviceConfig:
  """Returns an AndroidDeviceConfig for open-source emulators and AndroidWorld.

  Args:
    avd_name: Name of the local Android Virtual Device (AVD). Defaults to
      'androidworld_avd', matching the standard AndroidWorld benchmark AVD. Can
      be customized via --config=path/to/emulator_config.py:your_avd_name.

  Returns:
    An AndroidDeviceConfig instance configured for local open-source execution.
  """
  android_home = os.environ.get(
      'ANDROID_HOME', os.path.expanduser('~/Android/Sdk')
  )
  android_avd_home = os.environ.get(
      'ANDROID_AVD_HOME', os.path.expanduser('~/.android/avd')
  )

  return config_classes.AndroidDeviceConfig(
      emulator_launcher=config_classes.EmulatorLauncherConfig(
          avd_name=avd_name,
          android_avd_home=android_avd_home,
          android_sdk_root=android_home,
          emulator_path=os.path.join(android_home, 'emulator', 'emulator'),
          run_headless=True,
      ),
      adb_controller=config_classes.AdbControllerConfig(
          adb_path=os.path.join(android_home, 'platform-tools', 'adb'),
      ),
  )
