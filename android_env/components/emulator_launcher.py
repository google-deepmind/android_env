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

"""Prepares and launches the emulator."""

import os
import signal
import time
from typing import Optional

from absl import logging
from android_env.components import errors
import pexpect
from pexpect import popen_spawn


class EmulatorLauncher():
  """Handles launching the emulator."""

  def __init__(
      self,
      local_tmp_dir: str = '/tmp',
      adb_port: Optional[int] = None,
      adb_server_port: Optional[int] = None,
      emulator_console_port: Optional[int] = None,
      grpc_port: int = -1,
      emulator_path: str = '',
      android_sdk_root: str = '',
      avd_name: str = '',
      run_headless: bool = False,
      kvm_device: str = '/dev/kvm',
      gpu_mode: str = 'swiftshader_indirect',
      android_avd_home: str = '',
      startup_wait_time_sec: int = 300,
  ):
    """Installs required files locally and launches the emulator.

    Args:
      local_tmp_dir: Local directory for logs and maybe installing the AVD.
      adb_port: ADB port for the Android device.
      adb_server_port: Port of the ADB server deamon.
      emulator_console_port: Port for telnet communication with the emulator.
      grpc_port: Port for gRPC communication with the emulator.
      emulator_path: Path to the emulator binary.
      android_sdk_root: Root directory of the Android SDK.
      avd_name: Name of the AVD.
      run_headless: Whether to run in headless mode.
      kvm_device: Path to the KVM device.
      gpu_mode: GPU mode override. Supported values are listed at:
        https://developer.android.com/studio/run/emulator-acceleration#accel-graphics
      android_avd_home: Local directory for AVDs.
      startup_wait_time_sec: Timeout for booting the emulator.
    """
    self._local_tmp_dir = local_tmp_dir
    self._adb_port = adb_port
    self._adb_server_port = adb_server_port
    self._emulator_console_port = emulator_console_port
    self._emulator_path = emulator_path
    self._android_sdk_root = android_sdk_root
    self._avd_name = avd_name
    self._run_headless = run_headless
    self._kvm_device = kvm_device
    self._gpu_mode = gpu_mode
    self._android_avd_home = android_avd_home
    self._startup_wait_time_sec = startup_wait_time_sec
    self._grpc_port = grpc_port

    self._emulator = None
    self._emulator_output = None
    self._is_closed = False

  def launch(self) -> None:
    """Launches the emulator."""

    logging.info('Booting the emulator [%s]', self._emulator_path)

    # Set necessary environment variables.
    base_lib_dir = self._emulator_path[:-8] + 'lib64/'
    ld_library_path = ':'.join([
        base_lib_dir + 'x11/',
        base_lib_dir + 'qt/lib/',
        base_lib_dir + 'gles_swiftshader/',
        base_lib_dir
    ])
    extra_env_vars = {
        'ANDROID_HOME': '',
        'ANDROID_SDK_ROOT': self._android_sdk_root,
        'ANDROID_AVD_HOME': self._android_avd_home,
        'ANDROID_EMULATOR_KVM_DEVICE': self._kvm_device,
        'ANDROID_ADB_SERVER_PORT': str(self._adb_server_port),
        'LD_LIBRARY_PATH': ld_library_path,
        'QT_DEBUG_PLUGINS': '1',
        'QT_XKB_CONFIG_ROOT': str(self._emulator_path[:-8] + 'qt_config/'),
    }
    logging.info('extra_env_vars: %s', str(extra_env_vars))
    env_vars = dict(os.environ).copy()
    env_vars.update(extra_env_vars)

    # Compile command.
    grpc_port = ['-grpc', str(self._grpc_port)] if self._grpc_port >= 0 else []
    run_headless = ['-no-skin', '-no-window'] if self._run_headless else []
    ports = ['-ports', '%s,%s' % (self._emulator_console_port, self._adb_port)]
    command = [
        self._emulator_path,
        '-no-snapshot',
        '-gpu', self._gpu_mode,
        '-no-audio',
        '-verbose',
        '-avd', self._avd_name,
    ] + grpc_port + run_headless + ports
    logging.info('Emulator launch command: %s', ' '.join(command))

    # Prepare logfile.
    emulator_logfile = os.path.join(self._local_tmp_dir, 'emulator_output')
    self._emulator_output = open(emulator_logfile, 'wb')

    # Boot emulator.
    start_time = time.time()

    try:
      self._emulator = popen_spawn.PopenSpawn(
          cmd=command, logfile=self._emulator_output, env=env_vars)
      wait_time = self._startup_wait_time_sec
      logging.info('Waiting for boot for %0.1f seconds...', wait_time)
      self._emulator.expect('emulator: INFO: boot completed', timeout=wait_time)
      logging.info('Emulator log matched: %s', self._emulator.after)
    except pexpect.ExceptionPexpect as e:
      if self._emulator and self._emulator.before:
        for line in self._emulator.before.decode('utf-8').split('\n'):
          logging.info(line)
      raise errors.SimulatorCrashError('The emulator has crashed: %r' % e)

    elapsed_time = time.time() - start_time
    logging.info('Done booting the emulator (in %f seconds).', elapsed_time)

  def restart(self) -> None:
    logging.info('Restarting the emulator...')
    self._kill_emulator_process()
    self.launch()
    logging.info('Done restarting the emulator.')

  def _kill_emulator_process(self) -> None:
    if self._emulator:
      logging.info('Killing the emulator process...')
      self._emulator.kill(signal.SIGKILL)
      self._emulator.wait()
      self._emulator = None
      self._emulator_output.close()
      logging.info('Done killing the emulator process.')

  def close(self):
    if not self._is_closed:
      self._kill_emulator_process()
      self._is_closed = True

  def __del__(self):
    self.close()
