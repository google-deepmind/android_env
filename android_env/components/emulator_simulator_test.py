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

"""Tests for android_env.components.emulator_simulator."""

from absl.testing import absltest
from android_env.components import action_type
from android_env.components import adb_controller
from android_env.components import emulator_launcher
from android_env.components import emulator_simulator
from android_env.proto import emulator_controller_pb2
from android_env.proto import emulator_controller_pb2_grpc

import grpc
import mock
import numpy as np
from PIL import Image


class EmulatorSimulatorTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._adb_controller = mock.create_autospec(adb_controller.AdbController)
    self._launcher = mock.create_autospec(emulator_launcher.EmulatorLauncher)
    self._emulator_stub = mock.create_autospec(
        emulator_controller_pb2_grpc.EmulatorControllerStub)
    self._grpc_channel = mock.create_autospec(grpc.Channel)

    mock.patch.object(
        adb_controller, 'AdbController',
        return_value=self._adb_controller).start()
    mock.patch.object(
        emulator_launcher, 'EmulatorLauncher',
        return_value=self._launcher).start()

  @mock.patch('grpc.aio.insecure_channel')
  @mock.patch('grpc.insecure_channel')
  def test_adb_device_name_not_empty(self, aio_channel, channel):
    tmp_dir = absltest.get_default_test_tmpdir()
    aio_channel.return_value = self._grpc_channel
    channel.return_value = self._grpc_channel
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={'grpc_port': 1234},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')
    self.assertNotEmpty(simulator.adb_device_name())

  @mock.patch('grpc.aio.insecure_channel')
  @mock.patch('grpc.insecure_channel')
  def test_close(self, aio_channel, channel):
    tmp_dir = absltest.get_default_test_tmpdir()
    aio_channel.return_value = self._grpc_channel
    channel.return_value = self._grpc_channel
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={'grpc_port': 1234},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    simulator.launch()

    # For whatever reason clients may want to close the EmulatorSimulator.
    # We just want to check that the simulator does not crash and/or leak
    # resources.
    simulator.close()

  @mock.patch('grpc.aio.insecure_channel')
  @mock.patch('grpc.insecure_channel')
  def test_restart(self, aio_channel, channel):
    tmp_dir = absltest.get_default_test_tmpdir()
    aio_channel.return_value = self._grpc_channel
    channel.return_value = self._grpc_channel
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={'grpc_port': 1234},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    simulator.launch()

    # For whatever reason clients may want to restart the EmulatorSimulator.
    simulator.restart()

  @mock.patch('grpc.aio.insecure_channel')
  @mock.patch('grpc.insecure_channel')
  def test_get_observation(self, aio_channel, channel):
    tmp_dir = absltest.get_default_test_tmpdir()
    aio_channel.return_value = self._grpc_channel
    channel.return_value = self._grpc_channel
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={'grpc_port': 1234},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    simulator.launch()

    simulator._emulator_stub.getScreenshot = mock.MagicMock(
        return_value=emulator_controller_pb2.Image(
            format=emulator_controller_pb2.ImageFormat(width=5678, height=1234),
            image=Image.new('RGB', (1234, 5678)).tobytes(),
            timestampUs=123))

    observation = simulator.get_observation()
    # The observation should have three components:
    #   - an image
    #   - the timedelta
    #   - the orientation.
    self.assertLen(observation, 3)
    # The first element (the "image") should have the same screen dimensions as
    # reported by ADB and it should have 3 channels (RGB).
    self.assertEqual(observation['pixels'].shape, (1234, 5678, 3))
    self.assertEqual(observation['timedelta'], 123)

  @mock.patch('grpc.aio.insecure_channel')
  @mock.patch('grpc.insecure_channel')
  def test_send_action(self, aio_channel, channel):
    tmp_dir = absltest.get_default_test_tmpdir()
    aio_channel.return_value = self._grpc_channel
    channel.return_value = self._grpc_channel
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={'grpc_port': 1234},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (5000, 1000)
    simulator.launch()

    simulator._emulator_stub.sendTouch = mock.MagicMock(return_value=None)

    simulator.send_action(
        {'action_type': np.array([action_type.ActionType.TOUCH]),
         'touch_position': np.array([0.25, 0.75])})
    simulator.send_action(
        {'action_type': np.array([action_type.ActionType.TOUCH]),
         'touch_position': np.array([0.75, 0.50])})
    simulator.send_action(
        {'action_type': np.array([action_type.ActionType.LIFT]),
         'touch_position': np.array([0.66, 0.33])})
    # We expect EmulatorSimulator to send the following calls:
    # 1st call:
    #     x-coordinate: 10000 * 0.25 = 250
    #     y-coordinate: 50000 * 0.75 = 3750
    #     down: True  # It's a touch command.
    # 2nd call:
    #     x-coordinate: 10000 * 0.75 = 750
    #     y-coordinate: 50000 * 0.50 = 2500
    #     down: True  # It's a touch command.
    # 3rd call:
    #     x-coordinate: 0
    #     y-coordinate: 0
    #     down: False  # It's a lift command.

if __name__ == '__main__':
  absltest.main()
