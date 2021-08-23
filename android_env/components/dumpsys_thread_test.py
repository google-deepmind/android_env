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

"""Tests for android_env.components.dumpsys_thread."""

from absl.testing import absltest
from android_env.components import app_screen_checker as screen_checker
from android_env.components import dumpsys_thread

import mock


class DumpsysThreadTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._dumpsys_thread = dumpsys_thread.DumpsysThread(
        app_screen_checker=mock.create_autospec(
            screen_checker.AppScreenChecker),
        check_frequency=1,
        max_failed_current_activity=5,
        block_input=True,
        block_output=True)

  def test_unexpected_activity(self):
    outcome = screen_checker.AppScreenChecker.Outcome.UNEXPECTED_ACTIVITY
    self._dumpsys_thread._app_screen_checker.matches_current_app_screen.return_value = outcome
    self._dumpsys_thread.write(
        dumpsys_thread.DumpsysThread.Signal.FETCH_DUMPSYS)
    v = self._dumpsys_thread.read(block=True)
    expected = dumpsys_thread.DumpsysThread.Signal.USER_EXITED_ACTIVITY
    self.assertEqual(expected, v)

  def test_unexpected_view_hierarchy(self):
    outcome = screen_checker.AppScreenChecker.Outcome.UNEXPECTED_VIEW_HIERARCHY
    self._dumpsys_thread._app_screen_checker.matches_current_app_screen.return_value = outcome
    self._dumpsys_thread.write(
        dumpsys_thread.DumpsysThread.Signal.FETCH_DUMPSYS)
    v = self._dumpsys_thread.read(block=True)
    expected = dumpsys_thread.DumpsysThread.Signal.USER_EXITED_VIEW_HIERARCHY
    self.assertEqual(expected, v)

  def test_success(self):
    outcome = screen_checker.AppScreenChecker.Outcome.SUCCESS
    self._dumpsys_thread._app_screen_checker.matches_current_app_screen.return_value = outcome
    self._dumpsys_thread.write(
        dumpsys_thread.DumpsysThread.Signal.FETCH_DUMPSYS)
    v = self._dumpsys_thread.read(block=True)
    expected = dumpsys_thread.DumpsysThread.Signal.OK
    self.assertEqual(expected, v)

  def test_not_requested(self):
    self._dumpsys_thread.write('wrong_signal')
    v = self._dumpsys_thread.read(block=True)
    expected = dumpsys_thread.DumpsysThread.Signal.DID_NOT_CHECK
    self.assertEqual(expected, v)

  def test_skipped(self):
    outcome = screen_checker.AppScreenChecker.Outcome.SUCCESS
    self._dumpsys_thread._app_screen_checker.matches_current_app_screen.return_value = outcome
    self._dumpsys_thread._check_frequency = 5
    self._dumpsys_thread._main_loop_counter = 0

    for _ in range(4):
      self._dumpsys_thread.write(
          dumpsys_thread.DumpsysThread.Signal.FETCH_DUMPSYS)
      v = self._dumpsys_thread.read(block=True)
      expected = dumpsys_thread.DumpsysThread.Signal.DID_NOT_CHECK
      self.assertEqual(expected, v)

    self._dumpsys_thread.write(
        dumpsys_thread.DumpsysThread.Signal.FETCH_DUMPSYS)
    v = self._dumpsys_thread.read(block=True)
    expected = dumpsys_thread.DumpsysThread.Signal.OK
    self.assertEqual(expected, v)


if __name__ == '__main__':
  absltest.main()
