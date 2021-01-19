"""Tests for android_env.components.emulator_console."""

import builtins
import os
import select
import telnetlib
import time

from android_env.components import emulator_console
from android_env.components import errors
from android_env.proto import raw_observation_pb2
import mock
import numpy as np

from google3.testing.pybase import googletest


class EmulatorConsoleTest(googletest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    # Create a mock file with a fake auth code.
    self._mock_auth_file = mock.MagicMock()
    self._mock_auth_file.__enter__ = mock.MagicMock(
        return_value=self._mock_auth_file)
    self._mock_auth_file.read.return_value = 'some_code_i_dont_care'
    self._mock_open = mock.patch.object(builtins, 'open', autospec=True).start()
    self._mock_open.return_value = self._mock_auth_file

    # Create a mock file to hold the FIFO.
    self._mock_fifo_file = mock.MagicMock()
    self._mock_fifo_file.read.return_value = 'some encoded image'

    self._mock_os_open = mock.patch.object(os, 'open', autospec=True).start()
    self._mock_os_open.return_value = self._mock_fifo_file

  @mock.patch.object(time, 'sleep', autospec=True)
  @mock.patch.object(
      telnetlib,
      'Telnet',
      side_effect=ConnectionRefusedError('oops'),
      autospec=True)
  def test_connection_error(self, telnet_connection, mock_sleep):
    self.assertRaises(
        errors.ConsoleConnectionError,
        emulator_console.EmulatorConsole,
        console_port=1234,
        auth_code='dont_share_it_please',
        tmp_dir=googletest.GetDefaultTestTmpdir())
    telnet_connection.assert_has_calls([mock.call('localhost', 1234)] * 3)
    mock_sleep.assert_called()

  def test_auth_error(self):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'whatever. I will not be used'
    telnet_connection.read_until.side_effect = EOFError('oh no')

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      self.assertRaises(
          EOFError,
          emulator_console.EmulatorConsole,
          console_port=1234,
          auth_code='dont_share_it_please',
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)

  @mock.patch.object(os.path, 'expanduser', autospec=True)
  def test_no_auth_should_look_in_home_folder(self, mock_expanduser):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      _ = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      mock_expanduser.assert_called_once()
      self._mock_open.assert_called_once()

  @mock.patch.object(os, 'remove', autospec=True)
  @mock.patch.object(os.path, 'isfile', autospec=True)
  def test_existing_fifo_should_be_deleted(self, mock_isfile, mock_remove):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    # Pretend that a fifo with that name already exists so that we verify that
    # EmulatorConsole is deleting and recreating it.
    mock_isfile.return_value = True

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      _ = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      self._mock_open.assert_called_once()
      mock_isfile.assert_called_once()
      mock_remove.assert_called_once()

  @mock.patch.object(os, 'remove', autospec=True)
  @mock.patch.object(os, 'close', autospec=True)
  def test_send_mouse_action(self, mock_close, mock_remove):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      self._mock_open.assert_called_once()

    console.send_mouse_action(7, 8, True)
    telnet_connection.write.assert_called()

    # Close the console.
    console.close()

    # Because fetch_screenshot() was not called, the pipe was not actually
    # opened so we don't expect it to be closed.
    mock_close.assert_has_calls([])
    mock_remove.assert_has_calls([])

  @mock.patch.object(select, 'select', autospec=True)
  def test_fetch_screenshot_timedout(self, mock_select):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      self._mock_open.assert_called_once()

    mock_select.return_value = ([123], None, None)

    self.assertRaises(errors.PipeTimedOutError, console.fetch_screenshot)

  @mock.patch.object(os, 'read', autospec=True)
  @mock.patch.object(select, 'select', autospec=True)
  def test_fetch_screenshot_os_error(self, mock_select, mock_os_read):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      self._mock_open.assert_called_once()

    mock_select.return_value = ([self._mock_fifo_file], None, None)

    # Create a fake flat image with 4 channels.
    fake_img = np.array(list(range(10)) * 4, dtype=np.uint8)
    fake_raw_obs = raw_observation_pb2.RawObservation()
    fake_raw_obs.screen.data = fake_img.tobytes()
    fake_raw_obs.screen.height = 5
    fake_raw_obs.screen.width = 2
    fake_raw_obs.screen.num_channels = 4
    fake_raw_obs.timestamp_us = 123456789

    mock_os_read.side_effect = [
        b'',  # 1st call.
        fake_raw_obs.SerializeToString(),  # 2nd call.
        OSError('Nooo, os.read() crashed!'),
        b''  # final call.
    ]

    self.assertRaises(OSError, console.fetch_screenshot)

  @mock.patch.object(os, 'read', autospec=True)
  @mock.patch.object(select, 'select', autospec=True)
  def test_fetch_screenshot_decoding_error(self, mock_select, mock_os_read):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      self._mock_open.assert_called_once()

    mock_select.return_value = ([self._mock_fifo_file], None, None)

    mock_os_read.side_effect = [
        b'',  # 1st call.
        b'I am definitely not a RawObservation!',  # 2nd call.
        b''  # final call.
    ]

    self.assertRaises(errors.ObservationDecodingError, console.fetch_screenshot)

  @mock.patch.object(os, 'read', autospec=True)
  @mock.patch.object(select, 'select', autospec=True)
  @mock.patch.object(os, 'remove', autospec=True)
  @mock.patch.object(os, 'close', autospec=True)
  def test_fetch_screenshot_ok(self, mock_close, unused_mock_remove,
                               mock_select, mock_os_read):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=googletest.GetDefaultTestTmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      self._mock_open.assert_called_once()

    mock_select.return_value = ([self._mock_fifo_file], None, None)

    # Create a fake flat image with 4 channels.
    fake_img = np.array(list(range(10)) * 4, dtype=np.uint8)
    fake_raw_obs = raw_observation_pb2.RawObservation()
    fake_raw_obs.screen.data = fake_img.tobytes()
    fake_raw_obs.screen.height = 5
    fake_raw_obs.screen.width = 2
    fake_raw_obs.screen.num_channels = 4
    fake_raw_obs.timestamp_us = 123456789

    mock_os_read.side_effect = [
        b'',  # 1st call.
        fake_raw_obs.SerializeToString(),  # 2nd call.
        b''  # final call.
    ]

    observation = console.fetch_screenshot()

    reference_img = fake_img.reshape((5, 2, 4))
    reference_img = np.delete(reference_img, 3, 2)
    np.testing.assert_equal(reference_img, observation[0])
    self.assertEqual(observation[1], 123456789)

    # Close the console.
    console.close()

    # It should cleanup the resources it acquired.
    mock_close.assert_called_once()


if __name__ == '__main__':
  googletest.main()
