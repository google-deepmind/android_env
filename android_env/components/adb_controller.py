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

"""A class to manage and control an external ADB process."""

import os
import subprocess
import time
from typing import List, Optional

from absl import logging
from android_env.components import errors


class AdbController():
  """Manages communication with adb."""

  def __init__(self,
               device_name: str = '',
               adb_path: str = 'adb',
               adb_server_port: int = 5037,
               default_timeout: float = 120.0):
    """Instantiates an AdbController object.

    Args:
      device_name: Name of the device to communicate with.
      adb_path: Path to the adb binary.
      adb_server_port: Port for adb server.
      default_timeout: Default timeout in seconds.
    """

    self._device_name = device_name
    self._adb_path = adb_path
    self._adb_server_port = str(adb_server_port)
    self._default_timeout = default_timeout

    # Unset problematic environment variables. ADB commands will fail if these
    # are set. They are normally exported by AndroidStudio.
    if 'ANDROID_HOME' in os.environ:
      del os.environ['ANDROID_HOME']
    if 'ANDROID_ADB_SERVER_PORT' in os.environ:
      del os.environ['ANDROID_ADB_SERVER_PORT']

  def command_prefix(self) -> List[str]:
    """The command for instantiating an adb client to this server."""
    command_prefix = [self._adb_path, '-P', self._adb_server_port]
    if self._device_name:
      command_prefix.extend(['-s', self._device_name])
    return command_prefix

  def init_server(self, timeout: Optional[float] = None):
    """Initialize the ADB server deamon on the given port.

    This function should be called immediately after initializing the first
    adb_controller, and before launching the simulator.

    Args:
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.
    """
    # Make an initial device-independent call to ADB to start the deamon.
    device_name_tmp = self._device_name
    self._device_name = ''
    self.execute_command(['devices'], timeout=timeout)
    time.sleep(0.2)
    # Subsequent calls will use the device name.
    self._device_name = device_name_tmp

  def execute_command(self,
                      args: List[str],
                      timeout: Optional[float] = None) -> bytes:
    """Executes an adb command.

    Args:
      args: A list of strings representing each adb argument.
          For example: ['install', '/my/app.apk']
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.

    Returns:
      The output of running such command as a binary string.
    """
    timeout = self._default_timeout if timeout is None else timeout
    command = self.command_prefix() + args
    command_str = ' '.join(command)
    logging.info('Executing ADB command: [%s]', command_str)

    try:
      cmd_output = subprocess.check_output(
          command, stderr=subprocess.STDOUT, timeout=timeout)
      logging.info('Done executing ADB command: [%s]', command_str)
      return cmd_output
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
      if error.stdout is not None:
        logging.error('**stdout**:')
        for line in error.stdout.splitlines():
          logging.error(line)
      raise errors.AdbControllerError(
          f'Error executing adb command: [{command_str}]\n'
          f'Caused by {error}\n'
          f'adb output: [{error.stdout}]') from error
