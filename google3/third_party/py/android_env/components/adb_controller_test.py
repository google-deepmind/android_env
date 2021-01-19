"""Unit tests for AdbController."""

import os
import time

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import adb_controller
from android_env.components import errors
from android_env.proto import task_pb2
import mock
import numpy as np


class AdbControllerTest(parameterized.TestCase):

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_deletes_problem_env_vars(self, mock_execute_command, mock_sleep):
    os.environ['ANDROID_HOME'] = '/usr/local/Android/Sdk'
    os.environ['ANDROID_ADB_SERVER_PORT'] = '1337'
    adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    self.assertNotIn('ANDROID_HOME', os.environ)
    self.assertNotIn('ANDROID_ADB_SERVER_PORT', os.environ)
    mock_execute_command.assert_called()  # at __init__.
    mock_sleep.assert_called_once()  # We don't care about the arg.

  @mock.patch.object(
      adb_controller.AdbController, '_wait_for_device', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_set_touch_indicators(self, mock_execute_command, mock_sleep,
                                mock_wait_for_device):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_execute_command.assert_called()  # at __init__.
    mock_sleep.assert_called_once()  # We don't care about the arg.
    adb_control.set_touch_indicators(show_touches=True, pointer_location=False)
    mock_wait_for_device.assert_called_once()
    mock_execute_command.assert_called_with(
        adb_control,
        ['shell', 'settings', 'put', 'system', 'pointer_location', '0'])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_force_stop(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_execute_command.assert_called()  # at __init__.
    mock_sleep.assert_called_once()  # We don't care about the arg.
    adb_control.force_stop('com.amazing.package')
    mock_execute_command.assert_called_with(
        adb_control, ['shell', 'am', 'force-stop', 'com.amazing.package'])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_clear_cache(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_execute_command.assert_called()  # at __init__.
    mock_sleep.assert_called_once()  # We don't care about the arg.
    adb_control.clear_cache('com.amazing.package')
    mock_execute_command.assert_called_with(
        adb_control, ['shell', 'pm', 'clear', 'com.amazing.package'])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_grant_permissions(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_execute_command.assert_called()  # at __init__.
    mock_sleep.assert_called_once()  # We don't care about the arg.
    adb_control.grant_permissions('com.amazing.package',
                                  ['hey.READ', 'ho.WRITE'])
    mock_execute_command.assert_has_calls([
        mock.call(adb_control,
                  ['shell', 'pm', 'grant', 'com.amazing.package', 'hey.READ']),
        mock.call(adb_control,
                  ['shell', 'pm', 'grant', 'com.amazing.package', 'ho.WRITE']),
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_installed_packages(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.
    mock_execute_command.return_value = b"""
package:com.google.android.apps.wallpaper
package:com.android.phone
package:com.android.shell
package:com.android.wallpaperbackup
"""
    packages = adb_control._installed_packages()
    self.assertEqual(packages, [
        'com.google.android.apps.wallpaper',
        'com.android.phone',
        'com.android.shell',
        'com.android.wallpaperbackup',
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_start_activity(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.
    # mock_execute_command.
    adb_control.start_activity('hello.world/hello.world.MainActivity', [])
    adb_control.start_activity(
        full_activity='hello.world/hello.world.MainActivity',
        extra_args=['Planet 1', 'Planet 2'])
    mock_execute_command.assert_has_calls([
        mock.call(adb_control, [
            'shell', 'am', 'start', '-S', '-n',
            'hello.world/hello.world.MainActivity'
        ], 10),
        mock.call(adb_control, [
            'shell', 'am', 'start', '-S', '-n',
            'hello.world/hello.world.MainActivity', 'Planet 1', 'Planet 2'
        ], 10)
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_start_intent(self, mock_execute_command, unused_mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    adb_control.start_intent(
        action='action',
        data_uri='data',
        package_name='my.package',
        timeout=3.0)

    mock_execute_command.assert_has_calls([
        mock.call(adb_control, ['devices']),  # from the __init__
        mock.call(adb_control, [
            'shell', 'am', 'start', '-a', 'action', '-d', 'data', 'my.package'
        ], 3.0)
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_broadcast(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.
    # mock_execute_command.
    adb_control.broadcast('hello.world/hello.world.BroadcastReceiver',
                          'android.intent.action.TEST', [])
    adb_control.broadcast(
        receiver='hello.world/hello.world.BroadcastReceiver',
        action='android.intent.action.TEST',
        extra_args=['--es', 'KEY', 'VALUE'])
    mock_execute_command.assert_has_calls([
        mock.call(adb_control, [
            'shell', 'am', 'broadcast', '-n',
            'hello.world/hello.world.BroadcastReceiver', '-a',
            'android.intent.action.TEST'
        ]),
        mock.call(adb_control, [
            'shell', 'am', 'broadcast', '-n',
            'hello.world/hello.world.BroadcastReceiver', '-a',
            'android.intent.action.TEST', '--es', 'KEY', 'VALUE'
        ])
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_setprop(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()
    adb_control.setprop('myprop', 'true')
    adb_control.setprop('myotherprop', 'false')
    mock_execute_command.assert_has_calls([
        mock.call(adb_control, ['shell', 'setprop', 'myprop', 'true']),
        mock.call(adb_control, ['shell', 'setprop', 'myotherprop', 'false']),
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_rotate_device(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.
    adb_control.rotate_device(task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_90)
    adb_control.rotate_device(task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_0)
    adb_control.rotate_device(task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_270)
    adb_control.rotate_device(task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_180)
    mock_execute_command.assert_has_calls([
        mock.call(
            adb_control,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '1']),
        mock.call(
            adb_control,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '0']),
        mock.call(
            adb_control,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '3']),
        mock.call(
            adb_control,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '2'])
    ])

  @mock.patch.object(
      adb_controller.AdbController, '_wait_for_device', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_get_screen_dimensions_failed_wait(self, unused_mock_execute_command,
                                             mock_sleep, mock_wait_for_device):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_wait_for_device.side_effect = errors.AdbControllerDeviceTimeoutError(
        'Time is up.')
    self.assertRaises(errors.AdbControllerDeviceTimeoutError,
                      adb_control.get_screen_dimensions)
    mock_wait_for_device.assert_called_once()

  @mock.patch.object(
      adb_controller.AdbController, '_wait_for_device', autospec=True)
  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_get_screen_dimensions_success(self, mock_execute_command, mock_sleep,
                                         mock_wait_for_device):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b'Physical size: 1280x800'
    screen_dimensions = adb_control.get_screen_dimensions()
    mock_wait_for_device.assert_called()
    mock_execute_command.assert_called_with(adb_control,
                                            ['shell', 'wm', 'size'])
    self.assertEqual(screen_dimensions, (800, 1280))

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_activity_dumpsys(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    package_name = 'com.world.hello'
    mock_execute_command.return_value = b'My awesome dumpsys output!!!'
    activity_dumpsys = adb_control.get_activity_dumpsys(package_name)
    mock_execute_command.assert_called_with(
        adb_control,
        ['shell', 'dumpsys', 'activity', package_name, package_name])
    # Compare activity_dumpsys to what we want. Notice that we expect a UTF-8
    # string, NOT bytes.
    self.assertEqual(activity_dumpsys, 'My awesome dumpsys output!!!')

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_input_tap(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b''
    adb_control.input_tap(123, 456)
    mock_execute_command.assert_called_with(
        adb_control, ['shell', 'input', 'tap', '123', '456'])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_input_text(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b''
    adb_control.input_text('my_text')
    mock_execute_command.assert_called_with(
        adb_control, ['shell', 'input', 'text', 'my_text'])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController,
      '_get_image_array_from_bytes',
      autospec=True)
  def test_get_screencap(self, mock_image, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.
    fake_screencap = b'my_screencap'
    mock_execute_command.return_value = fake_screencap
    fake_array = np.ones((1, 2, 3))
    mock_image.return_value = fake_array

    img = adb_control.get_screencap()
    mock_image.assert_called_once_with(adb_control, fake_screencap)
    mock_execute_command.assert_called_with(adb_control,
                                            ['shell', 'screencap', '-p'])
    np.testing.assert_equal(fake_array, img)

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_input_key(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b''
    adb_control.input_key('KEYCODE_HOME')
    adb_control.input_key('KEYCODE_BACK')
    adb_control.input_key('KEYCODE_ENTER')
    mock_execute_command.assert_has_calls([
        mock.call(adb_control, ['shell', 'input', 'keyevent', 'KEYCODE_HOME']),
        mock.call(adb_control, ['shell', 'input', 'keyevent', 'KEYCODE_BACK']),
        mock.call(adb_control, ['shell', 'input', 'keyevent', 'KEYCODE_ENTER']),
    ])

    # A key code outside of the accepted codes should raise an exception.
    self.assertRaises(AssertionError, adb_control.input_key, 'KEYCODE_0')

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_install_apk(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b''
    # Passing an invalid path should raise an exception.
    self.assertRaises(AssertionError, adb_control.install_apk, '')

    local_apk_path = os.path.join(absltest.get_default_test_tmpdir(),
                                  'my_app.apk')
    with open(local_apk_path, 'wb') as f:
      f.write(b'blah. whatever')
    adb_control.install_apk(local_apk_path, timeout=2.0)
    mock_execute_command.assert_has_calls([
        mock.call(
            adb_control, ['install', '-r', '-t', '-g', local_apk_path],
            timeout=2.0),
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_start_accessibility_service(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b''
    adb_control.start_accessibility_service('my.service')
    mock_execute_command.assert_has_calls([
        mock.call(adb_control, [
            'shell', 'settings', 'put', 'secure',
            'enabled_accessibility_services', 'my.service'
        ])
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_fetch_current_task_id', autospec=True)
  def test_start_screen_pinning_task_not_found(self, mock_fetch_current_task_id,
                                               mock_execute_command,
                                               mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.reset_mock()
    mock_execute_command.return_value = b''
    mock_fetch_current_task_id.return_value = -1
    adb_control.start_screen_pinning('my.app.CoolActivity')
    mock_execute_command.assert_not_called()

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_fetch_current_task_id', autospec=True)
  def test_start_screen_pinning(self, mock_fetch_current_task_id,
                                mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b''
    mock_fetch_current_task_id.return_value = 123
    adb_control.start_screen_pinning('my.app.CoolActivity')
    mock_execute_command.assert_has_calls(
        [mock.call(adb_control, ['shell', 'am', 'task', 'lock', '123'])])

  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_fetch_current_task_id(self, mock_execute_command):
    full_activity_name = (
        'com.google.example.games.nostalgicracer/'
        'com.google.example.games.nostalgicracer.MainActivity')
    bad_task = (
        '  taskId=8: '
        'com.google.android.apps.maps/com.google.android.maps.MapsActivity '
        'bounds=[0,0][480,320] userId=0 visible=true '
        'topActivity=ComponentInfo{%s}' % full_activity_name)
    good_task_not_visible = (
        'taskId=49: %s bounds=[0,0][320,480] userId=0 visible=false more_stuff'
        % full_activity_name)
    good_task = (
        'taskId=50: %s bounds=[0,0][320,480] userId=0 visible=true more_stuff' %
        full_activity_name)
    stack_list = '\n'.join([bad_task, good_task_not_visible,
                            good_task]).encode('utf-8')
    mock_execute_command.return_value = stack_list

    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')

    self.assertEqual(50, adb_control._fetch_current_task_id(full_activity_name))

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_check_install_not_installed(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b"""
package:foo
package:bar
package:baz
"""
    self.assertFalse(adb_control.is_package_installed('faz'))

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_check_install_installed(self, mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    mock_execute_command.return_value = b"""
package:foo
package:bar
package:baz
"""
    self.assertTrue(adb_control.is_package_installed('baz'))

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_connect(self, mock_execute_command, mock_sleep):
    mock_execute_command.return_value = b'connected to myhost:12345'
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>',
        tcp_host='myhost',
        tcp_port=12345)
    mock_sleep.assert_called_once()
    mock_execute_command.assert_has_calls(
        [mock.call(adb_control, ['connect', 'myhost:12345'])])
    self.assertTrue(adb_control._connected)

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_no_connection(self, mock_execute_command, mock_sleep):
    mock_execute_command.return_value = b'connected to myhost:12345'
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()
    mock_execute_command.assert_called_once_with(adb_control, ['devices'])
    self.assertFalse(adb_control._connected)

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_connect_already_connected(self, mock_execute_command, mock_sleep):
    mock_execute_command.return_value = b'already connected to myhost:12345'
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>',
        tcp_host='myhost',
        tcp_port=12345)
    mock_sleep.assert_called_once()

    mock_execute_command.assert_has_calls(
        [mock.call(adb_control, ['connect', 'myhost:12345'])])
    self.assertTrue(adb_control._connected)

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_connect_retry(self, mock_execute_command, unused_mock_sleep):
    mock_execute_command.side_effect = [
        b'devices.',  # The first command is the 'devices' call in __init__.
        b'connection refused',
        b'connected to myhost:12345'
    ]
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>',
        tcp_host='myhost',
        tcp_port=12345,
        connect_max_tries=2)
    mock_execute_command.assert_has_calls([
        mock.call(adb_control, ['devices']),
        mock.call(adb_control, ['connect', 'myhost:12345']),
        mock.call(adb_control, ['connect', 'myhost:12345']),
    ])
    self.assertTrue(adb_control._connected)

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_connect_fail(self, mock_execute_command, unused_mock_sleep):
    mock_execute_command.side_effect = [
        b'devices.',  # The first command is the 'devices' call in __init__.
        b'connection refused',
        b'Nope!',
        b'connected to myhost:12345'  # A third try would have connected.
    ]
    self.assertRaises(
        errors.AdbControllerConnectionError,
        adb_controller.AdbController,
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>',
        tcp_host='myhost',
        tcp_port=12345,
        connect_max_tries=2)

  @parameterized.parameters(
      (True, True, 'null*'),
      (True, False, 'immersive.status=*'),
      (False, True, 'immersive.navigation=*'),
      (False, False, 'immersive.full=*'),
      (None, None, 'immersive.full=*'),  # Defaults to hiding both.
  )
  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      adb_controller.AdbController, '_execute_command', autospec=True)
  def test_set_bar_visibility(self, navigation, status, expected,
                              mock_execute_command, mock_sleep):
    adb_control = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        server_port=9999,
        shell_prompt='l33t>')
    mock_sleep.assert_called_once()  # We don't care about the arg.

    expected_output = b'Message.'
    mock_execute_command.return_value = expected_output

    self.assertEqual(
        expected_output,
        adb_control.set_bar_visibility(navigation=navigation, status=status))
    mock_execute_command.assert_has_calls([
        mock.call(adb_control, ['devices']),  # From the __init__.
        mock.call(
            adb_control,
            ['shell', 'settings', 'put', 'global', 'policy_control', expected]),
    ])


if __name__ == '__main__':
  absltest.main()
