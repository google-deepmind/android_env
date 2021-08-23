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

"""Tests for android_env.components.emulator_launcher."""

import builtins
import os
from absl.testing import absltest
from android_env.components.simulators.emulator import emulator_launcher
import grpc
import mock
from pexpect import popen_spawn


class EmulatorLauncherTest(absltest.TestCase):

  def setUp(self):
    super().setUp()

    self._emulator_path = 'fake/path/emulator'
    self._adb_port = 5554
    self._adb_server_port = 1234
    self._emulator_console_port = 5555
    self._avd_name = 'my_avd_name'

    self._emulator = mock.create_autospec(popen_spawn.PopenSpawn)
    self._emulator.after = 'after'
    self._emulator_output = mock.create_autospec(open)
    self._emulator_output.close = lambda: None

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

    self._expected_command = [
        self._emulator_path,
        '-no-snapshot',
        '-gpu', 'swiftshader_indirect',
        '-no-audio',
        '-verbose',
        '-avd', self._avd_name,
    ]
    self._ports = ['-ports', f'{self._emulator_console_port},{self._adb_port}']

    base_lib_dir = self._emulator_path[:-8] + 'lib64/'
    ld_library_path = ':'.join([
        base_lib_dir + 'x11/',
        base_lib_dir + 'qt/lib/',
        base_lib_dir + 'gles_swiftshader/',
        base_lib_dir
    ])

    self._expected_env_vars = {
        'ANDROID_HOME': '',
        'ANDROID_SDK_ROOT': '',
        'ANDROID_AVD_HOME': '',
        'ANDROID_EMULATOR_KVM_DEVICE': '/dev/kvm',
        'ANDROID_ADB_SERVER_PORT': '1234',
        'LD_LIBRARY_PATH': ld_library_path,
        'QT_DEBUG_PLUGINS': '1',
        'QT_XKB_CONFIG_ROOT': str(self._emulator_path[:-8] + 'qt_config/'),
    }

  @mock.patch.object(os, 'environ', autospec=True, return_value=dict())
  def test_launch(self, os_environ):
    del os_environ

    launcher = emulator_launcher.EmulatorLauncher(
        adb_port=self._adb_port,
        adb_server_port=self._adb_server_port,
        emulator_console_port=self._emulator_console_port,
        emulator_path=self._emulator_path,
        avd_name=self._avd_name,
        grpc_port=-1)

    with mock.patch.object(
        popen_spawn, 'PopenSpawn', autospec=True,
        return_value=self._emulator) as emulator_init, \
        mock.patch.object(
            builtins, 'open', autospec=True,
            return_value=self._emulator_output):

      launcher.launch()
      emulator_init.assert_called_once_with(
          cmd=self._expected_command + self._ports,
          logfile=self._emulator_output,
          env=self._expected_env_vars)

  @mock.patch.object(os, 'environ', autospec=True, return_value=dict())
  def test_grpc_port(self, os_environ):
    del os_environ

    launcher = emulator_launcher.EmulatorLauncher(
        adb_port=self._adb_port,
        adb_server_port=self._adb_server_port,
        emulator_console_port=self._emulator_console_port,
        emulator_path=self._emulator_path,
        avd_name=self._avd_name,
        grpc_port=8554)

    with mock.patch.object(
        popen_spawn, 'PopenSpawn', autospec=True,
        return_value=self._emulator) as emulator_init, \
        mock.patch.object(
            builtins, 'open', autospec=True,
            return_value=self._emulator_output):
      launcher.launch()
      emulator_init.assert_called_once_with(
          cmd=self._expected_command + ['-grpc', '8554'] + self._ports,
          logfile=self._emulator_output,
          env=self._expected_env_vars)

  @mock.patch.object(os, 'environ', autospec=True, return_value=dict())
  def test_restart(self, os_environ):
    del os_environ

    launcher = emulator_launcher.EmulatorLauncher(
        adb_port=self._adb_port,
        adb_server_port=self._adb_server_port,
        emulator_console_port=self._emulator_console_port,
        emulator_path=self._emulator_path,
        avd_name=self._avd_name,
        grpc_port=-1)

    with mock.patch.object(
        popen_spawn, 'PopenSpawn', autospec=True,
        return_value=self._emulator) as emulator_init, \
        mock.patch.object(
            builtins, 'open', autospec=True,
            return_value=self._emulator_output):
      launcher.launch()
      launcher.restart()
      launcher._emulator_stub.setVmState.assert_called_once()
      emulator_init.assert_has_calls([mock.call(
          cmd=self._expected_command + self._ports,
          logfile=self._emulator_output,
          env=self._expected_env_vars)]*2)


if __name__ == '__main__':
  absltest.main()
