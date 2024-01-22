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

"""Tests for android_env.components.setup_step_interpreter."""

from unittest import mock

from absl.testing import absltest
from android_env.components import adb_call_parser
from android_env.components import errors
from android_env.components import setup_step_interpreter
from android_env.proto import adb_pb2
from android_env.proto import task_pb2

from google.protobuf import text_format


def _to_proto(proto_class, text):
  proto = proto_class()
  text_format.Parse(text, proto)
  return proto


class SetupStepInterpreterTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._parser = mock.create_autospec(
        adb_call_parser.AdbCallParser, instance=True)

  def test_empty_setup_steps(self):
    """Simple test where nothing should break, and nothing should be done.

    The test simply expects this test to not crash.
    """
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([])

  def test_none_setup_steps(self):
    """Simple test where nothing should break, and nothing should be done.

    The test simply expects this test to not crash.
    """
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    # Empty setup steps should be ignored.
    interpreter.interpret([])

  def test_invalid_setup_step(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    # Empty setup steps should be ignored.
    self.assertRaises(AssertionError, interpreter.interpret,
                      [task_pb2.SetupStep()])

  def test_adb_install_apk_filesystem(self):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_request: {
  install_apk: {
    filesystem: {
      path: "/my/favorite/dir/my_apk.apk"
    }
  }
}""")
    ])
    self._parser.parse.assert_called_once_with(
        adb_pb2.AdbRequest(
            install_apk=adb_pb2.AdbRequest.InstallApk(
                filesystem=adb_pb2.AdbRequest.InstallApk.Filesystem(
                    path='/my/favorite/dir/my_apk.apk'))))

  def test_adb_force_stop(self):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_request: { force_stop: { package_name: "my.app.Activity" } }""")
    ])
    self._parser.parse.assert_called_once_with(
        adb_pb2.AdbRequest(
            force_stop=adb_pb2.AdbRequest.ForceStop(
                package_name='my.app.Activity')))

  def test_adb_start_activity(self):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_request: {
  start_activity: {
    full_activity: "my.app.Activity"
    extra_args: "arg1"
    extra_args: "arg2"
  }
}""")
    ])
    self._parser.parse.assert_called_once_with(
        adb_pb2.AdbRequest(
            start_activity=adb_pb2.AdbRequest.StartActivity(
                full_activity='my.app.Activity', extra_args=['arg1', 'arg2'])))

  def test_adb_single_tap(self):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep, """
