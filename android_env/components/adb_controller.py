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

"""A class to manage and control an external ADB process."""

import os
import subprocess
import time

from absl import logging
from android_env.components import config_classes
from android_env.components import errors


class AdbController:
  """Manages communication with adb."""

  def __init__(self, config: config_classes.AdbControllerConfig):
    """Instantiates an AdbController object."""

    self._config = config
    logging.info('config: %r', self._config)

    # Unset problematic environment variables. ADB commands will fail if these
    # are set. They are normally exported by AndroidStudio.
    if 'ANDROID_HOME' in os.environ:
      del os.environ['ANDROID_HOME']
    if 'ANDROID_ADB_SERVER_PORT' in os.environ:
      del os.environ['ANDROID_ADB_SERVER_PORT']

    # Explicitly expand the $HOME environment variable.
    self._os_env_vars = dict(os.environ).copy()
    self._os_env_vars.update(
        {'HOME': os.path.expandvars(self._os_env_vars.get('HOME', ''))}
    )
    logging.info('self._os_env_vars: %r', self._os_env_vars)

  def command_prefix(self, include_device_name: bool = True) -> list[str]:
    """The command for instantiating an adb client to this server."""
    command_prefix = [
        self._config.adb_path,
        '-P',
        str(self._config.adb_server_port),
    ]
    if include_device_name and self._config.device_name:
      command_prefix.extend(['-s', self._config.device_name])
    return command_prefix

  def init_server(self, timeout: float | None = None):
    """Initialize the ADB server deamon on the given port.

    This function should be called immediately after initializing the first
    adb_controller, and before launching the simulator.

    Args:
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.
    """
    # Make an initial device-independent call to ADB to start the deamon.
    self.execute_command(['devices'], timeout, device_specific=False)
    time.sleep(0.2)

  def _restart_server(self, timeout: float | None = None):
    """Kills and restarts the adb server.

    Args:
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.
    """
    logging.info('Restarting adb server.')
    self.execute_command(
        ['kill-server'], timeout=timeout, device_specific=False)
    time.sleep(0.2)
    cmd_output = self.execute_command(
        ['start-server'], timeout=timeout, device_specific=False)
    logging.info('start-server output: %r', cmd_output.decode('utf-8'))
    time.sleep(2.0)
    self.execute_command(
        ['devices'], timeout=timeout, device_specific=False)
    time.sleep(0.2)

  def execute_command(
      self,
      args: list[str],
      timeout: float | None = None,
      device_specific: bool = True,
  ) -> bytes:
    """Executes an adb command.

    Args:
      args: A list of strings representing each adb argument.
          For example: ['install', '/my/app.apk']
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.
      device_specific: Whether the call is device-specific or independent.

    Returns:
      The output of running such command as a binary string.
    """
    timeout = self._config.default_timeout if timeout is None else timeout
    command = self.command_prefix(include_device_name=device_specific) + args
    command_str = 'adb ' + ' '.join(command[1:])

    n_retries = 2
    n_tries = 1
    latest_error = None
    while n_tries <= n_retries:
      try:
        logging.info('Executing ADB command: [%s]', command_str)
        cmd_output = subprocess.check_output(
            command,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            env=self._os_env_vars,
        )
        logging.debug('ADB command output: %s', cmd_output)
        return cmd_output
      except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as e:
        logging.exception(
            'Failed to execute ADB command (try %r of 3): [%s]',
            n_tries, command_str)
        if e.stdout is not None:
          logging.error('**stdout**:')
          for line in e.stdout.splitlines():
            logging.error('    %s', line)
        if e.stderr is not None:
          logging.error('**stderr**:')
          for line in e.stderr.splitlines():
            logging.error('    %s', line)
        n_tries += 1
        latest_error = e
        if device_specific and n_tries <= n_retries:
          self._restart_server(timeout=timeout)

    raise errors.AdbControllerError(
        f'Error executing adb command: [{command_str}]\n'
        f'Caused by: {latest_error}\n'
        f'adb stdout: [{latest_error.stdout}]\n'
        f'adb stderr: [{latest_error.stderr}]') from latest_error
