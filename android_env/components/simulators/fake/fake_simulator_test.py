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

"""Tests for fake_simulator."""

import re
from absl.testing import absltest
from android_env.components import config_classes
from android_env.components.simulators.fake import fake_simulator
import numpy as np


class FakeSimulatorTest(absltest.TestCase):

  def test_device_name(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(320, 480))
    )
    self.assertEqual(simulator.adb_device_name(), 'fake_simulator')

  def test_launch_close(self):
    # The simulator should launch and not crash.
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(320, 480))
    )
    simulator.launch()
    # Closing the simulator should also not crash.
    simulator.close()

  def test_get_screenshot(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(320, 480))
    )
    simulator.launch()

    screenshot = simulator.get_screenshot()
    np.testing.assert_equal(screenshot.shape, [320, 480, 3])
    np.testing.assert_equal(screenshot.dtype, np.uint8)

  def test_log_stream(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(320, 480))
    )
    simulator.launch()
    log_stream = simulator.create_log_stream()
    # Start yielding lines from LogStream.
    log_stream.resume_stream()
    lines = [
        '',
        '         1553110400.424  5583  5658 D Tag: reward: 0.5',
        '         1553110400.424  5583  5658 D Tag: reward: 1.0',
        '         1553110400.424  5583  5658 D Tag: extra: my_extra [1.0]',
        '         1553110400.424  5583  5658 D Tag: episode end',
    ]
    for i, line in enumerate(log_stream.get_stream_output()):
      self.assertIn(line, lines)
      if i > 10:
        break

  def test_adb_output(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(320, 480))
    )
    simulator.launch()
    adb_controller = simulator.create_adb_controller()
    line = adb_controller.execute_command(['shell', 'dumpsys', 'input'])
    line = line.decode('utf-8')
    matches = re.match(r'\s+SurfaceOrientation:\s+(\d)', line)
    self.assertIsNotNone(matches)
    orientation = matches.group(1)
    self.assertEqual(orientation, '0')
    line = adb_controller.execute_command(['shell', 'service', 'check', 'foo'])
    line = line.decode('utf-8')
    self.assertEqual(line, 'Service foo: found')
    line = adb_controller.execute_command(['shell', 'am', 'stack', 'list'])
    line = line.decode('utf-8')
    self.assertEqual(line, 'taskId=0 fake_activity visible=true '
                     'topActivity=ComponentInfo{fake_activity}')

  def test_send_touch(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(320, 480))
    )
    simulator.launch()
    simulator.send_touch([(0, 1, True, 0)])
    simulator.send_touch([(0, 1, False, 0)])
    # No assertions, we just want to ensure that `send_touch()` can be called
    # without crashing anything.

  def test_send_key(self):
    simulator = fake_simulator.FakeSimulator(
        config_classes.FakeSimulatorConfig(screen_dimensions=(320, 480))
    )
    simulator.launch()
    simulator.send_key(np.int32(123), 'keydown')
    simulator.send_key(np.int32(123), 'keyup')
    simulator.send_key(np.int32(123), 'keypress')
    # No assertions, we just want to ensure that `send_key()` can be called
    # without crashing anything.

if __name__ == '__main__':
  absltest.main()
