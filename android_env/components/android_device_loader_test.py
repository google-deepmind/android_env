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

"""Unit tests for android_device_loader."""

import os
import time
from unittest import mock

from absl.testing import absltest
from android_env.components import adb_call_parser
from android_env.components import adb_controller
from android_env.components import android_device
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.components import device_connection
from android_env.components import errors
from android_env.components import setup_step_interpreter
from android_env.components.simulators.emulator import emulator_launcher
from android_env.components.simulators.emulator import tcp_ports


class AndroidDeviceLoaderTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._mock_conn_init = mock.patch.object(
        device_connection, 'DeviceConnection', autospec=True
    ).start()
    self._mock_conn = self._mock_conn_init.return_value

    self._mock_launcher_cls = mock.patch.object(
        emulator_launcher, 'EmulatorLauncher', autospec=True
    ).start()
    self._mock_launcher = self._mock_launcher_cls.return_value

    self._mock_adb_cls = mock.patch.object(
        adb_controller, 'AdbController', autospec=True
    ).start()
    self._mock_adb = self._mock_adb_cls.return_value

    self._mock_device_cls = mock.patch.object(
        android_device, 'AndroidDevice', autospec=True
    ).start()
    self._mock_device = self._mock_device_cls.return_value

    self._mock_pick_ports = mock.patch.object(
        tcp_ports, 'pick_emulator_ports'
    ).start()

  def tearDown(self):
    mock.patch.stopall()
    super().tearDown()

  @mock.patch.object(android_device_loader, '_prep_device', autospec=True)
  def test_load_physical_device_success(self, mock_prep):
    config = config_classes.AndroidDeviceConfig(
        serial='device-1',
        adb_path='~/Android/Sdk/platform-tools/adb',
        auto_setup=False,
    )
    device = android_device_loader.load_android_device(config)

    self.assertEqual(device, self._mock_device)
    self.assertEqual(
        config.adb_path,
        os.path.expanduser('~/Android/Sdk/platform-tools/adb'),
    )
    self._mock_launcher_cls.assert_not_called()
    mock_prep.assert_not_called()

  @mock.patch.object(android_device_loader, '_wait_for_boot', autospec=True)
  @mock.patch.object(android_device_loader, '_prep_device', autospec=True)
  def test_load_emulator_launches_process(self, mock_prep, mock_wait_boot):
    def fake_pick_ports(launcher_config):
      launcher_config.adb_port = 5555

    self._mock_pick_ports.side_effect = fake_pick_ports

    config = config_classes.AndroidDeviceConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            avd_name='test_avd',
            emulator_console_port=5554,
        ),
        adb_controller=config_classes.AdbControllerConfig(device_name=''),
    )
    device = android_device_loader.load_android_device(config)

    self.assertEqual(device, self._mock_device)
    self._mock_pick_ports.assert_called_once_with(config.emulator_launcher)
    self.assertIsNotNone(config.adb_controller)
    self.assertEqual(config.adb_controller.device_name, 'emulator-5554')
    self._mock_adb.init_server.assert_called_once()
    self._mock_launcher_cls.assert_called_once()
    self._mock_launcher.launch_emulator_process.assert_called_once()
    mock_wait_boot.assert_called_once()
    mock_prep.assert_called_once()

    on_error_cbs = self._mock_device_cls.call_args[1]['on_error_callbacks']
    self.assertLen(on_error_cbs, 1)

    with mock.patch('builtins.open', mock.mock_open()):
      on_error_cbs[0](None, None, None)
    self._mock_adb.execute_command.assert_called_with(
        ['logcat', '-d', '-t', '50000']
    )

  @mock.patch.object(android_device_loader, '_wait_for_boot', autospec=True)
  @mock.patch.object(android_device_loader, '_prep_device', autospec=True)
  def test_load_emulator_expands_user_paths_and_propagates_adb_path(
      self, mock_prep, mock_wait_boot
  ):
    del mock_prep, mock_wait_boot
    self._mock_pick_ports.side_effect = lambda cfg: setattr(
        cfg, 'adb_port', 5555
    )
    config = config_classes.AndroidDeviceConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            avd_name='test_avd',
            android_avd_home='~/.android/avd',
            android_sdk_root='~/Android/Sdk',
            emulator_path='~/Android/Sdk/emulator/emulator',
        ),
        adb_path='~/custom/sdk/platform-tools/adb',
    )

    android_device_loader.load_android_device(config)

    self.assertIsNotNone(config.emulator_launcher)
    self.assertIsNotNone(config.adb_controller)
    self.assertEqual(
        config.emulator_launcher.android_avd_home,
        os.path.expanduser('~/.android/avd'),
    )
    self.assertEqual(
        config.emulator_launcher.android_sdk_root,
        os.path.expanduser('~/Android/Sdk'),
    )
    self.assertEqual(
        config.emulator_launcher.emulator_path,
        os.path.expanduser('~/Android/Sdk/emulator/emulator'),
    )
    expected_adb = os.path.expanduser('~/custom/sdk/platform-tools/adb')
    self.assertEqual(config.adb_controller.adb_path, expected_adb)
    self.assertEqual(config.adb_path, expected_adb)

  @mock.patch.object(android_device_loader, '_wait_for_boot', autospec=True)
  def test_emulator_launch_failure_closes_launcher(self, mock_wait_boot):
    mock_wait_boot.side_effect = RuntimeError('Boot timeout')
    config = config_classes.AndroidDeviceConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            avd_name='test_avd'
        )
    )
    with self.assertRaises(RuntimeError):
      android_device_loader.load_android_device(config)

    self._mock_launcher.close.assert_called_once()

  @mock.patch.object(
      android_device_loader, '_get_prep_steps_path', autospec=True
  )
  @mock.patch.object(
      android_device_loader, '_get_core_apk_from_runfiles', autospec=True
  )
  @mock.patch.object(
      setup_step_interpreter, 'SetupStepInterpreter', autospec=True
  )
  def test_prep_device_configures_steps_and_interprets(
      self, mock_interpreter_cls, mock_get_apk, mock_get_prep_steps_path
  ):
    mock_get_prep_steps_path.return_value = (
        '/path/to/device_prep_steps.textproto'
    )
    mock_get_apk.return_value = '/path/to/server.apk'

    sample_textproto = (
        'setup_steps { adb_request { generic { args: "root" } } }\n'
        'setup_steps { adb_request { generic { args: "shell" } } }\n'
    )

    mock_parser = mock.create_autospec(
        adb_call_parser.AdbCallParser, instance=True
    )
    config = config_classes.AndroidDeviceConfig()
    config.device_connection.websocket_port = 12345

    with mock.patch(
        'builtins.open', mock.mock_open(read_data=sample_textproto)
    ):
      android_device_loader._prep_device(config, mock_parser)

    mock_interpreter_cls.assert_called_once_with(mock_parser)
    interpreter_instance = mock_interpreter_cls.return_value
    interpreter_instance.interpret.assert_called_once()

    steps = interpreter_instance.interpret.call_args[0][0]
    root_step = [
        s
        for s in steps
        if s.adb_request.HasField('generic')
        and s.adb_request.generic.args
        and s.adb_request.generic.args[0] == 'root'
    ]
    self.assertLen(root_step, 1)

    install_step = [s for s in steps if s.adb_request.HasField('install_apk')][
        0
    ]
    self.assertEqual(
        install_step.adb_request.install_apk.filesystem.path,
        '/path/to/server.apk',
    )
    forward_step = [
        s
        for s in steps
        if s.adb_request.HasField('generic')
        and s.adb_request.generic.args
        and s.adb_request.generic.args[0] == 'forward'
    ][0]
    self.assertIn('tcp:12345', forward_step.adb_request.generic.args)

  def test_connect_to_device_retries_and_starts_service(self):
    self._mock_conn_init.side_effect = [
        RuntimeError('Connection refused'),
        self._mock_conn,
    ]
    config = config_classes.AndroidDeviceConfig(
        auto_setup=True,
    )
    conn = android_device_loader._connect_to_device(config, self._mock_adb)
    self.assertEqual(conn, self._mock_conn)
    self.assertEqual(self._mock_conn_init.call_count, 2)
    self._mock_adb.execute_command.assert_called_once_with([
        'shell',
        'am',
        'start',
        '-n',
        'com.google.androidenv.core/.MainActivity',
        '--es',
        'COMMAND',
        'START_SERVER',
    ])

  def test_connect_to_device_fails_after_max_retries(self):
    self._mock_conn_init.side_effect = RuntimeError('Connection failed')
    config = config_classes.AndroidDeviceConfig(auto_setup=False)
    with self.assertRaisesRegex(RuntimeError, 'Connection failed'):
      android_device_loader._connect_to_device(
          config, self._mock_adb, max_retries=2
      )
    self.assertEqual(self._mock_conn_init.call_count, 2)

  def test_wait_for_boot_success(self):
    self._mock_adb.execute_command.return_value = b'1\n'
    android_device_loader._wait_for_boot(self._mock_adb, timeout_sec=5.0)
    self._mock_adb.execute_command.assert_called_with(
        ['shell', 'getprop', 'sys.boot_completed']
    )

  def test_wait_for_boot_handles_adb_error_then_succeeds(self):
    self._mock_adb.execute_command.side_effect = [
        errors.AdbControllerError('Boot check failed'),
        b'1\n',
    ]
    android_device_loader._wait_for_boot(self._mock_adb, timeout_sec=5.0)
    self.assertEqual(self._mock_adb.execute_command.call_count, 2)

  def test_wait_for_boot_succeeds_just_before_deadline(self):
    self._mock_adb.execute_command.side_effect = [b'0\n', b'1\n']
    with mock.patch.object(time, 'time', side_effect=[100.0, 100.0, 104.5]):
      android_device_loader._wait_for_boot(self._mock_adb, timeout_sec=5.0)
    self.assertEqual(self._mock_adb.execute_command.call_count, 2)

  def test_wait_for_boot_timeout(self):
    self._mock_adb.execute_command.side_effect = [b'0\n', b'1\n']
    with mock.patch.object(time, 'time', side_effect=[100.0, 100.0, 105.5]):
      with self.assertRaisesRegex(
          RuntimeError, 'Timed out waiting for emulator boot'
      ):
        android_device_loader._wait_for_boot(self._mock_adb, timeout_sec=5.0)

  @mock.patch.object(
      android_device_loader, '_get_prep_steps_path', autospec=True
  )
  @mock.patch.object(
      android_device_loader, '_get_core_apk_from_runfiles', autospec=True
  )
  @mock.patch.object(
      setup_step_interpreter, 'SetupStepInterpreter', autospec=True
  )
  def test_prep_device_without_apk(
      self, mock_interpreter_cls, mock_get_apk, mock_get_prep_steps_path
  ):
    mock_get_prep_steps_path.return_value = (
        '/path/to/device_prep_steps.textproto'
    )
    mock_get_apk.return_value = ''

    sample_textproto = (
        'setup_steps { adb_request { generic { args: "root" } } }\n'
    )
    mock_parser = mock.create_autospec(
        adb_call_parser.AdbCallParser, instance=True
    )
    config = config_classes.AndroidDeviceConfig()

    with mock.patch(
        'builtins.open', mock.mock_open(read_data=sample_textproto)
    ):
      android_device_loader._prep_device(config, mock_parser)

    interpreter_instance = mock_interpreter_cls.return_value
    steps = interpreter_instance.interpret.call_args[0][0]
    install_steps = [s for s in steps if s.adb_request.HasField('install_apk')]
    self.assertEmpty(install_steps)

  def test_get_prep_steps_path_exists(self):
    self.assertTrue(
        os.path.exists(android_device_loader._get_prep_steps_path())
    )

  def test_dump_logcat_cb_handles_adb_error(self):
    self._mock_adb.execute_command.side_effect = errors.AdbControllerError(
        'Logcat failed'
    )
    config = config_classes.AndroidDeviceConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            avd_name='test_avd',
            emulator_console_port=5554,
        ),
        adb_controller=config_classes.AdbControllerConfig(device_name=''),
    )
    with mock.patch.object(android_device_loader, '_wait_for_boot'):
      with mock.patch.object(android_device_loader, '_prep_device'):
        android_device_loader.load_android_device(config)

    on_error_cbs = self._mock_device_cls.call_args[1]['on_error_callbacks']
    self.assertLen(on_error_cbs, 1)
    on_error_cbs[0](None, None, None)

  def test_load_android_device_error_runs_on_close_callbacks(self):
    self._mock_conn_init.side_effect = errors.AdbControllerError('Conn failed')
    config = config_classes.AndroidDeviceConfig(
        emulator_launcher=config_classes.EmulatorLauncherConfig(
            avd_name='test_avd',
            emulator_console_port=5554,
        ),
        adb_controller=config_classes.AdbControllerConfig(device_name=''),
    )
    with mock.patch.object(android_device_loader, '_wait_for_boot'):
      with mock.patch.object(android_device_loader, '_prep_device'):
        with self.assertRaises(errors.AdbControllerError):
          android_device_loader.load_android_device(config)

    self._mock_launcher.close.assert_called_once()

  def test_connect_to_device_handles_adb_start_service_error(self):
    self._mock_conn_init.side_effect = [
        RuntimeError('Connection refused'),
        self._mock_conn,
    ]
    self._mock_adb.execute_command.side_effect = errors.AdbControllerError(
        'Start service error'
    )
    config = config_classes.AndroidDeviceConfig(auto_setup=True)
    conn = android_device_loader._connect_to_device(config, self._mock_adb)
    self.assertEqual(conn, self._mock_conn)

  def test_connect_to_device_raises_runtime_error_if_max_retries_zero(self):
    config = config_classes.AndroidDeviceConfig(auto_setup=False)
    with self.assertRaisesRegex(
        RuntimeError, 'Failed to connect to on-device server'
    ):
      android_device_loader._connect_to_device(
          config, self._mock_adb, max_retries=0
      )


if __name__ == '__main__':
  absltest.main()
