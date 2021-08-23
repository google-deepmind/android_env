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

"""Tests for android_env.components.setup_step_interpreter."""

from absl.testing import absltest
from android_env.components import adb_controller
from android_env.components import errors
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.proto import task_pb2
import mock

from google.protobuf import text_format


def _to_proto(proto_class, text):
  proto = proto_class()
  text_format.Parse(text, proto)
  return proto


class SetupStepInterpreterTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.logcat = mock.create_autospec(logcat_thread.LogcatThread)
    self.adb_controller = mock.create_autospec(adb_controller.AdbController)

  def test_empty_setup_steps(self):
    """Simple test where nothing should break, and nothing should be done.

    The test simply expects this test to not crash.
    """
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([])

  def test_none_setup_steps(self):
    """Simple test where nothing should break, and nothing should be done.

    The test simply expects this test to not crash.
    """
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    # Empty setup steps should be ignored.
    interpreter.interpret([None])

  def test_invalid_setup_step(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    # Empty setup steps should be ignored.
    with self.assertRaises(AssertionError):
      interpreter.interpret([_to_proto(task_pb2.SetupStep, '')])

  def test_adb_install_apk_filesystem(self):

    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: {
  install_apk: {
    filesystem: {
      path: "/my/favorite/dir/my_apk.apk"
    }
  }
}""")
    ])
    self.adb_controller.install_apk.assert_called_once_with(
        '/my/favorite/dir/my_apk.apk')

  def test_adb_force_stop(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: { force_stop: { package_name: "my.app.Activity" } }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.force_stop.assert_called_once_with('my.app.Activity')

  def test_adb_clear_cache(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: { clear_cache: { package_name: "my.app.Activity" } }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.clear_cache.assert_called_once_with('my.app.Activity')

  def test_adb_grant_permissions(self):

    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: {
  grant_permissions: {
    package_name: "my.app.Activity"
    permissions: [ "my.namespace.READ_DATA", "another.namespace.WRITE" ]
  }
}""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.grant_permissions.assert_called_once_with(
        'my.app.Activity',
        ['my.namespace.READ_DATA', 'another.namespace.WRITE'])

  def test_adb_start_activity(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: {
  start_activity: {
    full_activity: "my.app.Activity"
    extra_args: "arg1"
    extra_args: "arg2"
  }
}""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.start_activity.assert_called_once_with(
        'my.app.Activity', ['arg1', 'arg2'])

  def test_adb_single_tap(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep, """
adb_call: {
  tap: {
    x: 321
    y: 654
  }
}""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.input_tap.assert_called_once_with(321, 654)

  def test_adb_rotate(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    # Check landscape.
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_call: { rotate: { orientation: LANDSCAPE_90 } }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.rotate_device.assert_called_once_with(
        task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_90)

    self.adb_controller.reset_mock()
    # Check portrait.
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_call: { rotate: { orientation: PORTRAIT_0 } }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.rotate_device.assert_called_once_with(
        task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_0)

    self.adb_controller.reset_mock()
    # Check landscape inverted.
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_call: { rotate: { orientation: LANDSCAPE_270} }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.rotate_device.assert_called_once_with(
        task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_270)

    self.adb_controller.reset_mock()
    # Check portrait up-side-down.
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_call: { rotate: { orientation: PORTRAIT_180 } }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.rotate_device.assert_called_once_with(
        task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_180)

  def test_adb_press_button(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_call: { press_button: { button: HOME } }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.input_key.assert_called_once_with('KEYCODE_HOME')
    self.adb_controller.reset_mock()
    interpreter.interpret([
        _to_proto(task_pb2.SetupStep,
                  """ adb_call: { press_button: { button: BACK } }""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.input_key.assert_called_once_with('KEYCODE_BACK')

  def test_adb_start_accessibility_service(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: {
  start_accessibility_service: {
    full_service: "my.app.AccessibilityService"
  }
}""")
    ])
    # AdbController should be called exactly once with the following arguments.
    self.adb_controller.start_accessibility_service.assert_called_once_with(
        'my.app.AccessibilityService')

  def test_adb_start_screen_pinning(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: {
  start_screen_pinning: {
    full_activity: "my.app.HighlanderApp"  # "There can be only one".
  }
}""")
    ])
    # AdbController should be called once with the following arguments.
    self.adb_controller.start_screen_pinning.assert_called_with(
        u'my.app.HighlanderApp')

  @mock.patch('time.sleep')
  def test_time_sleep(self, mock_sleep):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret(
        [_to_proto(task_pb2.SetupStep, """sleep: { time_sec: 0.875 }""")])
    assert mock_sleep.call_count == 2
    mock_sleep.assert_has_calls([mock.call(0.875), mock.call(0.5)])

  @mock.patch('time.sleep')
  def test_wait_for_app_screen_empty_activity(self, unused_mock_sleep):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    with self.assertRaises(errors.StepCommandError):
      interpreter.interpret([
          _to_proto(task_pb2.SetupStep,
                    """success_condition: {wait_for_app_screen: { }}""")
      ])

  def test_wait_for_message_fail(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    self.assertRaises(errors.StepCommandError, interpreter.interpret, [
        _to_proto(
            task_pb2.SetupStep, """
success_condition: {
  wait_for_message: {
    message:'foo'
    timeout_sec: 0.0001
  }
}
""")
    ])

  def test_wait_for_message_success(self):
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)

    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away, ignoring `event`.
    def mock_add_ev_listener(event_listener):
      event_listener.handler_fn('some_event', 'some_match')

    self.logcat.add_event_listener.side_effect = mock_add_ev_listener
    # The test checks that this command raises no AssertionError.
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
success_condition: {
  wait_for_message: {
    message:'foo'
    timeout_sec: 1.0
  }
}
""")
    ])

  @mock.patch('time.sleep')
  def test_check_install_not_installed(self, unused_mock_sleep):
    self.adb_controller.is_package_installed.return_value = False
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
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
    self.adb_controller.is_package_installed.return_value = True
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
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
    self.adb_controller.is_package_installed.assert_called_once_with('baz')

  def test_num_retries_failure(self):
    self.adb_controller.is_package_installed.side_effect = [False] * 3
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
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
    self.assertEqual(3, self.adb_controller.is_package_installed.call_count)

  @mock.patch('time.sleep')
  def test_num_retries_success(self, unused_mock_sleep):
    self.adb_controller.is_package_installed.side_effect = [
        False, False, True, False
    ]
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
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
    self.assertEqual(3, self.adb_controller.is_package_installed.call_count)

  def test_retry_step(self):
    self.adb_controller.is_package_installed.side_effect = [False, True]
    interpreter = setup_step_interpreter.SetupStepInterpreter(
        adb_controller=self.adb_controller, logcat=self.logcat)
    interpreter.interpret([
        _to_proto(
            task_pb2.SetupStep, """
adb_call: { press_button: { button: HOME } }
success_condition: {
  check_install: {
    package_name: "bar"
    timeout_sec: 0.0001
  }
  num_retries: 2
}""")
    ])
    # We expect the check to fail twice and succeed on the third pass.
    self.adb_controller.input_key.assert_has_calls(
        [mock.call('KEYCODE_HOME')] * 2)
    self.assertEqual(2, self.adb_controller.is_package_installed.call_count)


if __name__ == '__main__':
  absltest.main()
