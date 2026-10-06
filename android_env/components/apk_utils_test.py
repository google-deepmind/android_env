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

"""Unit tests for apk_utils in android_env.components."""

from unittest import mock

from absl.testing import absltest
from android_env.components import apk_utils
from android_env.google.resource_utils import apk_utils as google_apk_utils
from android_env.proto import task_pb2


class ApkUtilsTest(absltest.TestCase):

  @mock.patch.object(google_apk_utils, 'fetch_apks_for_task', autospec=True)
  def test_fetch_apks_for_task_default_tmp_dir(self, mock_fetch):
    task = task_pb2.Task(id='test_task')
    expected_task = task_pb2.Task(id='test_task_resolved')
    mock_fetch.return_value = expected_task

    result = apk_utils.fetch_apks_for_task(task)

    mock_fetch.assert_called_once()
    called_args = mock_fetch.call_args[0]
    self.assertEqual(called_args[0], task)
    self.assertIsInstance(called_args[1], str)
    self.assertEqual(result, expected_task)

  @mock.patch.object(google_apk_utils, 'fetch_apks_for_task', autospec=True)
  def test_fetch_apks_for_task_custom_tmp_dir(self, mock_fetch):
    task = task_pb2.Task(id='test_task')
    expected_task = task_pb2.Task(id='test_task_resolved')
    mock_fetch.return_value = expected_task

    custom_dir = '/tmp/my_custom_dir'
    result = apk_utils.fetch_apks_for_task(task, custom_dir)

    mock_fetch.assert_called_once_with(task, custom_dir)
    self.assertEqual(result, expected_task)


if __name__ == '__main__':
  absltest.main()
