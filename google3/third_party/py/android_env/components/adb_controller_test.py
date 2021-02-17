"""Unit tests for AdbController."""

import os
import subprocess
import time

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import adb_controller
from android_env.components import errors
from android_env.proto import task_pb2
import mock

# Timeout to be used by default in tests below. Set to a small value to avoid
# hanging on a failed test.
_TIMEOUT = 2


class AdbControllerTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self._mock_execute_command = self.enter_context(
        mock.patch.object(
            adb_controller.AdbController, '_execute_command', autospec=True))
    self._adb_controller = adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        adb_server_port=9999,
        shell_prompt='l33t>')

  @mock.patch.object(
      adb_controller.AdbController, '_wait_for_device', autospec=True)
  def test_set_touch_indicators(self, mock_wait_for_device):
    self._adb_controller.set_touch_indicators(
        show_touches=True, pointer_location=False, timeout=_TIMEOUT)
    mock_wait_for_device.assert_called_once()
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller,
                  ['shell', 'settings', 'put', 'system', 'show_touches', '1'],
                  _TIMEOUT),
        mock.call(
            self._adb_controller,
            ['shell', 'settings', 'put', 'system', 'pointer_location', '0'],
            _TIMEOUT)
    ])

  def test_force_stop(self):
    self._adb_controller.force_stop('com.amazing.package', timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(
        self._adb_controller,
        ['shell', 'am', 'force-stop', 'com.amazing.package'], _TIMEOUT)

  def test_clear_cache(self):
    self._adb_controller.clear_cache('com.amazing.package', timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_with(
        self._adb_controller, ['shell', 'pm', 'clear', 'com.amazing.package'],
        _TIMEOUT)

  def test_grant_permissions(self):
    self._adb_controller.grant_permissions(
        'com.amazing.package', ['hey.READ', 'ho.WRITE'], timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller,
                  ['shell', 'pm', 'grant', 'com.amazing.package', 'hey.READ'],
                  _TIMEOUT),
        mock.call(self._adb_controller,
                  ['shell', 'pm', 'grant', 'com.amazing.package', 'ho.WRITE'],
                  _TIMEOUT),
    ])

  def test_start_activity(self):
    self._adb_controller.start_activity(
        'hello.world/hello.world.MainActivity', [], timeout=_TIMEOUT)
    self._adb_controller.start_activity(
        full_activity='hello.world/hello.world.MainActivity',
        extra_args=['Planet 1', 'Planet 2'],
        timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller, [
            'shell', 'am', 'start', '-S', '-n',
            'hello.world/hello.world.MainActivity'
        ], _TIMEOUT),
        mock.call(self._adb_controller, [
            'shell', 'am', 'start', '-S', '-n',
            'hello.world/hello.world.MainActivity', 'Planet 1', 'Planet 2'
        ], _TIMEOUT)
    ])

  def test_start_intent(self):
    self._adb_controller.start_intent(
        action='action',
        data_uri='data',
        package_name='my.package',
        timeout=_TIMEOUT)

    self._mock_execute_command.assert_called_once_with(
        self._adb_controller,
        ['shell', 'am', 'start', '-a', 'action', '-d', 'data', 'my.package'],
        _TIMEOUT)

  def test_broadcast(self):
    self._adb_controller.broadcast(
        'hello.world/hello.world.BroadcastReceiver',
        'android.intent.action.TEST', [],
        timeout=_TIMEOUT)
    self._adb_controller.broadcast(
        receiver='hello.world/hello.world.BroadcastReceiver',
        action='android.intent.action.TEST',
        extra_args=['--es', 'KEY', 'VALUE'],
        timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller, [
            'shell', 'am', 'broadcast', '-n',
            'hello.world/hello.world.BroadcastReceiver', '-a',
            'android.intent.action.TEST'
        ], _TIMEOUT),
        mock.call(self._adb_controller, [
            'shell', 'am', 'broadcast', '-n',
            'hello.world/hello.world.BroadcastReceiver', '-a',
            'android.intent.action.TEST', '--es', 'KEY', 'VALUE'
        ], _TIMEOUT)
    ])

  def test_setprop(self):
    self._adb_controller.setprop('myprop', 'true', timeout=_TIMEOUT)
    self._adb_controller.setprop('myotherprop', 'false', timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller, ['shell', 'setprop', 'myprop', 'true'],
                  _TIMEOUT),
        mock.call(self._adb_controller,
                  ['shell', 'setprop', 'myotherprop', 'false'], _TIMEOUT),
    ])

  def test_rotate_device(self):
    self._adb_controller.rotate_device(
        task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_90, timeout=_TIMEOUT)
    self._adb_controller.rotate_device(
        task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_0, timeout=_TIMEOUT)
    self._adb_controller.rotate_device(
        task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_270, timeout=_TIMEOUT)
    self._adb_controller.rotate_device(
        task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_180, timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(
            self._adb_controller,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '1'],
            timeout=_TIMEOUT),
        mock.call(
            self._adb_controller,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '0'],
            timeout=_TIMEOUT),
        mock.call(
            self._adb_controller,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '3'],
            timeout=_TIMEOUT),
        mock.call(
            self._adb_controller,
            args=['shell', 'settings', 'put', 'system', 'user_rotation', '2'],
            timeout=_TIMEOUT)
    ])

  @mock.patch.object(
      adb_controller.AdbController, '_wait_for_device', autospec=True)
  def test_get_screen_dimensions_failed_wait(self, mock_wait_for_device):

    mock_wait_for_device.side_effect = errors.AdbControllerDeviceTimeoutError(
        'Time is up.')
    self.assertRaises(errors.AdbControllerDeviceTimeoutError,
                      self._adb_controller.get_screen_dimensions)
    mock_wait_for_device.assert_called_once()

  @mock.patch.object(
      adb_controller.AdbController, '_wait_for_device', autospec=True)
  def test_get_screen_dimensions_success(self, mock_wait_for_device):
    self._mock_execute_command.return_value = b'Physical size: 1280x800'
    screen_dimensions = self._adb_controller.get_screen_dimensions(
        timeout=_TIMEOUT)
    mock_wait_for_device.assert_called()
    self._mock_execute_command.assert_called_with(self._adb_controller,
                                                  ['shell', 'wm', 'size'],
                                                  _TIMEOUT)
    self.assertEqual(screen_dimensions, (800, 1280))

  def test_activity_dumpsys(self):
    package_name = 'com.world.hello'
    self._mock_execute_command.return_value = b'My awesome dumpsys output!!!'
    activity_dumpsys = self._adb_controller.get_activity_dumpsys(
        package_name, timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(
        self._adb_controller,
        ['shell', 'dumpsys', 'activity', package_name, package_name], _TIMEOUT)
    # Compare activity_dumpsys to what we want. Notice that we expect a UTF-8
    # string, NOT bytes.
    self.assertEqual(activity_dumpsys, 'My awesome dumpsys output!!!')

  def test_input_tap(self):
    self._mock_execute_command.return_value = b''
    self._adb_controller.input_tap(123, 456, timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(
        self._adb_controller, ['shell', 'input', 'tap', '123', '456'], _TIMEOUT)

  def test_input_text(self):
    self._mock_execute_command.return_value = b''
    self._adb_controller.input_text('my_text', timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(
        self._adb_controller, ['shell', 'input', 'text', 'my_text'], _TIMEOUT)

  def test_input_key(self):
    self._mock_execute_command.return_value = b''
    self._adb_controller.input_key('KEYCODE_HOME', timeout=_TIMEOUT)
    self._adb_controller.input_key('KEYCODE_BACK', timeout=_TIMEOUT)
    self._adb_controller.input_key('KEYCODE_ENTER', timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller,
                  ['shell', 'input', 'keyevent', 'KEYCODE_HOME'], _TIMEOUT),
        mock.call(self._adb_controller,
                  ['shell', 'input', 'keyevent', 'KEYCODE_BACK'], _TIMEOUT),
        mock.call(self._adb_controller,
                  ['shell', 'input', 'keyevent', 'KEYCODE_ENTER'], _TIMEOUT),
    ])

    # A key code outside of the accepted codes should raise an exception.
    self.assertRaises(AssertionError, self._adb_controller.input_key,
                      'KEYCODE_0')

  def test_install_apk(self):
    self._mock_execute_command.return_value = b''
    # Passing an invalid path should raise an exception.
    self.assertRaises(AssertionError, self._adb_controller.install_apk, '')

    local_apk_path = os.path.join(absltest.get_default_test_tmpdir(),
                                  'my_app.apk')
    with open(local_apk_path, 'wb') as f:
      f.write(b'blah. whatever')
    self._adb_controller.install_apk(local_apk_path, timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller,
                  ['install', '-r', '-t', '-g', local_apk_path], _TIMEOUT),
    ])

  def test_start_accessibility_service(self):
    self._mock_execute_command.return_value = b''
    self._adb_controller.start_accessibility_service(
        'my.service', timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller, [
            'shell', 'settings', 'put', 'secure',
            'enabled_accessibility_services', 'my.service'
        ], _TIMEOUT)
    ])

  @mock.patch.object(
      adb_controller.AdbController, '_fetch_current_task_id', autospec=True)
  def test_start_screen_pinning_task_not_found(self,
                                               mock_fetch_current_task_id):
    self._mock_execute_command.return_value = b''
    mock_fetch_current_task_id.return_value = -1
    self._adb_controller.start_screen_pinning(
        'my.app.CoolActivity', timeout=_TIMEOUT)
    self._mock_execute_command.assert_not_called()

  @mock.patch.object(
      adb_controller.AdbController, '_fetch_current_task_id', autospec=True)
  def test_start_screen_pinning(self, mock_fetch_current_task_id):
    self._mock_execute_command.return_value = b''
    mock_fetch_current_task_id.return_value = 123
    self._adb_controller.start_screen_pinning(
        'my.app.CoolActivity', timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller, ['shell', 'am', 'task', 'lock', '123'],
                  _TIMEOUT)
    ])

  def test_fetch_current_task_id(self):
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
    self._mock_execute_command.return_value = stack_list

    self.assertEqual(
        50,
        self._adb_controller._fetch_current_task_id(
            full_activity_name, timeout=_TIMEOUT))

  def test_check_install_not_installed(self):
    self._mock_execute_command.return_value = b"""
package:foo
package:bar
package:baz
"""
    self.assertFalse(
        self._adb_controller.is_package_installed('faz', timeout=_TIMEOUT))

  def test_check_install_installed(self):
    self._mock_execute_command.return_value = b"""
package:foo
package:bar
package:baz
"""
    self.assertTrue(
        self._adb_controller.is_package_installed('baz', timeout=_TIMEOUT))

  def test_tcp_connect(self):
    connect_msg = b'connected to myhost:12345'
    self._mock_execute_command.return_value = connect_msg
    cmd_out = self._adb_controller.tcp_connect('myhost:12345', timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller, ['connect', 'myhost:12345'], _TIMEOUT)
    ])
    self.assertEqual(connect_msg, cmd_out)

  def test_connect_already_connected(self):
    connect_msg = b'already connected to myhost:12345'
    self._mock_execute_command.return_value = connect_msg
    cmd_out = self._adb_controller.tcp_connect('myhost:12345', timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(
        self._adb_controller, ['connect', 'myhost:12345'], _TIMEOUT)
    self.assertEqual(connect_msg, cmd_out)

  def test_connect_retry(self):
    connect_msg = b'connected to myhost:12345'
    self._mock_execute_command.side_effect = [
        b'connection refused', connect_msg
    ]
    cmd_out = self._adb_controller.tcp_connect('myhost:12345', timeout=_TIMEOUT)
    self._mock_execute_command.assert_has_calls([
        mock.call(self._adb_controller, ['connect', 'myhost:12345'], _TIMEOUT),
        mock.call(self._adb_controller, ['connect', 'myhost:12345'], _TIMEOUT),
    ])
    self.assertEqual(2, self._mock_execute_command.call_count)
    self.assertEqual(connect_msg, cmd_out)

  def test_connect_fail(self):
    self._mock_execute_command.side_effect = [
        b'connection refused',
        b'Nope!',
        b'connected to myhost:12345'  # A third try would have connected.
    ]
    self.assertRaises(
        errors.AdbControllerConnectionError,
        self._adb_controller.tcp_connect,
        'myhost:12345',
        connect_max_tries=2)

  def test_disconnect(self):
    disconnect_msg = b'disconnecting...'
    self._mock_execute_command.return_value = disconnect_msg
    cmd_out = self._adb_controller.tcp_disconnect(timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(self._adb_controller,
                                                       ['disconnect'], _TIMEOUT)
    self.assertEqual(disconnect_msg, cmd_out)

  def test_disconnect_fail(self):
    # If the disconnect command fails, we just ignore it.
    self._mock_execute_command.side_effect = subprocess.CalledProcessError(
        1, '', None)
    cmd_out = self._adb_controller.tcp_disconnect(timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(self._adb_controller,
                                                       ['disconnect'], _TIMEOUT)
    self.assertIsNone(cmd_out)

  @parameterized.parameters(
      (True, True, 'null*'),
      (True, False, 'immersive.status=*'),
      (False, True, 'immersive.navigation=*'),
      (False, False, 'immersive.full=*'),
      (None, None, 'immersive.full=*'),  # Defaults to hiding both.
  )
  def test_set_bar_visibility(self, navigation, status, expected):
    expected_output = b'Message.'
    self._mock_execute_command.return_value = expected_output

    self.assertEqual(
        expected_output,
        self._adb_controller.set_bar_visibility(
            navigation=navigation, status=status, timeout=_TIMEOUT))
    self._mock_execute_command.assert_has_calls([
        mock.call(
            self._adb_controller,
            ['shell', 'settings', 'put', 'global', 'policy_control', expected],
            _TIMEOUT),
    ])

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_init_server(self, mock_sleep):
    self._adb_controller.init_server(timeout=_TIMEOUT)
    self._mock_execute_command.assert_called_once_with(self._adb_controller,
                                                       ['devices'], _TIMEOUT)
    mock_sleep.assert_called_once()


class AdbControllerInitTest(absltest.TestCase):

  def test_deletes_problem_env_vars(self):
    os.environ['ANDROID_HOME'] = '/usr/local/Android/Sdk'
    os.environ['ANDROID_ADB_SERVER_PORT'] = '1337'
    adb_controller.AdbController(
        adb_path='my_adb',
        device_name='awesome_device',
        adb_server_port=9999,
        shell_prompt='l33t>',
        default_timeout=_TIMEOUT)
    self.assertNotIn('ANDROID_HOME', os.environ)
    self.assertNotIn('ANDROID_ADB_SERVER_PORT', os.environ)


if __name__ == '__main__':
  absltest.main()
