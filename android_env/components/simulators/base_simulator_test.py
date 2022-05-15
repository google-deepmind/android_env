# coding=utf-8
# Copyright 2022 DeepMind Technologies Limited.
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

"""Tests for base_simulator."""

from unittest import mock

from absl.testing import absltest
from android_env.components import action_type
from android_env.components import adb_controller
# fake_simulator.FakeSimulator inherits from BaseSimulator, so there's no need
# to import it here explicitly.
from android_env.components.simulators.fake import fake_simulator
import numpy as np


class BaseSimulatorTest(absltest.TestCase):

  def test_launch(self):
    simulator = fake_simulator.FakeSimulator(screen_dimensions=(640, 480))
    # The simulator should launch and not crash.
    simulator.launch()

  def test_launch_close(self):
    simulator = fake_simulator.FakeSimulator()
    # The simulator should launch and not crash.
    simulator.launch()
    # Closing the simulator should also not crash.
    simulator.close()

  def test_get_screenshot(self):
    simulator = fake_simulator.FakeSimulator(screen_dimensions=(640, 480))
    # The simulator should launch and not crash.
    simulator.launch()

    screenshot = simulator.get_screenshot()
    np.testing.assert_equal(screenshot.shape, [640, 480, 3])

  def test_print_logs_on_exception(self):
    simulator = fake_simulator.FakeSimulator()
    with mock.patch.object(simulator, 'get_logs') as mock_get_logs, \
         mock.patch.object(simulator, '_launch_impl', autospec=True) as mock_launch:
      mock_launch.side_effect = ValueError('Oh no!')
      self.assertRaises(ValueError, simulator.launch)
      mock_get_logs.assert_called_once()

if __name__ == '__main__':
  absltest.main()
