# coding=utf-8
# Copyright 2021 DeepMind Technologies Limited.
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

"""Tests for fake_simulator."""

from absl.testing import absltest
from android_env.components.simulators.fake import fake_simulator
import numpy as np


class FakeSimulatorTest(absltest.TestCase):

  def test_device_name(self):
    simulator = fake_simulator.FakeSimulator(screen_dimensions=(320, 480))
    self.assertEqual(simulator.adb_device_name(), 'fake_simulator')

  def test_launch_close(self):
    # The simulator should launch and not crash.
    simulator = fake_simulator.FakeSimulator(screen_dimensions=(320, 480))
    simulator.launch()
    # After a successful launch(), screen_dimensions() should return something.
    np.testing.assert_equal(simulator.screen_dimensions(), [320, 480])
    # Closing the simulator should also not crash.
    simulator.close()

  def test_get_observation(self):
    simulator = fake_simulator.FakeSimulator(screen_dimensions=(320, 480))
    simulator.launch()

    observation = simulator.get_observation()
    np.testing.assert_equal(
        observation['pixels'].shape, [320, 480, 3])
    np.testing.assert_array_equal(
        observation['pixels'], np.zeros((320, 480, 3), dtype=np.uint8))
    np.testing.assert_equal(
        observation['timedelta'].dtype, np.int64)
    np.testing.assert_array_equal(
        observation['orientation'], np.zeros((4,), dtype=np.uint8))

  def test_log_stream(self):
    simulator = fake_simulator.FakeSimulator(screen_dimensions=(320, 480))
    simulator.launch()
    log_stream = simulator.get_log_stream()
    lines = [
        '',
        '         1553110400.424  5583  5658 D Tag: reward: 0.5',
        '         1553110400.424  5583  5658 D Tag: reward: 1.0',
        '         1553110400.424  5583  5658 D Tag: extra: my_extra: [1.0]',
        '         1553110400.424  5583  5658 D Tag: episode end',
    ]
    for i, line in enumerate(log_stream.get_stream_output()):
      self.assertIn(line, lines)
      if i > 10:
        break

if __name__ == '__main__':
  absltest.main()
