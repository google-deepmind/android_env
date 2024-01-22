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

"""Tests for android_env.components.dumpsys_thread."""

from unittest import mock

from absl.testing import absltest
from android_env.components import app_screen_checker as screen_checker
from android_env.components import dumpsys_thread


class DumpsysThreadTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._app_screen_checker = mock.create_autospec(
        screen_checker.AppScreenChecker)

  def test_unexpected_activity(self):
    dumpsys = dumpsys_thread.DumpsysThread(
        app_screen_checker=self._app_screen_checker, check_frequency=1)
    outcome = screen_checker.AppScreenChecker.Outcome.UNEXPECTED_ACTIVITY
    self._app_screen_checker.matches_current_app_screen.return_value = outcome
    # The first time that `check_user_exited()` is called, it'll only trigger
    # the processing, but it should return immediately.
    self.assertFalse(dumpsys.check_user_exited(timeout=1.0))
    # The second time it should then wait for the result.
    self.assertTrue(dumpsys.check_user_exited(timeout=1.0))

  def test_unexpected_view_hierarchy(self):
    dumpsys = dumpsys_thread.DumpsysThread(
        app_screen_checker=self._app_screen_checker, check_frequency=1)
    outcome = screen_checker.AppScreenChecker.Outcome.UNEXPECTED_VIEW_HIERARCHY
    self._app_screen_checker.matches_current_app_screen.return_value = outcome
    self.assertFalse(dumpsys.check_user_exited(timeout=1.0))
    self.assertTrue(dumpsys.check_user_exited(timeout=1.0))

  def test_success(self):
    dumpsys = dumpsys_thread.DumpsysThread(
        app_screen_checker=self._app_screen_checker, check_frequency=1)
    outcome = screen_checker.AppScreenChecker.Outcome.SUCCESS
    self._app_screen_checker.matches_current_app_screen.return_value = outcome
    self.assertFalse(dumpsys.check_user_exited(timeout=1.0))
    self.assertFalse(dumpsys.check_user_exited(timeout=1.0))

  def test_skipped(self):
    dumpsys = dumpsys_thread.DumpsysThread(
        app_screen_checker=self._app_screen_checker, check_frequency=5)
    self._app_screen_checker.matches_current_app_screen.side_effect = [
        screen_checker.AppScreenChecker.Outcome.SUCCESS,
        screen_checker.AppScreenChecker.Outcome.FAILED_ACTIVITY_EXTRACTION
    ]

    for _ in range(17):
      self.assertFalse(dumpsys.check_user_exited(timeout=1.0))

    # The first 4 calls will hit the early exit from `check_frequency`.
    # The 5th call will trigger the processing (increasing the call count to
    # matches_current_app_screen() by 1), but it should return early.
    # The 10th call will find a result of the previous processing, and it should
    # be SUCCESS.
    # The next 4 calls (11, 12, 13, 14) will hit the early exit from
    # `check_frequency`.
    # The 15th call should trigger the processing again (increasing the call
    # count to matches_current_app_screen() by 1), but it should return early.
    # The next 2 calls (16, 17) will hit the early exit from `check_frequency`.
    # In total there should be only two calls to `matches_current_app_screen()`.
    expected_call_count = 2
    self.assertEqual(
        self._app_screen_checker.matches_current_app_screen.call_count,
        expected_call_count)


if __name__ == '__main__':
  absltest.main()
