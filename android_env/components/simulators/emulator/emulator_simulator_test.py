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

"""Tests for android_env.components.emulator_simulator."""

import builtins
import os
import time
from unittest import mock

from absl.testing import absltest
from android_env.components import adb_call_parser
from android_env.components import adb_controller
from android_env.components import config_classes
from android_env.components.simulators.emulator import emulator_launcher
from android_env.components.simulators.emulator import emulator_simulator
from android_env.proto import state_pb2
import grpc
from PIL import Image
import portpicker

from android_env.proto import emulator_controller_pb2
from android_env.proto import emulator_controller_pb2_grpc
from android_env.proto import snapshot_service_pb2


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
        grpc.aio, 'secure_channel', return_value=self._grpc_channel).start()
    mock.patch.object(
        grpc, 'secure_channel', return_value=self._grpc_channel).start()
    mock.patch.object(
        grpc, 'local_channel_credentials',
        return_value=self._grpc_channel).start()
    self._mock_future = mock.create_autospec(grpc.Future)
    mock.patch.object(
        grpc, 'channel_ready_future', return_value=self._mock_future).start()
    mock.patch.object(time, 'time', return_value=12345).start()

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
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)
    self.assertNotEmpty(simulator.adb_device_name())

  @mock.patch.object(os.path, 'exists', autospec=True, return_value=True)
  @mock.patch.object(builtins, 'open', autospec=True)
  def test_logfile_path(self, mock_open, unused_mock_exists):
    config = config_classes.EmulatorConfig(
        logfile_path='fake/logfile/path',
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)
    mock_open.return_value.__enter__.return_value.read.return_value = (
        'fake_logs'.encode('utf-8'))
    logs = simulator.get_logs()
    mock_open.assert_called_once_with('fake/logfile/path', 'rb')
    self.assertEqual(logs, 'fake_logs')

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  def test_grpc_port(self, unused_mock_portpicker):

    launcher_config = config_classes.EmulatorLauncherConfig(
        tmp_dir=self.create_tempdir().full_path
    )
    config = config_classes.EmulatorConfig(
        emulator_launcher=launcher_config,
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)
    self.assertEqual(launcher_config.grpc_port, 8554)

  @mock.patch.object(portpicker, 'is_port_free', return_value=False)
  def test_grpc_port_unavailable(self, unused_mock_portpicker):

    launcher_config = config_classes.EmulatorLauncherConfig(
        tmp_dir=self.create_tempdir().full_path
    )
    config = config_classes.EmulatorConfig(
        emulator_launcher=launcher_config,
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)
    self.assertNotEqual(launcher_config.grpc_port, 8554)

  def test_launch_operation_order(self):
    """Makes sure that adb_controller is started before Emulator is launched."""

    # Arrange.
    call_order = []
    self._adb_controller.init_server.side_effect = lambda: call_order.append(
        'init_server'
    )
    self._launcher.launch_emulator_process.side_effect = (
        lambda: call_order.append('launch_emulator_process')
    )
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # Act.
    simulator.launch()  # The simulator should launch and not crash.

    # Assert.
    # The adb server should be initialized before launching the emulator.
    self.assertEqual(call_order, ['init_server', 'launch_emulator_process'])

  def test_close(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # The simulator should launch and not crash.
    simulator.launch()

    # For whatever reason clients may want to close the EmulatorSimulator.
    # We just want to check that the simulator does not crash and/or leak
    # resources.
    simulator.close()

  def test_value_error_if_launch_attempt_params_incorrect(self):
    self.assertRaises(
        ValueError,
        emulator_simulator.EmulatorSimulator,
        config=config_classes.EmulatorConfig(
            emulator_launcher=config_classes.EmulatorLauncherConfig(
                grpc_port=1234, tmp_dir=self.create_tempdir().full_path
            ),
            adb_controller=config_classes.AdbControllerConfig(
                adb_path='/my/adb',
                adb_server_port=5037,
            ),
            launch_n_times_without_reboot=2,
            launch_n_times_without_reinstall=1,
        ),
    )

  def test_launch_attempt_reboot(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
        launch_n_times_without_reboot=1,
        launch_n_times_without_reinstall=2,
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # The simulator should launch and not crash.
    simulator.launch()

    self._launcher.launch_emulator_process.assert_called_once()
    self._launcher.reset_mock()

    # Launch attempt 2.
    simulator.launch()
    self._launcher.confirm_shutdown.assert_called_once()
    self._launcher.close.assert_not_called()
    self._launcher.launch_emulator_process.assert_called_once()

  def test_launch_attempt_reinstall_after_zero_attempts(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
        launch_n_times_without_reboot=0,
        launch_n_times_without_reinstall=0,
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # The simulator should not reboot or reinstall on its very first launch.
    simulator.launch()
    self._launcher.launch_emulator_process.assert_called_once()
    self._launcher.confirm_shutdown.assert_not_called()
    self._launcher.close.assert_not_called()

    # Every subsequent attempt should reboot and reinstall.
    self._launcher.reset_mock()
    simulator.launch()
    self._launcher.confirm_shutdown.assert_called_once()
    self._launcher.close.assert_called_once()  # Now this should `close()`.
    self._launcher.launch_emulator_process.assert_called_once()

  def test_launch_attempt_reinstall(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
        launch_n_times_without_reboot=1,
        launch_n_times_without_reinstall=2,
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # The simulator should launch and not crash.
    simulator.launch()
    self._launcher.launch_emulator_process.assert_called_once()

    # Launch attempt 2.
    self._launcher.reset_mock()
    simulator.launch()
    self._launcher.confirm_shutdown.assert_called_once()
    self._launcher.close.assert_not_called()  # Reboots don't `close()`.
    self._launcher.launch_emulator_process.assert_called_once()

    # Launch attempt 3.
    self._launcher.reset_mock()
    simulator.launch()
    self._launcher.confirm_shutdown.assert_called_once()
    self._launcher.close.assert_called_once()  # Now this should `close()`.
    self._launcher.launch_emulator_process.assert_called_once()

  def test_get_screenshot(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

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

  def test_load_state(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # The simulator should launch and not crash.
    simulator.launch()

    with mock.patch.object(
        simulator, '_snapshot_stub', create_autospec=True
    ) as mock_snapshot_stub:
      snapshot_list = snapshot_service_pb2.SnapshotList()
      snapshot_list.snapshots.add(snapshot_id='snapshot_name_foo')
      snapshot_list.snapshots.add(snapshot_id='snapshot_name_bar')
      mock_snapshot_stub.ListSnapshots.return_value = snapshot_list
      mock_snapshot_stub.LoadSnapshot.return_value = (
          snapshot_service_pb2.SnapshotPackage(success=True)
      )
      load_response = simulator.load_state(
          request=state_pb2.LoadStateRequest(
              args={'snapshot_name': 'snapshot_name_foo'}
          )
      )
      self.assertEqual(
          load_response.status, state_pb2.LoadStateResponse.Status.OK
      )
      load_response = simulator.load_state(
          request=state_pb2.LoadStateRequest(
              args={'snapshot_name': 'snapshot_name_baz'}
          )
      )
      self.assertEqual(
          load_response.status, state_pb2.LoadStateResponse.Status.NOT_FOUND
      )
      mock_snapshot_stub.LoadSnapshot.return_value = (
          snapshot_service_pb2.SnapshotPackage(success=False, err=b'error')
      )
      load_response = simulator.load_state(
          request=state_pb2.LoadStateRequest(
              args={'snapshot_name': 'snapshot_name_bar'}
          )
      )
      self.assertEqual(
          load_response.status, state_pb2.LoadStateResponse.Status.ERROR
      )
      self.assertEqual(load_response.error_message, 'error')

  def test_save_state(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # The simulator should launch and not crash.
    simulator.launch()

    with mock.patch.object(
        simulator, '_snapshot_stub', create_autospec=True
    ) as mock_snapshot_stub:
      mock_snapshot_stub.SaveSnapshot.return_value = (
          snapshot_service_pb2.SnapshotPackage(success=True)
      )
      save_response = simulator.save_state(
          request=state_pb2.SaveStateRequest(
              args={'snapshot_name': 'snapshot_name_foo'}
          )
      )
      self.assertEqual(
          save_response.status, state_pb2.SaveStateResponse.Status.OK
      )
      mock_snapshot_stub.SaveSnapshot.return_value = (
          snapshot_service_pb2.SnapshotPackage(success=False, err=b'error')
      )
      save_response = simulator.save_state(
          request=state_pb2.SaveStateRequest(
              args={'snapshot_name': 'snapshot_name_bar'}
          )
      )
      self.assertEqual(
          save_response.status, state_pb2.SaveStateResponse.Status.ERROR
      )
      self.assertEqual(save_response.error_message, 'error')

  def test_send_touch(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

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

  def test_send_key(self):
    config = config_classes.EmulatorConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            grpc_port=1234, tmp_dir=self.create_tempdir().full_path
        ),
        adb_controller=config_classes.AdbControllerConfig(
            adb_path='/my/adb',
            adb_server_port=5037,
        ),
    )
    simulator = emulator_simulator.EmulatorSimulator(config)

    # The simulator should launch and not crash.
    simulator.launch()

    simulator._emulator_stub.sendTouch = mock.MagicMock(return_value=None)

    simulator.send_key(123, 'keydown')
    simulator.send_key(321, 'keydown')
    simulator.send_key(321, 'keyup')
    simulator.send_key(123, 'keyup')
    simulator.send_key(321, 'keypress')
    simulator.send_key(123, 'keypress')

    simulator._emulator_stub.sendKey.assert_has_calls([
        mock.call(
            emulator_controller_pb2.KeyboardEvent(
                codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
                eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType
                .keydown,
                keyCode=123,
            )),
        mock.call(
            emulator_controller_pb2.KeyboardEvent(
                codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
                eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType
                .keydown,
                keyCode=321,
            )),
        mock.call(
            emulator_controller_pb2.KeyboardEvent(
                codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
                eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType
                .keyup,
                keyCode=321,
            )),
        mock.call(
            emulator_controller_pb2.KeyboardEvent(
                codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
                eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType
                .keyup,
                keyCode=123,
            )),
        mock.call(
            emulator_controller_pb2.KeyboardEvent(
                codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
                eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType
                .keypress,
                keyCode=321,
            )),
        mock.call(
            emulator_controller_pb2.KeyboardEvent(
                codeType=emulator_controller_pb2.KeyboardEvent.KeyCodeType.XKB,
                eventType=emulator_controller_pb2.KeyboardEvent.KeyEventType
                .keypress,
                keyCode=123,
            ))
    ])


if __name__ == '__main__':
  absltest.main()
