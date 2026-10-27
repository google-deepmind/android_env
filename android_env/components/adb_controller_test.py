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
    if 'ADB_SERVER_SOCKET' in os.environ:
      del os.environ['ADB_SERVER_SOCKET']
    if 'DISABLE_ADB_KILL_SERVER' in os.environ:
      del os.environ['DISABLE_ADB_KILL_SERVER']

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
        stdin=subprocess.DEVNULL,
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
        stdin=subprocess.DEVNULL,
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
        subprocess.CalledProcessError(
            returncode=1, cmd='blah', output=b'some error output'
        ),
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
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', 'kill-server'],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', 'start-server'],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', 'devices'],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-s', 'awesome_device', 'my_command'],
            stdin=subprocess.DEVNULL,
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
            subprocess.CalledProcessError(
                returncode=1, cmd='blah', output=b'some error output'
            ),
        ]
        + restart_sequence
        + [
            subprocess.CalledProcessError(
                returncode=1, cmd='blah', output=b'some final error output'
            )
        ]
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
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', 'kill-server'],
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', 'start-server'],
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', 'devices'],
                stdin=subprocess.DEVNULL,
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', '-s', 'awesome_device', 'my_command'],
                stdin=subprocess.DEVNULL,
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
        returncode=1, cmd='blah', output=b'always failing'
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

  def test_command_prefix_uses_config_port_by_default(self):
    """Pass `-P <port>` when neither OS env port nor socket is configured."""

    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
            use_adb_server_port_from_os_env=False,
        )
    )

    self.assertEqual(
        adb_controller.command_prefix(),
        ['my_adb', '-P', '9999', '-s', 'awesome_device'],
    )
    self.assertEqual(
        adb_controller.command_prefix(include_device_name=False),
        ['my_adb', '-P', '9999'],
    )

  def test_command_prefix_omits_port_when_adb_server_socket_set(self):
    """Do not pass `-P <port>` when `ADB_SERVER_SOCKET` is set in os.environ."""

    os.environ['ADB_SERVER_SOCKET'] = 'tcp:localhost:5037'
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
            use_adb_server_port_from_os_env=False,
        )
    )

    self.assertEqual(
        adb_controller.command_prefix(),
        ['my_adb', '-s', 'awesome_device'],
    )
    self.assertEqual(
        adb_controller.command_prefix(include_device_name=False),
        ['my_adb'],
    )

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_restart_server_skipped_when_adb_server_socket_set(
      self, mock_sleep, mock_check_output
  ):
    """Do not restart server if ADB_SERVER_SOCKET is set."""

    os.environ['ADB_SERVER_SOCKET'] = 'tcp:localhost:5037'
    mock_check_output.side_effect = [
        subprocess.CalledProcessError(
            returncode=1, cmd='blah', output=b'some error output'
        ),
        'fake_output'.encode('utf-8'),
    ]
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
            use_adb_server_port_from_os_env=False,
        )
    )

    output = adb_controller.execute_command(['my_command'], timeout=_TIMEOUT)

    self.assertEqual(output, b'fake_output')
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    expected_env['ADB_SERVER_SOCKET'] = 'tcp:localhost:5037'
    self.assertEqual(mock_check_output.call_count, 2)
    mock_check_output.assert_has_calls([
        mock.call(
            ['my_adb', '-s', 'awesome_device', 'my_command'],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-s', 'awesome_device', 'my_command'],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
    ])
    mock_sleep.assert_not_called()

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_restart_server_skipped_when_disable_adb_kill_server_set(
      self, mock_sleep, mock_check_output
  ):
    """Do not restart server if DISABLE_ADB_KILL_SERVER is set."""

    os.environ['DISABLE_ADB_KILL_SERVER'] = '1'
    mock_check_output.side_effect = [
        subprocess.CalledProcessError(
            returncode=1, cmd='blah', output=b'some error output'
        ),
        'fake_output'.encode('utf-8'),
    ]
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            use_adb_server_port_from_os_env=True,
        )
    )

    output = adb_controller.execute_command(['my_command'], timeout=_TIMEOUT)

    self.assertEqual(output, b'fake_output')
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    expected_env['DISABLE_ADB_KILL_SERVER'] = '1'
    self.assertEqual(mock_check_output.call_count, 2)
    mock_check_output.assert_has_calls([
        mock.call(
            ['my_adb', '-s', 'awesome_device', 'my_command'],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-s', 'awesome_device', 'my_command'],
            stdin=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
    ])
    mock_sleep.assert_not_called()


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
