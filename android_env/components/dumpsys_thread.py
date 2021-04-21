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

"""A ThreadFunction that runs and parses adb dumpsys."""

import enum

from absl import logging

from android_env.components import app_screen_checker as screen_checker
from android_env.components import thread_function

AppScreenChecker = screen_checker.AppScreenChecker


class DumpsysThread(thread_function.ThreadFunction):
  """A class that executes dumpsys in a separate thread."""

  class Signal(enum.IntEnum):
    """Defines commands we can use to communicate with the dumpsys thread."""
    # To ask the thread to fetch dumpsys from Android.
    FETCH_DUMPSYS = 0
    # The user has left the activity that contains the AndroidEnv task.
    USER_EXITED_ACTIVITY = 1
    # The user exited the view hierarchy that we expect.
    USER_EXITED_VIEW_HIERARCHY = 2
    # App screen checker determined none of the errors above happened.
    OK = 3
    # App screen checker was not queried.
    DID_NOT_CHECK = 4

  def __init__(
      self,
      app_screen_checker: AppScreenChecker,
      check_frequency: int,
      max_failed_current_activity: int,
      block_input: bool,
      block_output: bool,
      name: str = 'dumpsys',
  ):
    """Initializes the dumpsys reader thread.

    This loops forever waiting for inputs from the main thread and outputting
    its analyses of the output of ADB dumpsys. These analyses are too expensive
    to be in the critical path of AndroidEnv::step() so we consume them async
    from this separate thread.

    Args:
      app_screen_checker: The class that actually determines if the current
          screen matches the expected screen.
      check_frequency: Integer. We only call dumpsys 1/check_frequency times in
          each iteration of the while loop below.
      max_failed_current_activity: Integer. We try to fetch the current activity
          but sometimes it fails. If it fails more than
          `max_failed_current_activity` consecutive times, we declare that the
          user has exited `expected_activity`.
      block_input: Whether to block this thread when reading its input queue.
      block_output: Whether to block this thread when writing to its output
        queue.
      name: Name of the thread.
    """

    self._app_screen_checker = app_screen_checker
    self._main_loop_counter = 0
    self._check_frequency = check_frequency
    self._max_failed_activity_extraction = max_failed_current_activity
    self._num_failed_activity_extraction = 0
    super().__init__(
        block_input=block_input, block_output=block_output, name=name)

  def main(self):
    v = self._read_value()
    if v != DumpsysThread.Signal.FETCH_DUMPSYS:
      self._write_value(DumpsysThread.Signal.DID_NOT_CHECK)
      return

    # Update and check loop_counter against check_frequency.
    self._main_loop_counter += 1
    if (self._check_frequency <= 0 or
        self._main_loop_counter < self._check_frequency):
      self._write_value(DumpsysThread.Signal.DID_NOT_CHECK)
      return
    self._main_loop_counter = 0

    outcome = self._app_screen_checker.matches_current_app_screen()

    # We were unable to determine the current activity.
    if outcome == AppScreenChecker.Outcome.FAILED_ACTIVITY_EXTRACTION:
      self._num_failed_activity_extraction += 1
      logging.info('self._num_failed_activity_extraction: %s',
                   self._num_failed_activity_extraction)
      if (self._num_failed_activity_extraction >=
          self._max_failed_activity_extraction):
        logging.error('Maximum number of failed activity extraction reached.')
        self._num_failed_activity_extraction = 0
        self._write_value(DumpsysThread.Signal.USER_EXITED_ACTIVITY)
        return
    else:
      self._num_failed_activity_extraction = 0

    # The current app screen matches all expectations.
    if (outcome == AppScreenChecker.Outcome.SUCCESS or
        outcome == AppScreenChecker.Outcome.EMPTY_EXPECTED_ACTIVITY):
      self._write_value(DumpsysThread.Signal.OK)
      return

    # Player has exited the app. Terminate the episode.
    elif outcome == AppScreenChecker.Outcome.UNEXPECTED_ACTIVITY:
      self._write_value(DumpsysThread.Signal.USER_EXITED_ACTIVITY)
      return

    # Player has exited the main game. Terminate the episode.
    elif outcome == AppScreenChecker.Outcome.UNEXPECTED_VIEW_HIERARCHY:
      self._write_value(DumpsysThread.Signal.USER_EXITED_VIEW_HIERARCHY)
      return
