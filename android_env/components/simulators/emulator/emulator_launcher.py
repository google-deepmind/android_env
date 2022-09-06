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

"""Prepares and launches an emulator process."""

import os
import subprocess
import sys
import tempfile
from typing import Optional

from absl import logging


class EmulatorLauncher:
  """Handles launching an emulator."""

  def __init__(
      self,
      adb_port: Optional[int] = None,
      adb_server_port: Optional[int] = None,
      emulator_console_port: Optional[int] = None,
      grpc_port: int = -1,
      emulator_path: str = '',
      android_sdk_root: str = '',
      avd_name: str = '',
      android_avd_home: str = '',
      run_headless: bool = False,
      kvm_device: str = '/dev/kvm',
      gpu_mode: str = 'swiftshader_indirect',
      tmp_dir: str = '',
      snapshot_name: str = '',
      restrict_network: bool = False):
    """Launches an emulator.

    Args:
      adb_port: ADB port for the Android device.
      adb_server_port: Port of the ADB server deamon.
      emulator_console_port: Port for telnet communication with the emulator.
      grpc_port: Port for gRPC communication with the emulator.
      emulator_path: Path to the emulator binary.
      android_sdk_root: Root directory of the Android SDK.
      avd_name: Name of the AVD.
      android_avd_home: Local directory for AVDs.
      run_headless: Whether to run in headless mode.
      kvm_device: Path to the KVM device.
      gpu_mode: GPU mode override. Supported values are listed at:
        https://developer.android.com/studio/run/emulator-acceleration#accel-graphics
      tmp_dir: Path to directory which will hold temporary files.
      snapshot_name: Name of the snapshot to load.
      restrict_network: if True, will disable networking on the device. This
        option is only available for emulator version > 31.3.9 (June 2022).
    """
    self._adb_port = adb_port
    self._adb_server_port = adb_server_port
    self._emulator_console_port = emulator_console_port
    self._grpc_port = grpc_port
    self._emulator_path = emulator_path
    self._android_sdk_root = android_sdk_root
    self._avd_name = avd_name
    self._android_avd_home = android_avd_home
    self._run_headless = run_headless
    self._kvm_device = kvm_device
    self._gpu_mode = gpu_mode
    self._snapshot_name = snapshot_name
    self._restrict_network = restrict_network

    self._emulator = None
    self._emulator_output = None
    self._is_closed = False

    # Create directory for tmp files.
    # Note: this will be deleted once EmulatorLauncher instance is cleaned up.
    os.makedirs(tmp_dir, exist_ok=True)
    self._local_tmp_dir_handle = tempfile.TemporaryDirectory(
        dir=tmp_dir, prefix='simulator_instance_')
    self._local_tmp_dir = self._local_tmp_dir_handle.name
    self._logfile_path = os.path.join(self._local_tmp_dir, 'emulator_output')
    logging.info('Simulator local_tmp_dir: %s', self._local_tmp_dir)

  def logfile_path(self) -> str:
    return self._logfile_path

      self._is_closed = True

  def __del__(self):
    self.close()
