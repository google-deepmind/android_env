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

"""Tests for android_env.components.emulator_launcher."""

import builtins
import os
import subprocess
import tempfile
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import config_classes
from android_env.components.simulators.emulator import emulator_launcher


class EmulatorLauncherTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()

    self._emulator_path = 'fake/path/emulator'
    self._adb_path = 'fake/path/adb'
    self._adb_port = 5554
    self._adb_server_port = 1234
    self._emulator_console_port = 5555
    self._avd_name = 'my_avd_name'

    self._expected_command = [
        self._emulator_path,
        '-adb-path',
        'fake/path/adb',
        '-gpu',
        'swangle_indirect',
        '-no-audio',
        '-show-kernel',
        '-verbose',
        '-avd',
        self._avd_name,
    ]
    self._headless = ['-no-skin', '-no-window']
    self._ports = ['-ports', f'{self._emulator_console_port},{self._adb_port}']
    self._snapshot = ['-no-snapshot']

    base_lib_dir = self._emulator_path[:-8] + 'lib64/'
    ld_library_path = ':'.join([
        base_lib_dir + 'x11/', base_lib_dir + 'qt/lib/',
        base_lib_dir + 'gles_swiftshader/', base_lib_dir
    ])

    # Instantiate the config to extract default values.
    config = config_classes.EmulatorLauncherConfig()
    self._expected_env_vars = {
        'ANDROID_HOME': '',
        'ANDROID_SDK_ROOT': config.android_sdk_root,
        'ANDROID_AVD_HOME': config.android_avd_home,
        'ANDROID_EMULATOR_KVM_DEVICE': '/dev/kvm',
        'ANDROID_ADB_SERVER_PORT': '1234',
        'LD_LIBRARY_PATH': ld_library_path,
        'QT_XKB_CONFIG_ROOT': str(self._emulator_path[:-8] + 'qt_config/'),
        'ANDROID_EMU_ENABLE_CRASH_REPORTING': '1',
    }

  @parameterized.named_parameters([
      ('hide_perf_stats', False),
      ('show_perf_stats', True),
  ])
  @mock.patch.object(os, 'makedirs')
  @mock.patch.object(os, 'environ', autospec=True, return_value=dict())
  @mock.patch.object(tempfile, 'TemporaryDirectory', instance=True)
  def test_launch(
      self,
      show_perf_stats: bool,
      mock_tmp_dir,
      unused_os_environ,
      unused_os_makedirs,
  ):
    mock_tmp_dir.return_value.name.return_value = 'local_tmp_dir'

    config = config_classes.EmulatorLauncherConfig(
        adb_port=self._adb_port,
        emulator_console_port=self._emulator_console_port,
        emulator_path=self._emulator_path,
        avd_name=self._avd_name,
        grpc_port=-1,
        show_perf_stats=show_perf_stats,
    )
    adb_controller_config = config_classes.AdbControllerConfig(
        adb_path=self._adb_path,
        adb_server_port=self._adb_server_port,
    )
    launcher = emulator_launcher.EmulatorLauncher(
        config=config, adb_controller_config=adb_controller_config
    )

    expected_env_vars = self._expected_env_vars
    expected_env_vars['SHOW_PERF_STATS'] = '1' if show_perf_stats else '0'

    with mock.patch.object(
        subprocess, 'Popen', autospec=True
    ) as emulator_init, mock.patch.object(builtins, 'open', autospec=True) as f:
      f.return_value.__enter__ = f()
      launcher.launch_emulator_process()
      emulator_init.assert_called_once_with(
          args=self._expected_command
          + self._headless
          + self._ports
          + self._snapshot,
          env=expected_env_vars,
          stdout=f(),
          stderr=f(),
      )

  @parameterized.named_parameters([
      ('hide_perf_stats', False),
      ('show_perf_stats', True),
  ])
  @mock.patch.object(os, 'makedirs')
  @mock.patch.object(os, 'environ', autospec=True, return_value=dict())
  @mock.patch.object(tempfile, 'TemporaryDirectory', instance=True)
  def test_grpc_port(
      self,
      show_perf_stats: bool,
      mock_tmp_dir,
      unused_os_environ,
      unused_os_makedirs,
  ):
    mock_tmp_dir.return_value.name.return_value = 'local_tmp_dir'

    config = config_classes.EmulatorLauncherConfig(
        adb_port=self._adb_port,
        emulator_console_port=self._emulator_console_port,
        emulator_path=self._emulator_path,
        avd_name=self._avd_name,
        grpc_port=8554,
        show_perf_stats=show_perf_stats,
    )
    adb_controller_config = config_classes.AdbControllerConfig(
        adb_path=self._adb_path,
        adb_server_port=self._adb_server_port,
    )
    launcher = emulator_launcher.EmulatorLauncher(
        config=config, adb_controller_config=adb_controller_config
    )

    expected_env_vars = self._expected_env_vars
    expected_env_vars['SHOW_PERF_STATS'] = '1' if show_perf_stats else '0'

    with mock.patch.object(
        subprocess, 'Popen', autospec=True
    ) as emulator_init, mock.patch.object(builtins, 'open', autospec=True) as f:
      f.return_value.__enter__ = f()
      launcher.launch_emulator_process()
      emulator_init.assert_called_once_with(
          args=self._expected_command
          + ['-grpc', '8554']
          + self._headless
          + self._ports
          + self._snapshot,
          env=expected_env_vars,
          stdout=f(),
          stderr=f(),
      )

  @parameterized.named_parameters([
      ('hide_perf_stats', False),
      ('show_perf_stats', True),
  ])
  @mock.patch.object(os, 'makedirs')
  @mock.patch.object(os, 'environ', autospec=True, return_value=dict())
  @mock.patch.object(tempfile, 'TemporaryDirectory', instance=True)
  def test_snapshot(
      self,
      show_perf_stats: bool,
      mock_tmp_dir,
      unused_os_environ,
      unused_os_makedirs,
  ):
    mock_tmp_dir.return_value.name.return_value = 'local_tmp_dir'

    config = config_classes.EmulatorLauncherConfig(
        adb_port=self._adb_port,
        emulator_console_port=self._emulator_console_port,
        emulator_path=self._emulator_path,
        avd_name=self._avd_name,
        grpc_port=-1,
        snapshot_name='my_snapshot',
        show_perf_stats=show_perf_stats,
    )
    adb_controller_config = config_classes.AdbControllerConfig(
        adb_path=self._adb_path,
        adb_server_port=self._adb_server_port,
    )
    launcher = emulator_launcher.EmulatorLauncher(
        config=config, adb_controller_config=adb_controller_config
    )

    expected_snapshot = [
        '-snapshot', 'my_snapshot', '-feature',
        'AllowSnapshotMigration,MigratableSnapshotSave'
    ]

    expected_env_vars = self._expected_env_vars
    expected_env_vars['SHOW_PERF_STATS'] = '1' if show_perf_stats else '0'

    with mock.patch.object(
        subprocess, 'Popen', autospec=True) as emulator_init, \
        mock.patch.object(builtins, 'open', autospec=True) as f:
      f.return_value.__enter__ = f()
      launcher.launch_emulator_process()
      emulator_init.assert_called_once_with(
          args=self._expected_command
          + self._headless
          + self._ports
          + expected_snapshot,
          env=expected_env_vars,
          stdout=f(),
          stderr=f(),
      )

  @parameterized.named_parameters([
      ('hide_perf_stats', False),
      ('show_perf_stats', True),
  ])
  @mock.patch.object(os, 'makedirs')
  @mock.patch.object(os, 'environ', autospec=True, return_value=dict())
  @mock.patch.object(tempfile, 'TemporaryDirectory', instance=True)
  def test_network_restrict(
      self,
      show_perf_stats: bool,
      mock_tmp_dir,
      unused_os_environ,
      unused_os_makedirs,
  ):
    mock_tmp_dir.return_value.name.return_value = 'local_tmp_dir'

    config = config_classes.EmulatorLauncherConfig(
        adb_port=self._adb_port,
        emulator_console_port=self._emulator_console_port,
        emulator_path=self._emulator_path,
        avd_name=self._avd_name,
        grpc_port=-1,
        restrict_network=True,
        show_perf_stats=show_perf_stats,
    )
    adb_controller_config = config_classes.AdbControllerConfig(
        adb_path=self._adb_path,
        adb_server_port=self._adb_server_port,
    )
    launcher = emulator_launcher.EmulatorLauncher(
        config=config, adb_controller_config=adb_controller_config
    )

    expected_snapshot = ['-no-snapshot']
    expected_network_restrict = [
        '-network-user-mode-options', 'restrict=y', '-wifi-user-mode-options',
        'restrict=y'
    ]

    expected_env_vars = self._expected_env_vars
    expected_env_vars['SHOW_PERF_STATS'] = '1' if show_perf_stats else '0'

    with mock.patch.object(
        subprocess, 'Popen', autospec=True) as emulator_init, \
        mock.patch.object(builtins, 'open', autospec=True) as f:
      f.return_value.__enter__ = f()
      launcher.launch_emulator_process()
      emulator_init.assert_called_once_with(
          self._expected_command
          + self._headless
          + self._ports
          + expected_snapshot
          + expected_network_restrict,
          env=expected_env_vars,
          stdout=f(),
          stderr=f(),
      )


if __name__ == '__main__':
  absltest.main()
