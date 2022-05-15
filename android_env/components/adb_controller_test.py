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

"""Tests for android_env.components.adb_controller."""

import os
import time
from unittest import mock

from absl.testing import absltest
from android_env.components import adb_controller

# Timeout to be used by default in tests below. Set to a small value to avoid
# hanging on a failed test.
_TIMEOUT = 2


class AdbControllerTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._mock_execute_command = self.enter_context(
        mock.patch.object(
            adb_controller.AdbController, 'execute_command', autospec=True))
    self._adb_controller = adb_controller.AdbController(
        adb_path='my_adb', device_name='awesome_device', adb_server_port=9999)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_init_server(self, mock_sleep):
    self._adb_controller.init_server(timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(self._adb_controller,
                                                       ['devices'], _TIMEOUT)
    mock_sleep.assert_called_once()


class AdbControllerInitTest(absltest.TestCase):

  def test_deletes_problem_env_vars(self):
    os.environ['ANDROID_HOME'] = '/usr/local/Android/Sdk'
    os.environ['ANDROID_ADB_SERVER_PORT'] = '1337'
    adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        adb_server_port=9999,
        default_timeout=_TIMEOUT)
    self.assertNotIn('ANDROID_HOME', os.environ)
    self.assertNotIn('ANDROID_ADB_SERVER_PORT', os.environ)


if __name__ == '__main__':
  absltest.main()
