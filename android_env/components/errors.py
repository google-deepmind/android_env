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

"""Definitions of exceptions used by AndroidEnv."""


class ReadObservationError(Exception):
  """When the environment is unable to obtain an observation from a simulator."""

  ERROR_CODE = 1


class CoordinatorError(Exception):
  """Error raised by the Coordinator."""

  ERROR_CODE = 2


class TooManyRestartsError(CoordinatorError):
  """The number of restarts has exceeded _MAX_RESTART_TRIES."""

  ERROR_CODE = 3


class AdbControllerError(Exception):
  """Errors that can be raised by ADBController."""

  ERROR_CODE = 4


class AdbControllerDeviceTimeoutError(AdbControllerError):
  """Raised when a device takes too long to respond."""

  ERROR_CODE = 5


class SimulatorError(Exception):
  """Errors that can be raised by a simulator."""

  ERROR_CODE = 6


class SendActionError(Exception):
  """Raised when action couldn't be sent successfully."""

  ERROR_CODE = 7


class StepCommandError(Exception):
  """Raised when setup step interpreter cannot process a command."""

  ERROR_CODE = 8


class WaitForAppScreenError(StepCommandError):
  """Raised when the wait_for_app_screen success check is not met."""

  ERROR_CODE = 9


class CheckInstallError(StepCommandError):
  """Raised when the check_install success check is not met."""

  ERROR_CODE = 10
