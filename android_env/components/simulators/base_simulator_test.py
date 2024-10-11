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

import itertools
import time
from unittest import mock

from absl.testing import absltest
from android_env.components import config_classes
from android_env.components import errors
# fake_simulator.FakeSimulator inherits from BaseSimulator, so there's no need
# to import it here explicitly.
from android_env.components.simulators import base_simulator
from android_env.components.simulators.fake import fake_simulator
import numpy as np


class BaseSimulatorTest(absltest.TestCase):

  def test_launch(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(640, 480))
    )
    # The simulator should launch and not crash.
    simulator.launch()

  def test_launch_close(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig()
    )
    # The simulator should launch and not crash.
    simulator.launch()
    # Closing the simulator should also not crash.
    simulator.close()

  def test_get_screenshot(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(640, 480))
    )
    # The simulator should launch and not crash.
    simulator.launch()

    screenshot = simulator.get_screenshot()
    np.testing.assert_equal(screenshot.shape, [640, 480, 3])

  def test_print_logs_on_exception(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig()
    )
    with mock.patch.object(
        simulator, 'get_logs'
    ) as mock_get_logs, mock.patch.object(
        simulator, '_launch_impl', autospec=True
    ) as mock_launch:
      mock_launch.side_effect = ValueError('Oh no!')
      self.assertRaises(errors.SimulatorError, simulator.launch)
      mock_get_logs.assert_called_once()

  def test_get_screenshot_error_async(self):
    """An exception in the underlying interaction thread should bubble up."""

    # Arrange.
    mock_interaction_thread = mock.create_autospec(
        base_simulator.InteractionThread
    )
    mock_interaction_thread.screenshot.side_effect = (
        errors.ReadObservationError()
    )
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(interaction_rate_sec=0.5)
    )
    with mock.patch.object(
        base_simulator,
        'InteractionThread',
        autospec=True,
        return_value=mock_interaction_thread,
    ):
      simulator.launch()

    # Act & Assert.
    self.assertRaises(errors.ReadObservationError, simulator.get_screenshot)

    # Cleanup.
    simulator.close()

  def test_get_screenshot_faster_than_screenshot_impl(self):
    """Return same screenshot when step is faster than the interaction rate."""

    # Arrange.
    slow_rate = 0.5
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(interaction_rate_sec=slow_rate)
    )

    # Act.
    with mock.patch.object(
        simulator, '_get_screenshot_impl', autospec=True
    ) as mock_get_screenshot_impl:
      mock_get_screenshot_impl.side_effect = (
          np.array(i, ndmin=3) for i in itertools.count(0, 1)
      )
      simulator.launch()
      # Get two screenshots one after the other without pausing.
      screenshot1 = simulator.get_screenshot()
      screenshot2 = simulator.get_screenshot()

    # Assert.
    self.assertAlmostEqual(screenshot1[0][0][0], screenshot2[0][0][0])

    # Cleanup.
    simulator.close()

  def test_get_screenshot_slower_than_screenshot_impl(self):
    """Return different screenshots when step slower than the interaction rate."""

    # Arrange.
    fast_rate = 0.01
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(interaction_rate_sec=fast_rate)
    )

    # Act.
    with mock.patch.object(
        simulator, '_get_screenshot_impl', autospec=True
    ) as mock_get_screenshot_impl:
      mock_get_screenshot_impl.side_effect = (
          np.array(i, ndmin=3) for i in itertools.count(0, 1)
      )
      simulator.launch()
      # Sleep for 500ms between two screenshots.
      screenshot1 = simulator.get_screenshot()
      time.sleep(0.5)
      screenshot2 = simulator.get_screenshot()

    # Assert.
    self.assertNotEqual(screenshot1[0][0][0], screenshot2[0][0][0])

    # Cleanup.
    simulator.close()

  def test_interaction_thread_closes_upon_relaunch(self):
    """Async interaction should kill the InteractionThread when relaunching."""

    # Arrange.
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(interaction_rate_sec=0.01)
    )
    mock_interaction_thread = mock.create_autospec(
        base_simulator.InteractionThread
    )

    # Act & Assert.
    with mock.patch.object(
        base_simulator,
        'InteractionThread',
        autospec=True,
        return_value=mock_interaction_thread,
    ):
      simulator.launch()
      mock_interaction_thread.stop.assert_not_called()
      mock_interaction_thread.join.assert_not_called()
      simulator.launch()
      mock_interaction_thread.stop.assert_called_once()
      mock_interaction_thread.join.assert_called_once()
      simulator.close()


if __name__ == '__main__':
  absltest.main()
