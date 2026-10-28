# coding=utf-8
# Copyright 2026 DeepMind Technologies Limited.
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

"""Tests for playground entrypoint and thread orchestration."""

import runpy
import sys
from unittest import mock

from absl.testing import absltest
from absl.testing import flagsaver
from android_env.components import android_device
from android_env.components import config_classes
from android_env.playground import playground
from android_env.playground import state as state_lib
import numpy as np


class PlaygroundTest(absltest.TestCase):

  @mock.patch.object(playground.device_runner, 'run_device', autospec=True)
  @mock.patch.object(playground.device_runner, 'setup_device', autospec=True)
  def test_run_device_thread_success_closes_device(
      self, mock_setup_device, mock_run_device
  ):
    state = state_lib.PlaygroundState()
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    pixels = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_setup_device.return_value = (mock_dev, 0, pixels)

    playground._run_device_thread(state, 'dummy_config')

    mock_setup_device.assert_called_once_with(state, 'dummy_config')
    mock_run_device.assert_called_once_with(mock_dev, 0, pixels, state)
    mock_dev.close.assert_called_once()

  @mock.patch.object(playground.device_runner, 'run_device', autospec=True)
  @mock.patch.object(playground.device_runner, 'setup_device', autospec=True)
  def test_run_device_thread_setup_error_returns_early(
      self, mock_setup_device, mock_run_device
  ):
    state = state_lib.PlaygroundState()
    mock_setup_device.side_effect = playground.device_runner.DeviceSetupError(
        'bad orientation'
    )

    playground._run_device_thread(state, 'dummy_config')

    mock_run_device.assert_not_called()

  @mock.patch.object(playground.websocket, 'try_send_status', autospec=True)
  @mock.patch.object(playground.device_runner, 'run_device', autospec=True)
  @mock.patch.object(playground.device_runner, 'setup_device', autospec=True)
  def test_run_device_thread_run_error_sends_status_and_closes_device(
      self, mock_setup_device, mock_run_device, mock_send_status
  ):
    state = state_lib.PlaygroundState()
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    pixels = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_setup_device.return_value = (mock_dev, 0, pixels)
    mock_run_device.side_effect = RuntimeError('step failed')

    playground._run_device_thread(state, 'dummy_config')

    mock_send_status.assert_called_once_with(state, 'ERROR: step failed')
    mock_dev.close.assert_called_once()

  @mock.patch.object(playground.device_runner, 'run_device', autospec=True)
  @mock.patch.object(playground.device_runner, 'setup_device', autospec=True)
  def test_run_device_thread_server_not_running_closes_device_without_running(
      self, mock_setup_device, mock_run_device
  ):
    state = state_lib.PlaygroundState()
    state.running = False
    mock_dev = mock.create_autospec(android_device.AndroidDevice, instance=True)
    pixels = np.zeros((10, 10, 3), dtype=np.uint8)
    mock_setup_device.return_value = (mock_dev, 0, pixels)

    playground._run_device_thread(state, 'dummy_config')

    mock_setup_device.assert_called_once_with(state, 'dummy_config')
    mock_run_device.assert_not_called()
    mock_dev.close.assert_called_once()

  @mock.patch.object(playground.server, 'PlaygroundServer', autospec=True)
  def test_serve_http_handles_keyboard_interrupt(self, mock_server_cls):
    state = state_lib.PlaygroundState()
    mock_httpd = mock_server_cls.return_value.__enter__.return_value
    mock_httpd.serve_forever.side_effect = KeyboardInterrupt()

    playground._serve_http(state, '/fake/static', 8080)

    self.assertTrue(mock_server_cls.allow_reuse_address)
    self.assertTrue(mock_server_cls.daemon_threads)
    mock_server_cls.assert_called_once_with(
        ('', 8080),
        playground.server.StreamHandler,
        state,
        '/fake/static',
    )
    self.assertFalse(state.running)
    mock_httpd.serve_forever.assert_called_once()

  @mock.patch.object(playground, '_serve_http', autospec=True)
  @mock.patch.object(
      playground.server,
      'get_default_static_dir',
      autospec=True,
      return_value='/fake/static',
  )
  @mock.patch.object(playground.threading, 'Thread', autospec=True)
  def test_main_starts_thread_and_serves_http(
      self, mock_thread_cls, unused_mock_static_dir, mock_serve_http
  ):
    mock_serve_http.side_effect = OSError('bind failed')
    absl_logger = playground.logging.get_absl_logger()
    initial_handlers = list(absl_logger.handlers)

    playground.main(['playground'])

    self.assertEqual(list(absl_logger.handlers), initial_handlers)
    mock_thread_cls.assert_called_once()
    self.assertTrue(mock_thread_cls.call_args.kwargs.get('daemon'))
    mock_thread_cls.return_value.start.assert_called_once()
    mock_serve_http.assert_called_once_with(mock.ANY, '/fake/static', 8080)
    mock_thread_cls.return_value.join.assert_called_once_with(timeout=5.0)

  @mock.patch.object(playground, '_serve_http', autospec=True)
  @mock.patch.object(
      playground.server,
      'get_default_static_dir',
      autospec=True,
      return_value='/fake/static',
  )
  @mock.patch.object(playground.threading, 'Thread', autospec=True)
  def test_main_uses_serial_flag_when_config_unset(
      self, mock_thread_cls, unused_mock_static_dir, unused_mock_serve_http
  ):
    with flagsaver.flagsaver((playground._SERIAL, 'emulator-5554')):
      playground.main(['playground'])

    passed_config = mock_thread_cls.call_args.kwargs['args'][1]
    self.assertEqual(
        passed_config,
        config_classes.AndroidDeviceConfig(serial='emulator-5554'),
    )

  @mock.patch.object(playground, '_serve_http', autospec=True)
  @mock.patch.object(
      playground.server,
      'get_default_static_dir',
      autospec=True,
      return_value='/fake/static',
  )
  @mock.patch.object(playground.threading, 'Thread', autospec=True)
  def test_main_uses_avd_name_flag_when_config_unset(
      self, mock_thread_cls, unused_mock_static_dir, unused_mock_serve_http
  ):
    with flagsaver.flagsaver((playground._AVD_NAME, 'my_test_avd')):
      playground.main(['playground'])

    passed_config = mock_thread_cls.call_args.kwargs['args'][1]
    self.assertIsInstance(passed_config, config_classes.AndroidDeviceConfig)
    self.assertIsNotNone(passed_config.emulator_launcher)
    self.assertEqual(passed_config.emulator_launcher.avd_name, 'my_test_avd')

  def test_main_raises_usage_error_when_serial_and_avd_name_both_set(self):
    with flagsaver.flagsaver(
        (playground._SERIAL, 'emulator-5554'),
        (playground._AVD_NAME, 'my_test_avd'),
    ):
      with self.assertRaises(playground.app.UsageError):
        playground.main(['playground'])

  @mock.patch.object(playground.app, 'run', autospec=True)
  def test_run_invokes_app_run(self, mock_app_run):
    playground.run()
    mock_app_run.assert_called_once_with(playground.main)

  def test_main_execution(self):
    original_setitem = playground.flags.FlagValues.__setitem__

    def _safe_setitem(
        fv_self: playground.flags.FlagValues,
        name: str,
        flag: playground.flags.Flag,
    ) -> None:
      try:
        original_setitem(fv_self, name, flag)
      except playground.flags.DuplicateFlagError:
        pass

    with mock.patch.object(
        playground.flags.FlagValues, '__setitem__', _safe_setitem
    ):
      with mock.patch.object(
          playground.app, 'run', autospec=True
      ) as mock_app_run:
        with mock.patch.object(sys, 'argv', ['playground.py']):
          runpy.run_module(
              'android_env.playground.playground',
              run_name='__main__',
          )
        mock_app_run.assert_called_once()
        self.assertEqual(mock_app_run.call_args[0][0].__name__, 'main')


if __name__ == '__main__':
  absltest.main()
