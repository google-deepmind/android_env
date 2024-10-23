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

from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import config_classes
from android_env.components import device_settings as device_settings_lib
from android_env.components.simulators import base_simulator
import numpy as np


class DeviceSettingsTest(parameterized.TestCase):

  def test_screen_size_before_update(self):
    """The screen size should be 0x0 without calling `update()`."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    device_settings = device_settings_lib.DeviceSettings(simulator)

    # Act.
    height = device_settings.screen_height()
    width = device_settings.screen_width()

    # Assert.
    self.assertEqual(height, 0)
    self.assertEqual(width, 0)

  def test_screen_size_after_update(self):
    """The screen size should be set after calling `update()`."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    simulator.get_screenshot.return_value = np.random.randint(
        low=0, high=255, size=(123, 456, 3), dtype=np.uint8
    )
    adb_controller = simulator.create_adb_controller.return_value
    adb_controller.execute_command.return_value = b''
    device_settings = device_settings_lib.DeviceSettings(simulator)

    # Act.
    device_settings.update(config_classes.DeviceSettingsConfig())
    height = device_settings.screen_height()
    width = device_settings.screen_width()

    # Assert.
    self.assertEqual(height, 123)
    self.assertEqual(width, 456)

  @parameterized.named_parameters(
      (
          'show_touches',
          config_classes.DeviceSettingsConfig(show_touches=True),
          mock.call(
              ['shell', 'settings', 'put', 'system', 'show_touches', '1'],
              timeout=None,
          ),
      ),
      (
          'show_touches_false',
          config_classes.DeviceSettingsConfig(show_touches=False),
          mock.call(
              ['shell', 'settings', 'put', 'system', 'show_touches', '0'],
              timeout=None,
          ),
      ),
      (
          'show_pointer_location',
          config_classes.DeviceSettingsConfig(show_pointer_location=True),
          mock.call(
              ['shell', 'settings', 'put', 'system', 'pointer_location', '1'],
              timeout=None,
          ),
      ),
      (
          'show_pointer_location_false',
          config_classes.DeviceSettingsConfig(show_pointer_location=False),
          mock.call(
              ['shell', 'settings', 'put', 'system', 'pointer_location', '0'],
              timeout=None,
          ),
      ),
      (
          'show_navigation_and_status',
          config_classes.DeviceSettingsConfig(
              show_navigation_bar=True, show_status_bar=True
          ),
          mock.call(
              ['shell', 'settings', 'put', 'global', 'policy_control', 'null*'],
              timeout=None,
          ),
      ),
      (
          'show_navigation_and_no_status',
          config_classes.DeviceSettingsConfig(
              show_navigation_bar=True, show_status_bar=False
          ),
          mock.call(
              [
                  'shell',
                  'settings',
                  'put',
                  'global',
                  'policy_control',
                  'immersive.status=*',
              ],
              timeout=None,
          ),
      ),
      (
          'show_no_navigation_and_status',
          config_classes.DeviceSettingsConfig(
              show_navigation_bar=False, show_status_bar=True
          ),
          mock.call(
              [
                  'shell',
                  'settings',
                  'put',
                  'global',
                  'policy_control',
                  'immersive.navigation=*',
              ],
              timeout=None,
          ),
      ),
      (
          'show_no_navigation_and_no_status',
          config_classes.DeviceSettingsConfig(
              show_navigation_bar=False, show_status_bar=False
          ),
          mock.call(
              [
                  'shell',
                  'settings',
                  'put',
                  'global',
                  'policy_control',
                  'immersive.full=*',
              ],
              timeout=None,
          ),
      ),
  )
  def test_update(
      self, settings: config_classes.DeviceSettingsConfig, expected_call
  ):
    """We expect the right call for each setting."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    adb_controller = simulator.create_adb_controller.return_value
    adb_controller.execute_command.return_value = b''
    device_settings = device_settings_lib.DeviceSettings(simulator)

    # Act.
    device_settings.update(settings)

    # Assert.
    adb_controller.execute_command.assert_has_calls(
        [expected_call], any_order=True
    )

  def test_get_orientation_bad_response(self):
    """The orientation should be unset if the underlying response is bad."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    adb_controller = simulator.create_adb_controller.return_value
    adb_controller.execute_command.return_value = b''
    device_settings = device_settings_lib.DeviceSettings(simulator)

    # Act.
    orientation = device_settings.get_orientation()

    # Assert.
    np.testing.assert_array_equal(orientation, np.zeros(4))

  def test_get_orientation_bad_orientation(self):
    """The orientation should be unset if the underlying orientation is bad."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    adb_controller = simulator.create_adb_controller.return_value
    adb_controller.execute_command.return_value = b' InputDeviceOrientation: 9'
    device_settings = device_settings_lib.DeviceSettings(simulator)

    # Act.
    orientation = device_settings.get_orientation()

    # Assert.
    np.testing.assert_array_equal(orientation, np.zeros(4))

  def test_get_orientation_success(self):
    """Checks that the orientation comes back as expected."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    adb_controller = simulator.create_adb_controller.return_value
    adb_controller.execute_command.return_value = b' InputDeviceOrientation: 3'
    device_settings = device_settings_lib.DeviceSettings(simulator)

    # Act.
    orientation = device_settings.get_orientation()
    # The output should be idempotent if the underlying system did not change.
    orientation_again = device_settings.get_orientation()

    # Assert.
    np.testing.assert_array_equal(orientation, np.array([0, 0, 0, 1]))
    np.testing.assert_array_equal(orientation, orientation_again)


if __name__ == '__main__':
  absltest.main()
