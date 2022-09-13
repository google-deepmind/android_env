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

"""Tests for errors.py."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import errors


class ErrorsTest(parameterized.TestCase):

  @parameterized.parameters(
      (errors.ReadObservationError, 1),
      (errors.CoordinatorError, 2),
      (errors.TooManyRestartsError, 3),
      (errors.AdbControllerError, 4),
      (errors.AdbControllerDeviceTimeoutError, 5),
      (errors.SimulatorError, 6),
      (errors.SendActionError, 7),
      (errors.StepCommandError, 8),
      (errors.WaitForAppScreenError, 9),
      (errors.CheckInstallError, 10),
  )
  def test_error_codes(self, error, expected_error_code):
    with self.assertRaises(error) as context:
      raise error()
    self.assertEqual(context.exception.ERROR_CODE, expected_error_code)

  def test_error_codes_unique(self):
    error_codes = set()
    errors_list = (
        errors.ReadObservationError,
        errors.CoordinatorError,
        errors.TooManyRestartsError,
        errors.AdbControllerError,
        errors.AdbControllerDeviceTimeoutError,
        errors.SimulatorError,
        errors.SendActionError,
        errors.StepCommandError,
        errors.WaitForAppScreenError,
        errors.CheckInstallError,
    )
    for error in errors_list:
      self.assertNotIn(error.ERROR_CODE, error_codes)
      error_codes.add(error.ERROR_CODE)

  @parameterized.parameters([
      errors.ReadObservationError(),
      errors.CoordinatorError(),
      errors.TooManyRestartsError(),
      errors.AdbControllerError(),
      errors.AdbControllerDeviceTimeoutError(),
      errors.SimulatorError(),
      errors.SendActionError(),
      errors.StepCommandError(),
      errors.WaitForAppScreenError(),
      errors.CheckInstallError(),
  ])
  def test_all_errors_are_androidenv_errors(self, error):
    self.assertIsInstance(error, errors.AndroidEnvError)


if __name__ == '__main__':
  absltest.main()
