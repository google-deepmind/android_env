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
      (errors.SimulatorError, 5),
      (errors.SendActionError, 6),
      (errors.StepCommandError, 7),
      (errors.WaitForAppScreenError, 8),
      (errors.CheckInstallError, 9),
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
      errors.SimulatorError(),
      errors.SendActionError(),
      errors.StepCommandError(),
      errors.WaitForAppScreenError(),
      errors.CheckInstallError(),
  ])
  def test_all_errors_are_androidenv_errors(self, error):
    self.assertIsInstance(error, errors.AndroidEnvError)

  @parameterized.named_parameters([
      ('less_than_zero', -1),
      # The largest `ERROR_CODE` is currently `CheckInstallError == 10`.
      ('greater_than_all_errors', 10 + 1),
      ('less_than_zero_float', -3.14159265),
      ('greater_than_all_errors_float', 123.456),
  ])
  def test_from_code_unsupported_code(self, code: int):
    """Unsupported errors should raise `RuntimeError`."""

    self.assertIsNone(errors.from_code(code))

  @parameterized.parameters([
      (-1, None, 'No such error code.'),
      (0, errors.AndroidEnvError, 'hello'),
      (0, errors.AndroidEnvError, ''),
      (1, errors.ReadObservationError, 'Could not read obs.'),
      (2, errors.CoordinatorError, 'Some error'),
      (3, errors.TooManyRestartsError, 'Too many already...'),
      (4, errors.AdbControllerError, 'Some adb error...'),
      (5, errors.SimulatorError, 'Simulator is not coping.'),
      (6, errors.SendActionError, 'Could not send action.'),
      (7, errors.StepCommandError, 'Some issue setting up the task.'),
      (8, errors.WaitForAppScreenError, 'Waited for too long!'),
      (9, errors.CheckInstallError, 'App did not install correctly.'),
  ])
  def test_from_code(self, code: int, expected_class: errors.AndroidEnvError,
                     msg: str):
    """`from_code` should produce consistent outputs for known errors."""

    error = errors.from_code(code, msg)
    if error is not None:
      self.assertIsInstance(error, expected_class)
      self.assertEqual(error.ERROR_CODE, code)
      self.assertEqual(str(error), msg)


if __name__ == '__main__':
  absltest.main()