adb_request: {
  tap: {
    x: 321
    y: 654
  }
}""")
    ])
    self._parser.parse.assert_called_once_with(
        adb_pb2.AdbRequest(tap=adb_pb2.AdbRequest.Tap(x=321, y=654)))

  def test_adb_press_button(self):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_request: { press_button: { button: HOME } }""")
    ])
    self._parser.parse.assert_called_once_with(
        adb_pb2.AdbRequest(
            press_button=adb_pb2.AdbRequest.PressButton(
                button=adb_pb2.AdbRequest.PressButton.Button.HOME)))

    self._parser.reset_mock()
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_request: { press_button: { button: BACK } }""")
    ])
    self._parser.parse.assert_called_once_with(
        adb_pb2.AdbRequest(
            press_button=adb_pb2.AdbRequest.PressButton(
                button=adb_pb2.AdbRequest.PressButton.Button.BACK)))

  def test_adb_start_screen_pinning(self):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_request: {
  start_screen_pinning: {
    full_activity: "my.app.HighlanderApp"  # "There can be only one".
  }
}""")
    ])
    self._parser.parse.assert_called_once_with(
        adb_pb2.AdbRequest(
            start_screen_pinning=adb_pb2.AdbRequest.StartScreenPinning(
                full_activity='my.app.HighlanderApp')))

  @mock.patch('time.sleep')
  def test_time_sleep(self, mock_sleep):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret(
        [_to_proto(task_pb2.SetupStep, """sleep: { time_sec: 0.875 }""")])
    assert mock_sleep.call_count == 2
    mock_sleep.assert_has_calls([mock.call(0.875), mock.call(0.5)])

  @mock.patch('time.sleep')
  def test_wait_for_app_screen_empty_activity(self, unused_mock_sleep):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    with self.assertRaises(errors.StepCommandError):
      interpreter.interpret([
          _to_proto(task_pb2.SetupStep,
                    """success_condition: {wait_for_app_screen: { }}""")
      ])

  @mock.patch('time.sleep')
  def test_check_install_not_installed(self, unused_mock_sleep):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
            list=adb_pb2.AdbResponse.PackageManagerResponse.List(items=[
                'com.some.package',
                'not.what.you.are.looking.for',
            ])))
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    with self.assertRaises(errors.StepCommandError):
      interpreter.interpret([
          _to_proto(
              task_pb2.SetupStep, """
success_condition: {
  check_install: {
    package_name: "faz"
    timeout_sec: 0.0001
  }
}
""")
      ])

  def test_check_install_installed(self):
    self._parser.parse.return_value = adb_pb2.AdbResponse(
        package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
            list=adb_pb2.AdbResponse.PackageManagerResponse.List(items=[
                'com.some.package',
                'baz',
            ])))
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    # The test checks that this command raises no AssertionError.
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
success_condition: {
  check_install: {
    package_name: "baz"
    timeout_sec: 0.0001
  }
}""")
    ])

  def test_num_retries_failure(self):
    self._parser.parse.side_effect = [
        adb_pb2.AdbResponse(
            package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
                list=adb_pb2.AdbResponse.PackageManagerResponse.List(
                    items=[]))),
    ] * 3
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    with self.assertRaises(errors.StepCommandError):
      interpreter.interpret([
          _to_proto(
              task_pb2.SetupStep, """
success_condition: {
  check_install: {
    package_name: "faz"
    timeout_sec: 0.0001
  }
  num_retries: 3
}""")
      ])
    # We retried 3 times after the first call, so we expect 3+1 calls.
    self.assertEqual(self._parser.parse.call_count, 3)

  @mock.patch('time.sleep')
  def test_num_retries_success(self, unused_mock_sleep):
    self._parser.parse.side_effect = [
        adb_pb2.AdbResponse(
            package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
                list=adb_pb2.AdbResponse.PackageManagerResponse.List(
                    items=[]))),
        adb_pb2.AdbResponse(
            package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
                list=adb_pb2.AdbResponse.PackageManagerResponse.List(
                    items=[]))),
        adb_pb2.AdbResponse(
            package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
                list=adb_pb2.AdbResponse.PackageManagerResponse.List(items=[
                    'com.some.package',
                    'bar',
                ]))),
        adb_pb2.AdbResponse(
            package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
                list=adb_pb2.AdbResponse.PackageManagerResponse.List(items=[])))
    ]
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
success_condition: {
  check_install: {
    package_name: "bar"
    timeout_sec: 0.0001
  }
  num_retries: 5
}""")
    ])
    # The check should succeed on the third try.
    self.assertEqual(self._parser.parse.call_count, 3)

  def test_retry_step(self):
    self._parser.parse.side_effect = [
        adb_pb2.AdbResponse(
            package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
                list=adb_pb2.AdbResponse.PackageManagerResponse.List(
                    items=[]))),
        adb_pb2.AdbResponse(
            package_manager=adb_pb2.AdbResponse.PackageManagerResponse(
                list=adb_pb2.AdbResponse.PackageManagerResponse.List(items=[
                    'com.some.package',
                    'bar',
                ]))),
    ]
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_call_parser=self._parser)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
success_condition: {
  check_install: {
    package_name: "bar"
    timeout_sec: 0.0001
  }
  num_retries: 2
}""")
    ])
    # We expect the check to fail once and succeed on the second pass.
    self.assertEqual(self._parser.parse.call_count, 2)


if __name__ == '__main__':
  absltest.main()
