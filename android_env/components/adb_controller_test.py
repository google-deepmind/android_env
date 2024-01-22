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

"""Tests for android_env.components.adb_controller."""

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
    # Set two env vars.
    os.environ['MY_ENV_VAR'] = '/some/path/'
    os.environ['HOME'] = '$MY_ENV_VAR'
    self._env_before = os.environ
    self._adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
        )
    )

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_init_server(self, mock_sleep, mock_check_output):
    # Arrange.
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
        )
    )

    # Act.
    adb_controller.init_server(timeout=_TIMEOUT)

    # Assert.
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    mock_check_output.assert_called_once_with(
        ['my_adb', '-P', '9999', 'devices'],
        stderr=subprocess.STDOUT,
        timeout=_TIMEOUT,
        env=expected_env,
    )
    mock_sleep.assert_called_once()

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_restart_server(self, mock_sleep, mock_check_output):
    # Arrange.
    mock_check_output.side_effect = [
        subprocess.CalledProcessError(returncode=1, cmd='blah'),
    ] + ['fake_output'.encode('utf-8')] * 4
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
        )
    )

    # Act.
    adb_controller.execute_command(['my_command'], timeout=_TIMEOUT)

    # Assert.
    expected_env = self._env_before
    expected_env['HOME'] = '/some/path/'
    mock_check_output.assert_has_calls([
        mock.call(
            ['my_adb', '-P', '9999', '-s', 'awesome_device', 'my_command'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-P', '9999', 'kill-server'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-P', '9999', 'start-server'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-P', '9999', 'devices'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
        mock.call(
            ['my_adb', '-P', '9999', '-s', 'awesome_device', 'my_command'],
            stderr=subprocess.STDOUT,
            timeout=_TIMEOUT,
            env=expected_env,
        ),
    ])
    mock_sleep.assert_has_calls(
        [mock.call(0.2), mock.call(2.0), mock.call(0.2)])

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_invalid_command(self, mock_sleep, mock_check_output):
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
            adb_server_port=9999,
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
                ['my_adb', '-P', '9999', '-s', 'awesome_device', 'my_command'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', '-P', '9999', 'kill-server'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', '-P', '9999', 'start-server'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', '-P', '9999', 'devices'],
                stderr=subprocess.STDOUT,
                timeout=_TIMEOUT,
                env=expected_env,
            ),
            mock.call(
                ['my_adb', '-P', '9999', '-s', 'awesome_device', 'my_command'],
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
    del mock_sleep
    mock_check_output.side_effect = subprocess.CalledProcessError(
        returncode=1, cmd='blah')
    adb_controller = adb_controller_lib.AdbController(
        config_classes.AdbControllerConfig(
            adb_path='my_adb',
            device_name='awesome_device',
            adb_server_port=9999,
        )
    )
    self.assertRaises(
        errors.AdbControllerError,
        adb_controller.execute_command, ['my_command'], timeout=_TIMEOUT)


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


if __name__ == '__main__':
  absltest.main()
