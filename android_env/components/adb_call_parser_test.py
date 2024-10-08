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

import builtins
import os
import subprocess
import sys
import tempfile
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import adb_call_parser
from android_env.components import adb_controller
from android_env.proto import adb_pb2


class AdbCallParserTest(parameterized.TestCase):

  def test_unknown_command(self):
    """Gets UNKNOWN_COMMAND for an empty request."""
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    response = parser.parse(request)
    self.assertEqual(
        response.status, adb_pb2.AdbResponse.Status.UNKNOWN_COMMAND
    )

  def test_invalid_timeout(self):
    """AdbRequest.timeout_sec must be positive."""
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.tap.x = 123
    request.timeout_sec = -5
    response = parser.parse(request)
    self.assertEqual(
        response.status, adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
    )

  @mock.patch.object(os.path, 'exists', autospec=True)
  def test_install_apk_file_not_found(self, mock_exists):
    """Should fail installing APK when it is not found."""
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.install_apk.filesystem.path = '/my/home/game.apk'
    mock_exists.return_value = False

    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.INTERNAL_ERROR)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  @mock.patch.object(os.path, 'exists', autospec=True)
  def test_install_apk_successful(self, mock_exists):
    """Should succeed installing an arbitrary APK."""
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.install_apk.filesystem.path = '/my/home/game.apk'
    mock_exists.return_value = True

    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['install', '-r', '-t', '-g', '/my/home/game.apk'], None)

  @mock.patch.object(tempfile, 'NamedTemporaryFile', autospec=True)
  def test_install_apk_from_blob(self, mock_tempfile):
    """Should succeed installing APK from blob."""
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    blob_content = b'A fake blob content'
    request.install_apk.blob.contents = blob_content
    mock_tempfile.return_value.__enter__.return_value.name = '/my/home/test.apk'
    mock_tempfile.return_value.__enter__.return_value.write.return_value = None

    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['install', '-r', '-t', '-g', '/my/home/test.apk'], None
    )
    # pytype: disable=attribute-error
    mock_tempfile.assert_has_calls([
        mock.call(suffix='.apk'),  # Constructor
        mock.call().__enter__(),  # Enter context
        mock.call().__enter__().write(blob_content),  # Call write function
        mock.call().__exit__(None, None, None),  # Exit context
    ])
    # pytype: enable=attribute-error

  def test_start_activity_empty_full_activity(self):
    """A start_activity command should always have a nonempty activity."""
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_activity.extra_args.extend(['blah'])
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)

  def test_start_activity_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    command_output = (b'Stopping: my.project.SplashActivity\n'
                      b'Starting: Intent { cmp=my.project.SplashActivity }\n')
    adb.execute_command.return_value = command_output
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_activity.full_activity = 'my.project.SplashActivity'
    request.start_activity.extra_args.extend(['blah'])
    request.start_activity.force_stop = True
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_has_calls([
        mock.call([
            'shell', 'am', 'start', '-S', '-W', '-n',
            'my.project.SplashActivity', 'blah'
        ],
                  timeout=None),
    ])

  def test_start_activity_successful_no_force_stop(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    command_output = (b'Stopping: my.project.SplashActivity\n'
                      b'Starting: Intent { cmp=my.project.SplashActivity }\n')
    adb.execute_command.return_value = command_output
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_activity.full_activity = 'my.project.SplashActivity'
    request.start_activity.extra_args.extend(['blah'])
    request.start_activity.force_stop = False
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_has_calls([
        mock.call([
            'shell', 'am', 'start', '', '-W', '-n', 'my.project.SplashActivity',
            'blah'
        ],
                  timeout=None),
    ])

  def test_start_activity_error(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    command_output = (b'Stopping: my.project.SplashActivity\n'
                      b'Starting: Intent { cmp=my.project.SplashActivity }\n'
                      b'Error: Activity not started, unknown error code 101\n')
    adb.execute_command.return_value = command_output
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_activity.full_activity = 'my.project.SplashActivity'
    request.start_activity.extra_args.extend(['blah'])
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.INTERNAL_ERROR)
    self.assertEqual(
        response.error_message,
        f'start_activity failed with error: {str(command_output)}')

  def test_force_stop(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.force_stop.package_name = 'my.project'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'am', 'force-stop', 'my.project'], None)

  def test_grant_permissions_empty_package_name(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.package_manager.grant.permissions.extend(['perm1', 'perm2'])
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)

  def test_grant_permissions_empty_permissions(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.package_manager.grant.package_name = 'my.project'
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)

  def test_grant_permissions_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.package_manager.grant.package_name = 'my.project'
    request.package_manager.grant.permissions.extend(['perm1', 'perm2'])
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_has_calls([
        mock.call(['shell', 'pm', 'grant', 'my.project', 'perm1'], None),
        mock.call(['shell', 'pm', 'grant', 'my.project', 'perm2'], None),
    ])

  def test_press_button_invalid_button(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.press_button.button = 99999
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)

  def test_press_button_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b''
    parser = adb_call_parser.AdbCallParser(adb)
    # HOME.
    request = adb_pb2.AdbRequest()
    request.press_button.button = adb_pb2.AdbRequest.PressButton.Button.HOME
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_with(
        ['shell', 'input', 'keyevent', 'KEYCODE_HOME'], None)
    # BACK.
    request = adb_pb2.AdbRequest()
    request.press_button.button = adb_pb2.AdbRequest.PressButton.Button.BACK
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_with(
        ['shell', 'input', 'keyevent', 'KEYCODE_BACK'], None)
    # ENTER.
    request = adb_pb2.AdbRequest()
    request.press_button.button = adb_pb2.AdbRequest.PressButton.Button.ENTER
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_with(
        ['shell', 'input', 'keyevent', 'KEYCODE_ENTER'], None)

  def test_start_screen_pinning_package_not_found(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = (
        b'  taskId=12345: my.project.AnotherActivity visible=true'
        b'  topActivity=ComponentInfo{my.project.AnotherActivity}')
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_screen_pinning.full_activity = 'my.project.AmazingActivity'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.INTERNAL_ERROR)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'am', 'stack', 'list'], None)

  def test_start_screen_pinning_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = (
        b'  taskId=12345: my.project.AmazingActivity visible=true'
        b'  topActivity=ComponentInfo{my.project.AmazingActivity}')
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_screen_pinning.full_activity = 'my.project.AmazingActivity'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_has_calls([
        mock.call(['shell', 'am', 'stack', 'list'], None),
        mock.call(['shell', 'am', 'task', 'lock', '12345'], None),
    ])

  def test_start_screen_pinning_base_activity(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = (
        b'  taskId=12345: my.project.MainActivity visible=true'
        b'  topActivity=ComponentInfo{my.project.TopActivity}')
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_screen_pinning.full_activity = 'my.project.MainActivity'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_has_calls([
        mock.call(['shell', 'am', 'stack', 'list'], None),
        mock.call(['shell', 'am', 'task', 'lock', '12345'], None),
    ])

  def test_start_screen_pinning_top_activity(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = (
        b'  taskId=12345: my.project.MainActivity visible=true'
        b'  topActivity=ComponentInfo{my.project.TopActivity}')
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.start_screen_pinning.full_activity = 'my.project.TopActivity'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_has_calls([
        mock.call(['shell', 'am', 'stack', 'list'], None),
        mock.call(['shell', 'am', 'task', 'lock', '12345'], None),
    ])

  def test_send_broadcast_empty_action(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        send_broadcast=adb_pb2.AdbRequest.SendBroadcast())
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)

  def test_send_broadcast_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.send_broadcast.action = 'SOME-ACTION'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)

  def test_send_broadcast_with_component_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.send_broadcast.action = 'SOME-ACTION'
    request.send_broadcast.component = 'SOME-COMPONENT'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)

  def test_uninstall_package_empty_package_name(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.uninstall_package.package_name = ''
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)

  def test_uninstall_package_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'package:my.package'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest()
    request.uninstall_package.package_name = 'my.package'
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)

  def test_get_current_activity_no_visible_task(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = None
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        get_current_activity=adb_pb2.AdbRequest.GetCurrentActivity())
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.INTERNAL_ERROR)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_has_calls([
        mock.call(
            ['shell', 'am', 'stack', 'list', '|', 'grep', '-E', 'visible=true'],
            None),
        mock.call(['shell', 'am', 'stack', 'list'], None),
    ])

  def test_get_orientation_empty_dumpsys(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b''
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        get_orientation=adb_pb2.AdbRequest.GetOrientationRequest())
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.INTERNAL_ERROR)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(['shell', 'dumpsys', 'input'],
                                                None)

  def test_get_orientation_invalid_device_no_surface_orientation(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b' PhysicalWidth: -123px'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        get_orientation=adb_pb2.AdbRequest.GetOrientationRequest())
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.INTERNAL_ERROR)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(['shell', 'dumpsys', 'input'],
                                                None)

  @parameterized.named_parameters(
      ('rotation_0', b""" SurfaceOrientation: 0""", 0),
      ('rotation_90', b""" SurfaceOrientation: 1""", 1),
      ('rotation_180', b""" SurfaceOrientation: 2""", 2),
      ('rotation_270', b""" SurfaceOrientation: 3""", 3),
      ('rotation_0_new', b""" InputDeviceOrientation: 0""", 0),
      ('rotation_90_new', b""" InputDeviceOrientation: 1""", 1),
      ('rotation_180_new', b""" InputDeviceOrientation: 2""", 2),
      ('rotation_270_new', b""" InputDeviceOrientation: 3""", 3),
  )
  def test_get_orientation_success(
      self, orientation: bytes, expected_orientation: int
  ):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = (
        b"""SomeRandomKey: 12345\n""" + orientation + b"""
    MoreRandomStuff: awesome_value
"""
    )

    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        get_orientation=adb_pb2.AdbRequest.GetOrientationRequest())
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.get_orientation.orientation, expected_orientation)
    adb.execute_command.assert_called_once_with(['shell', 'dumpsys', 'input'],
                                                None)

  def test_get_current_activity_no_matches(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        get_current_activity=adb_pb2.AdbRequest.GetCurrentActivity())
    for platform in ['win32', 'linux']:
      with mock.patch.object(
          sys, 'platform', autospec=True, return_value=platform):
        response = parser.parse(request)
        self.assertEqual(response.status,
                         adb_pb2.AdbResponse.Status.INTERNAL_ERROR)
        self.assertNotEmpty(response.error_message)
        adb.execute_command.assert_has_calls([
            mock.call([
                'shell', 'am', 'stack', 'list', '|', 'grep', '-E',
                'visible=true'
            ], None),
            mock.call(['shell', 'am', 'stack', 'list'], None),
        ])

  def test_get_current_activity_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'{MyAwesomeActivity}'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        get_current_activity=adb_pb2.AdbRequest.GetCurrentActivity())
    for platform in ['win32', 'linux']:
      with mock.patch.object(
          sys, 'platform', autospec=True, return_value=platform):
        response = parser.parse(request)
        self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
        self.assertEmpty(response.error_message)
        # `execute_command` will be called once for each platform.
        adb.execute_command.assert_called_with(
            ['shell', 'am', 'stack', 'list', '|', 'grep', '-E', 'visible=true'],
            None)
        self.assertEqual(response.get_current_activity.full_activity,
                         'MyAwesomeActivity')

  def test_push_no_path(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        push=adb_pb2.AdbRequest.Push(content=b'Has content but no path'))
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  def test_push_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        push=adb_pb2.AdbRequest.Push(
            content=b'My text.', path='/sdcard/my_file.txt'))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once()
    args, kwargs = adb.execute_command.call_args
    self.assertLen(args, 1)
    cmd_args = args[0]
    self.assertLen(cmd_args, 3)
    self.assertEqual(cmd_args[0], 'push')
    self.assertEqual(cmd_args[2], '/sdcard/my_file.txt')
    self.assertIn('timeout', kwargs)
    self.assertIsNone(kwargs['timeout'])

  def test_pull_no_path(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(pull=adb_pb2.AdbRequest.Pull())
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  @mock.patch.object(builtins, 'open', autospec=True)
  def test_pull_successful(self, mock_open):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    mock_open.return_value.__enter__ = mock_open
    mock_open.return_value.read.return_value = b'S3cR3t. dO nOt TeLl ANYONE'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        pull=adb_pb2.AdbRequest.Pull(path='/sdcard/my_file.txt'))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.pull.content, b'S3cR3t. dO nOt TeLl ANYONE')
    adb.execute_command.assert_called_once()
    args, kwargs = adb.execute_command.call_args
    self.assertLen(args, 1)
    cmd_args = args[0]
    self.assertLen(cmd_args, 3)
    self.assertEqual(cmd_args[0], 'pull')
    self.assertEqual(cmd_args[1], '/sdcard/my_file.txt')
    self.assertIn('timeout', kwargs)
    self.assertIsNone(kwargs['timeout'])

  def test_input_text_no_text(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(input_text=adb_pb2.AdbRequest.InputText())
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  def test_input_text_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        input_text=adb_pb2.AdbRequest.InputText(
            text='The Greatest Text of All Time'))
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'input', 'text', 'The Greatest Text of All Time'], None)

  @parameterized.named_parameters(
      ('negative_x_and_negative_y',
       adb_pb2.AdbRequest(tap=adb_pb2.AdbRequest.Tap(x=-1, y=-1))),
      ('negative_x',
       adb_pb2.AdbRequest(tap=adb_pb2.AdbRequest.Tap(x=-1, y=123))),
      ('negative_y',
       adb_pb2.AdbRequest(tap=adb_pb2.AdbRequest.Tap(x=456, y=-1))),
  )
  def test_tap_failed(self, request: adb_pb2.AdbRequest):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  def test_tap_successful(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(tap=adb_pb2.AdbRequest.Tap(x=135, y=246))
    response = parser.parse(request)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'input', 'tap', '135', '246'], None)

  @parameterized.named_parameters(
      ('empty_request', adb_pb2.AdbRequest.SettingsRequest()),
      ('no_namespace',
       adb_pb2.AdbRequest.SettingsRequest(
           get=adb_pb2.AdbRequest.SettingsRequest.Get(key='my_key'))),
      ('get_no_key',
       adb_pb2.AdbRequest.SettingsRequest(
           name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
           get=adb_pb2.AdbRequest.SettingsRequest.Get())),
      ('put_no_key',
       adb_pb2.AdbRequest.SettingsRequest(
           name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
           put=adb_pb2.AdbRequest.SettingsRequest.Put())),
      ('put_no_value',
       adb_pb2.AdbRequest.SettingsRequest(
           name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
           put=adb_pb2.AdbRequest.SettingsRequest.Put(key='another_key'))),
      ('delete_no_key',
       adb_pb2.AdbRequest.SettingsRequest(
           name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
           delete_key=adb_pb2.AdbRequest.SettingsRequest.Delete())),
      ('reset_no_package_name_and_no_mode',
       adb_pb2.AdbRequest.SettingsRequest(
           name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
           reset=adb_pb2.AdbRequest.SettingsRequest.Reset())),
  )
  def test_settings_failures(self, request):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(settings=request)
    response = parser.parse(request)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  def test_settings_success_get(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'here it is!'
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest.SettingsRequest(
        name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
        get=adb_pb2.AdbRequest.SettingsRequest.Get(key='some_key'))
    request = adb_pb2.AdbRequest(settings=request)
    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.settings.output, b'here it is!')
    adb.execute_command.assert_called_once_with(
        ['shell', 'settings', 'get', 'system', 'some_key'], None)

  def test_settings_success_put(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'Done for ya!'
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest.SettingsRequest(
        name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SECURE,
        put=adb_pb2.AdbRequest.SettingsRequest.Put(key='key1', value='val2'))
    request = adb_pb2.AdbRequest(settings=request)
    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.settings.output, b'Done for ya!')
    adb.execute_command.assert_called_once_with(
        ['shell', 'settings', 'put', 'secure', 'key1', 'val2'], None)

  def test_settings_success_delete(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'Key deleted.'
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest.SettingsRequest(
        name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
        delete_key=adb_pb2.AdbRequest.SettingsRequest.Delete(key='useless_key'))
    request = adb_pb2.AdbRequest(settings=request)
    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.settings.output, b'Key deleted.')
    adb.execute_command.assert_called_once_with(
        ['shell', 'settings', 'delete', 'global', 'useless_key'], None)

  @parameterized.named_parameters(
      ('mode_untrusted_defaults',
       adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.UNTRUSTED_DEFAULTS, '',
       'untrusted_defaults'),
      ('mode_untrusted_clear',
       adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.UNTRUSTED_CLEAR, '',
       'untrusted_clear'),
      ('mode_trusted_defaults',
       adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.TRUSTED_DEFAULTS, '',
       'trusted_defaults'),
      # If `package_name` is given, it takes precedence over `mode`.
      ('mode_unknown_package_given',
       adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.UNKNOWN, 'great.package',
       'great.package'),
      ('mode_untrusted_defaults_package_given',
       adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.UNTRUSTED_DEFAULTS,
       'great.package', 'great.package'),
      ('mode_untrusted_clear_package_given',
       adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.UNTRUSTED_CLEAR,
       'great.package', 'great.package'),
      ('mode_trusted_defaults_package_given',
       adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.TRUSTED_DEFAULTS,
       'great.package', 'great.package'),
  )
  def test_settings_success_reset(self, mode, package_name, expected_arg):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'Pkg reset.'
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest.SettingsRequest(
        name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
        reset=adb_pb2.AdbRequest.SettingsRequest.Reset(
            package_name=package_name, mode=mode))
    request = adb_pb2.AdbRequest(settings=request)
    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.settings.output, b'Pkg reset.')
    adb.execute_command.assert_called_once_with(
        ['shell', 'settings', 'reset', 'global', expected_arg], None)

  def test_settings_success_list(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'volume_ring=5\nvolume_system=7'
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest.SettingsRequest(
        name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
        list=adb_pb2.AdbRequest.SettingsRequest.List())
    request = adb_pb2.AdbRequest(settings=request)
    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.settings.output,
                     b'volume_ring=5\nvolume_system=7')
    adb.execute_command.assert_called_once_with(
        ['shell', 'settings', 'list', 'system'], None)

  def test_generic_command(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    expected_output = b'generic_output'
    args = ['shell', 'am', 'broadcast', '-n', 'receiver', '-a', 'action']
    adb.execute_command.return_value = expected_output
    parser = adb_call_parser.AdbCallParser(adb)

    generic_request = adb_pb2.AdbRequest.GenericRequest(args=args)
    request = adb_pb2.AdbRequest(generic=generic_request)
    response = parser.parse(request)

    self.assertEqual(adb_pb2.AdbResponse.Status.OK, response.status)
    self.assertEmpty(response.error_message)
    self.assertEqual(response.generic.output, expected_output)
    adb.execute_command.assert_called_once_with(args, None)

  def test_generic_command_adb_error(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    args = ['shell', 'am', 'broadcast', '-n', 'receiver', '-a', 'action']
    adb.execute_command.side_effect = subprocess.CalledProcessError(
        cmd='cmd', output='adb_error', returncode=-1)
    parser = adb_call_parser.AdbCallParser(adb)

    generic_request = adb_pb2.AdbRequest.GenericRequest(args=args)
    request = adb_pb2.AdbRequest(generic=generic_request)
    response = parser.parse(request)

    self.assertEqual(adb_pb2.AdbResponse.Status.ADB_ERROR, response.status)
    self.assertEqual('adb_error', response.error_message)
    self.assertEmpty(response.generic.output)
    adb.execute_command.assert_called_once_with(args, None)

  def test_generic_command_timeout(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    args = ['shell', 'am', 'broadcast', '-n', 'receiver', '-a', 'action']
    adb.execute_command.side_effect = subprocess.TimeoutExpired(
        cmd='cmd', timeout=10)
    parser = adb_call_parser.AdbCallParser(adb)

    generic_request = adb_pb2.AdbRequest.GenericRequest(args=args)
    request = adb_pb2.AdbRequest(generic=generic_request)
    response = parser.parse(request)

    self.assertEqual(adb_pb2.AdbResponse.Status.TIMEOUT, response.status)
    self.assertEqual('Timeout', response.error_message)
    self.assertEmpty(response.generic.output)
    adb.execute_command.assert_called_once_with(args, None)

  @parameterized.named_parameters(
      ('features',
       adb_pb2.AdbRequest(
           package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
               list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                   features=adb_pb2.AdbRequest.PackageManagerRequest.List
                   .Features())))),
      ('libraries',
       adb_pb2.AdbRequest(
           package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
               list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                   libraries=adb_pb2.AdbRequest.PackageManagerRequest.List
                   .Libraries())))),
      ('packages',
       adb_pb2.AdbRequest(
           package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
               list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                   packages=adb_pb2.AdbRequest.PackageManagerRequest.List
                   .Packages())))),
  )
  def test_package_manager_list_bad_output(self, request):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b"""Something irrelevant."""
    parser = adb_call_parser.AdbCallParser(adb)
    response = parser.parse(request)
    response.package_manager.output = b"""Something irrelevant."""
    self.assertEmpty(response.package_manager.list.items)
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once()

  def test_package_manager_list_features(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    output = b"""
feature:android.hardware.audio.output
feature:android.hardware.bluetooth
feature:android.hardware.camera
feature:android.hardware.fingerprint
feature:android.software.autofill
feature:android.software.backup
feature:android.software.webview
"""
    adb.execute_command.return_value = output
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
            list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                features=adb_pb2.AdbRequest.PackageManagerRequest.List.Features(
                ))))
    response = parser.parse(request)
    self.assertEqual(response.package_manager.output, output)
    self.assertEqual(response.package_manager.list.items, [
        'android.hardware.audio.output',
        'android.hardware.bluetooth',
        'android.hardware.camera',
        'android.hardware.fingerprint',
        'android.software.autofill',
        'android.software.backup',
        'android.software.webview',
    ])
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'pm', 'list', 'features'], None)

  def test_package_manager_list_libraries(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    output = b"""
library:android.ext.shared
library:android.hidl.base-V1.0-java
library:android.hidl.manager-V1.0-java
library:android.net.ipsec.ike
library:android.test.base
library:android.test.mock
library:android.test.runner
library:androidx.window.sidecar
library:com.android.future.usb.accessory
library:com.android.location.provider
library:com.android.media.remotedisplay
library:com.android.mediadrm.signer
library:com.android.nfc_extras
library:com.google.android.gms
library:com.google.android.trichromelibrary
library:javax.obex
library:org.apache.http.legacy
"""
    adb.execute_command.return_value = output
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
            list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                libraries=adb_pb2.AdbRequest.PackageManagerRequest.List
                .Libraries())))
    response = parser.parse(request)
    self.assertEqual(response.package_manager.output, output)
    self.assertEqual(response.package_manager.list.items, [
        'android.ext.shared',
        'android.hidl.base-V1.0-java',
        'android.hidl.manager-V1.0-java',
        'android.net.ipsec.ike',
        'android.test.base',
        'android.test.mock',
        'android.test.runner',
        'androidx.window.sidecar',
        'com.android.future.usb.accessory',
        'com.android.location.provider',
        'com.android.media.remotedisplay',
        'com.android.mediadrm.signer',
        'com.android.nfc_extras',
        'com.google.android.gms',
        'com.google.android.trichromelibrary',
        'javax.obex',
        'org.apache.http.legacy',
    ])
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'pm', 'list', 'libraries'], None)

  def test_package_manager_list_packages(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    output = b"""
package:com.android.phone
package:com.awesome.company
package:com.another.great.thingie
"""
    adb.execute_command.return_value = output
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
            list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                packages=adb_pb2.AdbRequest.PackageManagerRequest.List.Packages(
                ))))
    response = parser.parse(request)
    self.assertEqual(response.package_manager.output, output)
    self.assertEqual(response.package_manager.list.items, [
        'com.android.phone',
        'com.awesome.company',
        'com.another.great.thingie',
    ])
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'pm', 'list', 'packages'], None)

  def test_package_manager_clear_no_package_name(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b"""Something irrelevant."""
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest(
        package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
            clear=adb_pb2.AdbRequest.PackageManagerRequest.Clear(
                package_name='')))
    response = parser.parse(request)

    self.assertEmpty(response.package_manager.output)
    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  def test_package_manager_clear_successful_no_user_id(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b"""Some successful message."""
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest(
        package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
            clear=adb_pb2.AdbRequest.PackageManagerRequest.Clear(
                package_name='my.package')))
    response = parser.parse(request)

    self.assertEqual(response.package_manager.output,
                     b"""Some successful message.""")
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'pm', 'clear', 'my.package'], None)

  def test_package_manager_clear_successful_with_user_id(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b"""Some successful message."""
    parser = adb_call_parser.AdbCallParser(adb)

    request = adb_pb2.AdbRequest(
        package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
            clear=adb_pb2.AdbRequest.PackageManagerRequest.Clear(
                package_name='my.package', user_id='mrawesome')))
    response = parser.parse(request)

    self.assertEqual(response.package_manager.output,
                     b"""Some successful message.""")
    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'pm', 'clear', '-f', 'mrawesome', 'my.package'], None)

  def test_dumpsys_empty_request(self):
    """An empty `DumpsysRequest` is a valid request."""
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(dumpsys=adb_pb2.AdbRequest.DumpsysRequest())

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(['shell', 'dumpsys'],
                                                timeout=None)

  @parameterized.named_parameters(
      ('negative_timeout_sec',
       adb_pb2.AdbRequest(
           dumpsys=adb_pb2.AdbRequest.DumpsysRequest(timeout_sec=-1))),
      ('negative_timeout_ms',
       adb_pb2.AdbRequest(
           dumpsys=adb_pb2.AdbRequest.DumpsysRequest(timeout_ms=-2))),
  )
  def test_dumpsys_negative_timeouts(self, request):
    """`DumpsysRequest.timeout_{sec, ms}` if passed, should be positive."""
    adb = mock.create_autospec(adb_controller.AdbController)
    parser = adb_call_parser.AdbCallParser(adb)

    response = parser.parse(request)

    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  @parameterized.named_parameters(
      ('both_timeouts_zero', 0, 0, ['shell', 'dumpsys']),
      ('sec_takes_precedence_zero', 123, 0, ['shell', 'dumpsys', '-t', '123']),
      ('sec_takes_precedence', 123, 456, ['shell', 'dumpsys', '-t', '123']),
      ('ms_if_no_sec', 0, 456, ['shell', 'dumpsys', '-T', '456']),
  )
  def test_dumpsys_timeout_successful(self, timeout_sec, timeout_ms, expected):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(
            timeout_sec=timeout_sec, timeout_ms=timeout_ms))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(expected, timeout=None)

  @parameterized.named_parameters(
      ('priority_undefined',
       adb_pb2.AdbRequest.DumpsysRequest.PriorityLevel.UNSET,
       ['shell', 'dumpsys']),
      ('priority_normal',
       adb_pb2.AdbRequest.DumpsysRequest.PriorityLevel.NORMAL,
       ['shell', 'dumpsys', '--priority', 'NORMAL']),
      ('priority_high', adb_pb2.AdbRequest.DumpsysRequest.PriorityLevel.HIGH,
       ['shell', 'dumpsys', '--priority', 'HIGH']),
      ('priority_critical',
       adb_pb2.AdbRequest.DumpsysRequest.PriorityLevel.CRITICAL,
       ['shell', 'dumpsys', '--priority', 'CRITICAL']),
  )
  def test_dumpsys_priority_timeout_successful(self, priority, expected):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(priority=priority))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(expected, timeout=None)

  @parameterized.named_parameters(
      (
          'window_service',
          adb_pb2.AdbRequest.DumpsysRequest(list_only=True, service='window'),
      ),
      (
          'arbitrary_args',
          adb_pb2.AdbRequest.DumpsysRequest(
              list_only=True, args=['myoption', 'anotheroption']
          ),
      ),
      (
          'skip_usb',
          adb_pb2.AdbRequest.DumpsysRequest(
              list_only=True, skip_services=['usb']
          ),
      ),
  )
  def test_dumpsys_list_only_cannot_be_combined(
      self, dumpsys_request: adb_pb2.AdbRequest.DumpsysRequest
  ):
    """When `list_only==True`, the request cannot contain a few fields."""

    # Arrange.
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(dumpsys=dumpsys_request)

    # Act.
    response = parser.parse(request)

    # Assert.
    self.assertEqual(
        response.status, adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
    )
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  def test_dumpsys_list_only_success(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(list_only=True))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(['shell', 'dumpsys', '-l'],
                                                timeout=None)

  def test_dumpsys_skip_services_cannot_combine_with_service(self):
    """When using `DumpsysRequest.skip_service`, it cannot contain `.service`."""
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(
            service='wifi', skip_services=['window', 'usb']))

    response = parser.parse(request)

    self.assertEqual(response.status,
                     adb_pb2.AdbResponse.Status.FAILED_PRECONDITION)
    self.assertNotEmpty(response.error_message)
    adb.execute_command.assert_not_called()

  def test_dumpsys_skip_services(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(
            skip_services=['window', 'usb']))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'dumpsys', '--skip', 'window,usb'], timeout=None)

  def test_dumpsys_single_service(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(service='window'))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(['shell', 'dumpsys', 'window'],
                                                timeout=None)

  def test_dumpsys_single_service_with_args(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'whatever'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(
            service='window', args=['arg1', 'arg2']))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'dumpsys', 'window', 'arg1', 'arg2'], timeout=None)

  def test_dumpsys_single_service_with_proto(self):
    adb = mock.create_autospec(adb_controller.AdbController)
    adb.execute_command.return_value = b'some binary output'
    parser = adb_call_parser.AdbCallParser(adb)
    request = adb_pb2.AdbRequest(
        dumpsys=adb_pb2.AdbRequest.DumpsysRequest(service='window', proto=True))

    response = parser.parse(request)

    self.assertEqual(response.status, adb_pb2.AdbResponse.Status.OK)
    self.assertEmpty(response.error_message)
    adb.execute_command.assert_called_once_with(
        ['shell', 'dumpsys', 'window', '--proto'], timeout=None)


if __name__ == '__main__':
  absltest.main()
