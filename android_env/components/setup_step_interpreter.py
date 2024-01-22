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

"""A component that parses and processes SetupSteps."""

from collections.abc import Sequence
import copy
import time
from typing import Any

from absl import logging
from android_env.components import adb_call_parser as adb_call_parser_lib
from android_env.components import app_screen_checker
from android_env.components import errors
from android_env.proto import adb_pb2
from android_env.proto import task_pb2


class SetupStepInterpreter:
  """An interpreter for SetupSteps."""

  def __init__(self, adb_call_parser: adb_call_parser_lib.AdbCallParser):
    """Initializes this interpreter.

    Args:
      adb_call_parser: An object to communicate with Android via ADB.
    """
    self._adb_call_parser = adb_call_parser
    self._stats = {
        'error_count_adb_request': 0,
        'error_count_wait_for_app_screen': 0,
        'error_count_check_install': 0,
        'error_count_wait_for_message': 0,
        'total_time_waiting_for_app_screen': 0
    }

  def stats(self) -> dict[str, Any]:
    return copy.deepcopy(self._stats)

  def interpret(self, setup_steps: Sequence[task_pb2.SetupStep]) -> None:
    """Returns True if parsing and processing `setup_steps` is successful."""
    if setup_steps:
      logging.info('Executing setup steps: %s', setup_steps)
      for step in setup_steps:
        self._process_step_command(step)
      logging.info('Done executing setup steps.')

  def _process_step_command(self, step_cmd: task_pb2.SetupStep) -> None:
    """Processes a single step command from a reset or extra setup."""

    if not step_cmd:
      logging.info('Empty step_cmd')
      return

    logging.info('Executing step_cmd: %r', step_cmd)
    step_type = step_cmd.WhichOneof('step')
    success_condition = step_cmd.success_condition
    success_check = success_condition.WhichOneof('check')
    assert step_type or success_check, (
        'At least one of step and success_condition must be defined.')

    num_tries = 0
    max_retries = max(success_condition.num_retries, 3)
    latest_error = None
    while num_tries < max_retries:

      num_tries += 1

      try:
        unused_adb_response = self._execute_step_cmd(step_cmd, step_type)
        time.sleep(0.5)
        self._check_success(success_check, success_condition)
        return

      except NotImplementedError:
        logging.exception('Not implemented error! Skipping this step command.')
        return

      except errors.AdbControllerError as error:
        latest_error = error
        self._stats['error_count_adb_request'] += 1
        logging.exception('ADB call [%r] has failed. Try %d of %d.',
                          step_cmd.adb_request, num_tries, max_retries)

      except errors.WaitForAppScreenError as error:
        latest_error = error
        self._stats['error_count_wait_for_app_screen'] += 1
        logging.exception('Failed to wait for app screen. Try %d of %d.',
                          num_tries, max_retries)

      except errors.CheckInstallError as error:
        latest_error = error
        self._stats['error_count_check_install'] += 1
        logging.exception('Package [%r] not installed. Try %d of %d.',
                          success_condition.check_install.package_name,
                          num_tries, max_retries)

    raise errors.StepCommandError(
        f'Step failed: [{step_cmd}]') from latest_error

  def _execute_step_cmd(
      self, step_cmd: task_pb2.SetupStep, step_type: str | None
  ) -> adb_pb2.AdbResponse | None:
    """Executes a step command of given type."""

    match step_type:
      case None:
        return None
      case 'sleep':
        time.sleep(step_cmd.sleep.time_sec)
        return None
      case 'adb_request':
        response = self._adb_call_parser.parse(step_cmd.adb_request)
        if response.status != adb_pb2.AdbResponse.Status.OK:
          raise errors.AdbControllerError(
              f'Failed to execute AdbRequest [{step_cmd.adb_request}].\n'
              f'Status: {response.status}\n'
              f'Error: {response.error_message}'
          )
        return response
      case _:
        raise NotImplementedError(f'No step command of type [{step_type}].')

  def _check_success(
      self,
      success_check: str | None,
      success_condition: task_pb2.SuccessCondition,
  ) -> None:
    """Checks whether the given success condition was met."""

    match success_check:
      case None:
        return None
      case 'wait_for_app_screen':
        wait_for_app_screen = success_condition.wait_for_app_screen
        screen_checker = app_screen_checker.AppScreenChecker(
            adb_call_parser=self._adb_call_parser,
            expected_app_screen=wait_for_app_screen.app_screen,
        )
        wait_time = screen_checker.wait_for_app_screen(
            timeout_sec=wait_for_app_screen.timeout_sec
        )
        self._stats['total_time_waiting_for_app_screen'] += wait_time
      case 'check_install':
        self._check_install(success_condition.check_install)
      case _:
        raise NotImplementedError(f'No success check called [{success_check}].')

  def _check_install(self, check_install: task_pb2.CheckInstall) -> None:
    """Checks that the given package is installed."""

    package = check_install.package_name
    logging.info('Checking if package is installed: [%r]', package)

    request = adb_pb2.AdbRequest(
        package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
            list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                packages=adb_pb2.AdbRequest.PackageManagerRequest.List.Packages(
                ))))

    start_time = time.time()
    while time.time() - start_time < check_install.timeout_sec:
      response = self._adb_call_parser.parse(request)
      if package in response.package_manager.list.items:
        logging.info('Done confirming that package is installed.')
        return
      time.sleep(0.1)

    logging.error('Package not found.')
    raise errors.CheckInstallError()
