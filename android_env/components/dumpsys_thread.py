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

"""A ThreadFunction that runs and parses adb dumpsys."""

import concurrent.futures

from absl import logging
from android_env.components import app_screen_checker as app_screen_checker_lib

_Outcome = app_screen_checker_lib.AppScreenChecker.Outcome


class DumpsysThread:
  """A thread that checks if the user is in the expected app screen."""

  def __init__(
      self,
      app_screen_checker: app_screen_checker_lib.AppScreenChecker,
      check_frequency: int = 10,
      max_failed_current_activity: int = 10,
  ):
    """Initializes the dumpsys reader thread.

    This loops forever checking if the user is in the expected screen dictated
    by `app_screen_checker`. These analyses are too expensive to be in the
    critical path of AndroidEnv::step() so we consume them async from this
    separate thread.

    Args:
      app_screen_checker: The class that actually determines if the current
          screen matches the expected screen.
      check_frequency: Integer. We only call dumpsys 1/check_frequency times in
          each iteration of the while loop below.
      max_failed_current_activity: Integer. We try to fetch the current activity
          but sometimes it fails. If it fails more than
          `max_failed_current_activity` consecutive times, we declare that the
          user has exited `expected_activity`.
    """

    self._app_screen_checker = app_screen_checker
    self._main_loop_counter = 0
    self._check_frequency = check_frequency
    self._max_failed_activity_extraction = max_failed_current_activity
    self._num_failed_activity_extraction = 0
    self._latest_check: concurrent.futures.Future | None = None

  def check_user_exited(self, timeout: float | None = None) -> bool:
    """Returns True if the user is not in the expected screen.

    Args:
      timeout: An optional time in seconds to block waiting for the result of
        the (expensive) checking operation. If None, the function will return
        immediately with `False`.

    Returns:
      Whether the user of the Android device has exited the expected screen
      determined by `AppScreenChecker` given at __init__().
    """

    # Update and check loop_counter against check_frequency.
    self._main_loop_counter += 1
    if (self._check_frequency <= 0 or
        self._main_loop_counter < self._check_frequency):
      return False
    self._main_loop_counter = 0

    # If the latest check is None, perform a check and return.
    if self._latest_check is None:
      with concurrent.futures.ThreadPoolExecutor() as executor:
        self._latest_check = executor.submit(self._check_impl)
      return False

    # If there's a check in flight, continue only if it's finished.
    if not timeout and not self._latest_check.done():
      return False

    v = self._latest_check.result(timeout=timeout)
    self._latest_check = None  # Reset the check.
    return v

  def _check_impl(self) -> bool:
    """The synchronous implementation of Dumpsys."""

    outcome = self._app_screen_checker.matches_current_app_screen()

    # We were unable to determine the current activity.
    if outcome == _Outcome.FAILED_ACTIVITY_EXTRACTION:
      self._num_failed_activity_extraction += 1
      logging.info('self._num_failed_activity_extraction: %s',
                   self._num_failed_activity_extraction)
      if (self._num_failed_activity_extraction >=
          self._max_failed_activity_extraction):
        logging.error('Maximum number of failed activity extraction reached.')
        self._num_failed_activity_extraction = 0
        return True
    else:
      self._num_failed_activity_extraction = 0

    # The current app screen matches all expectations.
    if (outcome == _Outcome.SUCCESS or
        outcome == _Outcome.EMPTY_EXPECTED_ACTIVITY):
      return False

    # Player has exited the app. Terminate the episode.
    elif outcome == _Outcome.UNEXPECTED_ACTIVITY:
      return True

    # Player has exited the main game. Terminate the episode.
    elif outcome == _Outcome.UNEXPECTED_VIEW_HIERARCHY:
      return True

    return False
