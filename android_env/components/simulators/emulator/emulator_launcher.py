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

"""Prepares and launches an emulator process."""

import glob
import os
import subprocess
import tempfile

from absl import logging
from android_env.components import config_classes


class EmulatorLauncher:
  """Handles launching an emulator."""

  def __init__(
      self,
      config: config_classes.EmulatorLauncherConfig,
      adb_controller_config: config_classes.AdbControllerConfig,
  ):
    """Launches an emulator."""

    self._config = config
    self._adb_controller_config = adb_controller_config

    self._emulator = None
    self._emulator_output = None
    self._is_closed = False

    # Create directory for tmp files.
    # Note: this will be deleted once EmulatorLauncher instance is cleaned up.
    os.makedirs(config.tmp_dir, exist_ok=True)
    self._local_tmp_dir_handle = tempfile.TemporaryDirectory(
        dir=config.tmp_dir, prefix='simulator_instance_'
    )
    self._local_tmp_dir = self._local_tmp_dir_handle.name
    self._logfile_path = os.path.join(self._local_tmp_dir, 'emulator_output')
    logging.info('Simulator local_tmp_dir: %s', self._local_tmp_dir)

  def logfile_path(self) -> str:
    return self._logfile_path

  def launch_emulator_process(self) -> None:
    """Launches the emulator."""

    logging.info('Booting new emulator: %s', self._config.emulator_path)

    # Set necessary environment variables.
    base_lib_dir = self._config.emulator_path[:-8] + 'lib64/'
    ld_library_path = ':'.join([
        base_lib_dir + 'x11/', base_lib_dir + 'qt/lib/',
        base_lib_dir + 'gles_swiftshader/', base_lib_dir
    ])
    extra_env_vars = {
        'ANDROID_HOME': '',
        'ANDROID_SDK_ROOT': self._config.android_sdk_root,
        'ANDROID_AVD_HOME': self._config.android_avd_home,
        'ANDROID_EMULATOR_KVM_DEVICE': self._config.kvm_device,
        'ANDROID_ADB_SERVER_PORT': str(
            self._adb_controller_config.adb_server_port
        ),
        'LD_LIBRARY_PATH': ld_library_path,
        'QT_XKB_CONFIG_ROOT': str(
            self._config.emulator_path[:-8] + 'qt_config/'
        ),
        'ANDROID_EMU_ENABLE_CRASH_REPORTING': '1',
        'SHOW_PERF_STATS': str(1 if self._config.show_perf_stats else 0),
    }
    logging.info('extra_env_vars: %s',
                 ' '.join(f'{k}={v}' for k, v in extra_env_vars.items()))
    env_vars = dict(os.environ).copy()
    env_vars.update(extra_env_vars)

    # Compile command.
    grpc_port = (
        ['-grpc', str(self._config.grpc_port)]
        if self._config.grpc_port >= 0
        else []
    )
    run_headless = (
        ['-no-skin', '-no-window'] if self._config.run_headless else []
    )
    ports = [
        '-ports',
        '%s,%s' % (self._config.emulator_console_port, self._config.adb_port),
    ]
    snapshot = [
        '-snapshot',
        self._config.snapshot_name,
        '-feature',
        'AllowSnapshotMigration,MigratableSnapshotSave',
    ]
    snapshot = snapshot if self._config.snapshot_name else ['-no-snapshot']
    restrict_network_args = [
        '-network-user-mode-options', 'restrict=y', '-wifi-user-mode-options',
        'restrict=y'
    ]
    network_args = (
        restrict_network_args if self._config.restrict_network else []
    )
    command = (
        [
            self._config.emulator_path,
            '-adb-path',
            self._adb_controller_config.adb_path,
            '-gpu',
            self._config.gpu_mode,
            '-no-audio',
            '-show-kernel',
            '-verbose',
            '-avd',
            self._config.avd_name,
        ]
        + grpc_port
        + run_headless
        + ports
        + snapshot
        + network_args
    )
    logging.info('Emulator launch command: %s', ' '.join(command))
    # Prepare logfile.
    self._emulator_output = open(self._logfile_path, 'wb')

    # Spawn the emulator process.
    self._emulator = subprocess.Popen(
        command,
        env=env_vars,
        stdout=self._emulator_output,
        stderr=self._emulator_output)

  def confirm_shutdown(self) -> None:
    """Shuts down the emulator process."""
    if self._emulator is not None:
      logging.info('Checking if emulator process has finished...')
      try:
        self._emulator.wait(timeout=30.0)
      except subprocess.TimeoutExpired:
        logging.exception(
            'The emulator process did not finish after 30s. '
            'returncode: %s. Will now try to kill() it.',
            self._emulator.returncode)
        self._emulator.kill()
      self._emulator = None
      self._emulator_output.close()
      logging.info('The emulator process has finished.')

  def close(self):
    """Clean up launcher files and processes."""
    if not self._is_closed:
      self._local_tmp_dir_handle.cleanup()
      self.confirm_shutdown()
      self._is_closed = True

  def __del__(self):
    self.close()
