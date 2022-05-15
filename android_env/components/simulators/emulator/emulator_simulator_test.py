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

"""Tests for android_env.components.emulator_simulator."""

import builtins
import os
import time
from unittest import mock

from absl.testing import absltest
from android_env.components import adb_call_parser
from android_env.components import adb_controller
from android_env.components.simulators.emulator import emulator_launcher
from android_env.components.simulators.emulator import emulator_simulator
import grpc
from PIL import Image

from android_env.proto import emulator_controller_pb2
from android_env.proto import emulator_controller_pb2_grpc


class EmulatorSimulatorTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._adb_controller = mock.create_autospec(adb_controller.AdbController)
    self._adb_call_parser = mock.create_autospec(adb_call_parser.AdbCallParser)
    self._launcher = mock.create_autospec(emulator_launcher.EmulatorLauncher)
    self._launcher.logfile_path.return_value = 'logfile_path'
    self._emulator_stub = mock.create_autospec(
        emulator_controller_pb2_grpc.EmulatorControllerStub)

    self._grpc_channel = mock.create_autospec(grpc.Channel)
    mock.patch.object(
        grpc.aio, 'secure_channel',
        return_value=self._grpc_channel).start()
    mock.patch.object(
        grpc, 'secure_channel',
        return_value=self._grpc_channel).start()
    mock.patch.object(
        grpc, 'local_channel_credentials',
        return_value=self._grpc_channel).start()
    self._mock_future = mock.create_autospec(grpc.Future)
    mock.patch.object(
        grpc, 'channel_ready_future',
        return_value=self._mock_future).start()
    mock.patch.object(
        time, 'time',
        return_value=12345).start()

    mock.patch.object(
        adb_controller, 'AdbController',
        return_value=self._adb_controller).start()
    mock.patch.object(
        adb_call_parser,
        'AdbCallParser',
        autospec=True,
        return_value=self._adb_call_parser).start()
    mock.patch.object(
        emulator_launcher, 'EmulatorLauncher',
        return_value=self._launcher).start()

  def test_adb_device_name_not_empty(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        tmp_dir=tmp_dir,
        emulator_launcher_args={'grpc_port': 1234},
        adb_controller_args={
            'adb_path': '/my/adb',
            'adb_server_port': 5037,
        })
    self.assertNotEmpty(simulator.adb_device_name())

  @mock.patch.object(os.path, 'exists', autospec=True, return_value=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_logfile_path(self, mock_open, unused_mock_exists):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        tmp_dir=tmp_dir,
        logfile_path='fake/logfile/path',
        emulator_launcher_args={'grpc_port': 1234},
        adb_controller_args={
            'adb_path': '/my/adb',
            'adb_server_port': 5037,
        })
    mock_open.return_value.__enter__.return_value.read.return_value = (
        'fake_logs'.encode('utf-8'))
    logs = simulator.get_logs()
    mock_open.assert_called_once_with('fake/logfile/path', 'rb')
    self.assertEqual(logs, 'fake_logs')

  def test_launch(self):

    # Make sure that adb_controller is started before Emulator is launched.
    call_order = []
    self._adb_controller.init_server.side_effect = (
        lambda *a, **kw: call_order.append('init_server'))
    self._launcher.launch_emulator_process.side_effect = (
        lambda *a, **kw: call_order.append('launch_emulator_process'))

    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        tmp_dir=tmp_dir,
        emulator_launcher_args={'grpc_port': 1234},
        adb_controller_args={
            'adb_path': '/my/adb',
            'adb_server_port': 5037,
            'prompt_regex': 'awesome>',
        })

    # The simulator should launch and not crash.
    simulator.launch()

    self.assertEqual(call_order, ['init_server', 'launch_emulator_process'])

  def test_close(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        tmp_dir=tmp_dir,
        emulator_launcher_args={'grpc_port': 1234},
        adb_controller_args={
            'adb_path': '/my/adb',
            'adb_server_port': 5037,
        })

    # The simulator should launch and not crash.
    simulator.launch()

    # For whatever reason clients may want to close the EmulatorSimulator.
    # We just want to check that the simulator does not crash and/or leak
    # resources.
    simulator.close()

  def test_restart(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        tmp_dir=tmp_dir,
        emulator_launcher_args={'grpc_port': 1234},
        adb_controller_args={
            'adb_path': '/my/adb',
            'adb_server_port': 5037,
        })

    # The simulator should launch and not crash.
    simulator.launch()

    self._launcher.launch_emulator_process.assert_called_once()
    self._launcher.reset_mock()

    # For whatever reason clients may want to restart the EmulatorSimulator.
    simulator.restart()
    self._launcher.confirm_shutdown.assert_called_once()
    self._launcher.launch_emulator_process.assert_called_once()

  def test_get_screenshot(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        tmp_dir=tmp_dir,
        emulator_launcher_args={'grpc_port': 1234},
        adb_controller_args={
            'adb_path': '/my/adb',
            'adb_server_port': 5037,
        })

    # The simulator should launch and not crash.
    simulator.launch()

    simulator._emulator_stub.getScreenshot = mock.MagicMock(
        return_value=emulator_controller_pb2.Image(
            format=emulator_controller_pb2.ImageFormat(width=5678, height=1234),
            image=Image.new('RGBA', (1234, 5678)).tobytes(),
            timestampUs=123))

    screenshot = simulator.get_screenshot()
    # The screenshot should have the same screen dimensions as reported by ADB
    # and it should have 3 channels (RGB).
    self.assertEqual(screenshot.shape, (1234, 5678, 3))

  def test_send_touch(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        tmp_dir=tmp_dir,
        emulator_launcher_args={'grpc_port': 1234},
        adb_controller_args={
            'adb_path': '/my/adb',
            'adb_server_port': 5037,
        })

    # The simulator should launch and not crash.
    simulator.launch()

    simulator._emulator_stub.sendTouch = mock.MagicMock(return_value=None)

    simulator.send_touch([(123, 456, True, 0), (135, 246, True, 1)])
    simulator.send_touch([(1, 2, True, 0), (3, 4, True, 1)])
    simulator.send_touch([(321, 654, False, 0), (531, 642, False, 1)])

    simulator._emulator_stub.sendTouch.assert_has_calls([
        mock.call(
            emulator_controller_pb2.TouchEvent(touches=[{
                'x': 123,
                'y': 456,
                'pressure': 1
            }, {
                'x': 135,
                'y': 246,
                'pressure': 1,
                'identifier': 1
            }])),
        mock.call(
            emulator_controller_pb2.TouchEvent(touches=[{
                'x': 1,
                'y': 2,
                'pressure': 1
            }, {
                'x': 3,
                'y': 4,
                'pressure': 1,
                'identifier': 1
            }])),
        mock.call(
            emulator_controller_pb2.TouchEvent(touches=[{
                'x': 321,
                'y': 654,
                'pressure': 0
            }, {
                'x': 531,
                'y': 642,
                'pressure': 0,
                'identifier': 1
            }])),
    ])


if __name__ == '__main__':
  absltest.main()
