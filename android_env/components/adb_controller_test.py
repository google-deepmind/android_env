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

import os
import subprocess
import time
from unittest import mock

from absl.testing import absltest
from android_env.components import adb_controller as adb_controller_lib
from android_env.components import config_classes
from android_env.components import errors

# Timeout to be used by default in tests below. Set to a small value to avoid
# hanging on a failed test.
_TIMEOUT = 2


class AdbControllerTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    # Set env vars.
    os.environ['MY_ENV_VAR'] = '/some/path/'
    os.environ['HOME'] = '$MY_ENV_VAR'
    self._env_before = os.environ.copy()

  def tearDown(self):
    super().tearDown()
    if 'ANDROID_HOME' in os.environ:
      del os.environ['ANDROID_HOME']
    if 'ANDROID_ADB_SERVER_PORT' in os.environ:
      del os.environ['ANDROID_ADB_SERVER_PORT']

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_init_server(self, mock_sleep, mock_check_output):
    """We expect an `adb devices` call when initializing the server."""

    # Arrange.
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            use_adb_server_port_from_os_env=True,
        )
    )

    # Act.
    adb_controller.init_server(timeout=_TIMEOUT)

    # Assert.
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    mock_check_output.assert_called_once_with(
        ['my_adb', 'devices'],
        stderr=subprocess.STDOUT,
        timeout=_TIMEOUT,
        env=expected_env,
    )
    mock_sleep.assert_called_once()

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_init_server_with_adb_server_port_from_os_env(
      self, mock_sleep, mock_check_output
  ):
    """Us OS env vars if `use_adb_server_port_from_os_env` is True."""

    # Arrange.
    # Set the ADB server port to 1234 in the OS environment.
    os.environ['ANDROID_ADB_SERVER_PORT'] = '1234'
    os.environ['ANDROID_HOME'] = '/some/path/to/android'
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
            use_adb_server_port_from_os_env=True,
        )
    )

    # Act.
    adb_controller.init_server(timeout=_TIMEOUT)

    # Assert.
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    expected_env['ANDROID_HOME'] = '/some/path/to/android'
    expected_env['ANDROID_ADB_SERVER_PORT'] = '1234'

    mock_check_output.assert_called_once_with(
        ['my_adb', 'devices'],
        stderr=subprocess.STDOUT,
        timeout=_TIMEOUT,
        env=expected_env,
    )
    mock_sleep.assert_called_once()

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_restart_server(self, mock_sleep, mock_check_output):
    """When an adb command fails, we expect the server to be restarted."""

    # Arrange.
    mock_check_output.side_effect = [
        subprocess.CalledProcessError(returncode=1, cmd='blah'),
    ] + ['fake_output'.encode('utf-8')] * 4
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            use_adb_server_port_from_os_env=True,
        )
    )

    # Act.
    adb_controller.execute_command(['my_command'], timeout=_TIMEOUT)

    # Assert.
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    mock_check_output.assert_has_calls([
        mock.call(
            ['my_adb', '-s', 'awesome_device', 'my_command'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', 'kill-server'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', 'start-server'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', 'devices'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-s', 'awesome_device', 'my_command'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
    ])
    mock_sleep.assert_has_calls(
        [mock.call(0.2), mock.call(2.0), mock.call(0.2)]
    )

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_invalid_command(self, mock_sleep, mock_check_output):
    """Restart the server when given an invalid command."""

    # Arrange.
    restart_sequence = ['fake_output'.encode('utf-8')] * 3
    mock_check_output.side_effect = (
        [
            subprocess.CalledProcessError(returncode=1, cmd='blah'),
        ]
        + restart_sequence
        + [subprocess.CalledProcessError(returncode=1, cmd='blah')]
        # Don't restart if last call fails.
    )
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            use_adb_server_port_from_os_env=True,
        )
    )

    # Act.
    with self.assertRaises(errors.AdbControllerError):
      adb_controller.execute_command(['my_command'], timeout=_TIMEOUT)

    # Assert.
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    mock_check_output.assert_has_calls(
        [
            mock.call(
                ['my_adb', '-s', 'awesome_device', 'my_command'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', 'kill-server'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', 'start-server'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', 'devices'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', '-s', 'awesome_device', 'my_command'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
        ],
        any_order=False,
    )
    mock_sleep.assert_has_calls(
        [mock.call(0.2), mock.call(2.0), mock.call(0.2)]
    )

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_avoid_infinite_recursion(self, mock_sleep, mock_check_output):
    """Raise an error if the command fails even after restarts."""

    del mock_sleep
    mock_check_output.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd='blah'
    )
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            use_adb_server_port_from_os_env=True,
        )
    )
    self.assertRaises(
        errors.AdbControllerError,
        adb_controller.execute_command,
        ['my_command'],
        timeout=_TIMEOUT,
    )

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(adb_controller_lib.logging, 'error', autospec=True)
  @mock.patch.object(adb_controller_lib.logging, 'exception', autospec=True)
  def test_timeout_binary_logging(
      self,
      mock_logging_exception,
      mock_logging_error,
      mock_sleep,
      mock_check_output,
  ):
    """Verify that binary output from timed out command is truncated in logs."""
    del mock_sleep, mock_logging_exception

    binary_line = b'\x00\x01\x02\x03\x0a'
    huge_binary_output = binary_line * 1000
    mock_check_output.side_effect = subprocess.TimeoutExpired(
        cmd='screencap', timeout=120.0, output=huge_binary_output
    )

    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            use_adb_server_port_from_os_env=True,
        )
    )

    with self.assertRaises(errors.AdbControllerError):
      # Pass device_specific=False to avoid server restarts, but it still tries 2 times.
      adb_controller.execute_command(
          ['version'], timeout=_TIMEOUT, device_specific=False
      )

    error_calls = mock_logging_error.call_args_list
    self.assertLen(error_calls, 6)  # 2 tries * 3 logs per try
    self.assertEqual(error_calls[0], mock.call('**stdout** (truncated):'))
    self.assertEqual(error_calls[1], mock.call('    [binary data, size %d]', 4))
    self.assertEqual(
        error_calls[2], mock.call('    ... and %d more lines', 990)
    )
    self.assertEqual(error_calls[3], mock.call('**stdout** (truncated):'))
    self.assertEqual(error_calls[4], mock.call('    [binary data, size %d]', 4))
    self.assertEqual(
        error_calls[5], mock.call('    ... and %d more lines', 990)
    )

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(adb_controller_lib.logging, 'error', autospec=True)
  @mock.patch.object(adb_controller_lib.logging, 'exception', autospec=True)
  def test_timeout_long_text_logging(
      self,
      mock_logging_exception,
      mock_logging_error,
      mock_sleep,
      mock_check_output,
  ):
    """Verify that long text output from timed out command is truncated in logs."""
    del mock_sleep, mock_logging_exception

    text_output = b'line\n' * 20
    mock_check_output.side_effect = subprocess.TimeoutExpired(
        cmd='blah', timeout=120.0, output=text_output
    )

    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            use_adb_server_port_from_os_env=True,
        )
    )

    with self.assertRaises(errors.AdbControllerError):
      # Pass device_specific=False to avoid server restarts, but it still tries 2 times.
      adb_controller.execute_command(
          ['version'], timeout=_TIMEOUT, device_specific=False
      )

    error_calls = mock_logging_error.call_args_list
    self.assertLen(error_calls, 24)  # 2 tries * 12 logs per try
    for offset in (0, 12):
      self.assertEqual(
          error_calls[offset], mock.call('**stdout** (truncated):')
      )
      for i in range(1, 11):
        self.assertEqual(error_calls[offset + i], mock.call('    %s', 'line'))
      self.assertEqual(
          error_calls[offset + 11], mock.call('    ... and %d more lines', 10)
      )


class AdbControllerInitTest(absltest.TestCase):

  def test_deletes_problem_env_vars(self):
    os.environ['ANDROID_HOME'] = '/usr/local/Android/Sdk'
    os.environ['ANDROID_ADB_SERVER_PORT'] = '1337'
    adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
            default_timeout=_TIMEOUT,
        )
    )
    self.assertNotIn('ANDROID_HOME', os.environ)
    self.assertNotIn('ANDROID_ADB_SERVER_PORT', os.environ)

  def test_use_adb_server_port_from_os_env_retains_os_env_vars(self):
    os.environ['ANDROID_HOME'] = '/usr/local/Android/Sdk'
    os.environ['ANDROID_ADB_SERVER_PORT'] = '1337'
    adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
            default_timeout=_TIMEOUT,
            use_adb_server_port_from_os_env=True,
        )
    )
    self.assertIn('ANDROID_ADB_SERVER_PORT', os.environ)
    self.assertEqual(os.environ['ANDROID_ADB_SERVER_PORT'], '1337')
    self.assertIn('ANDROID_HOME', os.environ)
    self.assertEqual(os.environ['ANDROID_HOME'], '/usr/local/Android/Sdk')


if __name__ == '__main__':
  absltest.main()
