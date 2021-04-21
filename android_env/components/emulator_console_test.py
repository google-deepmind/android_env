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

"""Tests for android_env.components.emulator_console."""

import builtins
import os
import telnetlib
import time

from absl.testing import absltest
from android_env.components import emulator_console
from android_env.components import errors
from android_env.proto import raw_observation_pb2
import mock
import numpy as np


class EmulatorConsoleTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    # Create a mock file with a fake auth code.
    self._mock_auth_file = mock.MagicMock()
    self._mock_auth_file.__enter__ = mock.MagicMock(
        return_value=self._mock_auth_file)
    self._mock_auth_file.read.return_value = 'some_code_i_dont_care'

    # Create a mock file to hold the FIFO.
    self._mock_fifo_file = mock.MagicMock()
    self._mock_fifo_file.__enter__ = mock.MagicMock(
        return_value=self._mock_fifo_file)

    self._mock_open = mock.patch.object(builtins, 'open', autospec=True).start()

    def fake_open(fname, mode=''):
      """A closure that returns auth file the first time, then fifo."""
      del fname, mode
      fake_open.open_counter += 1
      if fake_open.open_counter == 1:
        return self._mock_auth_file
      return self._mock_fifo_file

    fake_open.open_counter = 0  # Function attribute ("static" local variable).
    self._mock_open.side_effect = fake_open

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
        tmp_dir=absltest.get_default_test_tmpdir())
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
          tmp_dir=absltest.get_default_test_tmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)

  @mock.patch.object(os.path, 'expanduser', autospec=True)
  def test_no_auth_should_look_in_home_folder(self, mock_expanduser):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=absltest.get_default_test_tmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      mock_expanduser.assert_called_once()
      console.close()

  @mock.patch.object(os, 'remove', autospec=True)
  @mock.patch.object(os.path, 'isfile', autospec=True)
  def test_existing_fifo_should_be_deleted(self, mock_isfile, mock_remove):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    # Pretend that a fifo with that name already exists so that we verify that
    # EmulatorConsole is deleting and recreating it.
    mock_isfile.return_value = True

    self._mock_fifo_file.read.return_value = b''

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=absltest.get_default_test_tmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)
      mock_isfile.assert_called_once()
      mock_remove.assert_called_once()

      console.close()

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
          tmp_dir=absltest.get_default_test_tmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)

    console.send_mouse_action(7, 8, True)
    telnet_connection.write.assert_called()

    # Close the console.
    console.close()

    # Because fetch_screenshot() was not called, the pipe was not actually
    # opened so we don't expect it to be closed.
    mock_close.assert_has_calls([])
    mock_remove.assert_has_calls([])

  def test_fetch_screenshot_timedout(self):
    """Ensures that we get an exception if `fetch_screenshot` takes >20s."""
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'
    pipe_read_timeout = 1.0

    def stuck_read():
      """A .read() call that takes a long time to return something."""
      time.sleep(pipe_read_timeout + 5)
      return b'hello there'

    self._mock_fifo_file.read.side_effect = stuck_read

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=absltest.get_default_test_tmpdir(),
          pipe_read_timeout_sec=pipe_read_timeout)
      telnet_init.assert_called_once_with('localhost', 1234)

    self.assertRaises(errors.PipeTimedOutError, console.fetch_screenshot)

    console.close()

  def test_fetch_screenshot_io_error(self):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    # Create a fake flat image with 4 channels.
    fake_img = np.array(list(range(10)) * 4, dtype=np.uint8)
    fake_raw_obs = raw_observation_pb2.RawObservation()
    fake_raw_obs.screen.data = fake_img.tobytes()
    fake_raw_obs.screen.height = 5
    fake_raw_obs.screen.width = 2
    fake_raw_obs.screen.num_channels = 4
    fake_raw_obs.timestamp_us = 123456789

    # Setup fifo as thread starts reading in the constructor.
    def io_error_read():
      io_error_read.counter += 1
      if io_error_read.counter % 2 == 1:
        return fake_raw_obs.SerializeToString()
      raise IOError('Nooo, f.read() crashed!')

    io_error_read.counter = 0
    self._mock_fifo_file.read.side_effect = io_error_read

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=absltest.get_default_test_tmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)

    self.assertRaises(IOError, console.fetch_screenshot)

    console.close()

  def test_fetch_screenshot_decoding_error(self):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    # Setup fifo as thread starts reading in the constructor.
    def bad_proto_read():
      bad_proto_read.counter += 1
      if bad_proto_read.counter % 2 == 1:
        return b'I am definitely not a RawObservation!'
      else:
        return b''

    bad_proto_read.counter = 0
    self._mock_fifo_file.read.side_effect = bad_proto_read

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=absltest.get_default_test_tmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)

    self.assertRaises(errors.ObservationDecodingError, console.fetch_screenshot)

    console.close()

  def test_fetch_screenshot_ok(self):
    telnet_connection = mock.create_autospec(telnetlib.Telnet)
    telnet_connection.read_until.return_value = 'OK'

    # Create a fake flat image with 4 channels.
    fake_img = np.array(list(range(10)) * 4, dtype=np.uint8)
    fake_raw_obs = raw_observation_pb2.RawObservation()
    fake_raw_obs.screen.data = fake_img.tobytes()
    fake_raw_obs.screen.height = 5
    fake_raw_obs.screen.width = 2
    fake_raw_obs.screen.num_channels = 4
    fake_raw_obs.timestamp_us = 123456789

    # Setup fifo as thread starts reading in the constructor.
    def good_read():
      good_read.counter += 1
      if good_read.counter % 2 == 1:
        return fake_raw_obs.SerializeToString()
      else:
        return b''

    good_read.counter = 0
    self._mock_fifo_file.read.side_effect = good_read

    with mock.patch.object(
        telnetlib, 'Telnet', autospec=True,
        return_value=telnet_connection) as telnet_init:
      console = emulator_console.EmulatorConsole(
          console_port=1234,
          auth_code=None,
          tmp_dir=absltest.get_default_test_tmpdir())
      telnet_init.assert_called_once_with('localhost', 1234)

    observation = console.fetch_screenshot()

    reference_img = fake_img.reshape((5, 2, 4))
    reference_img = np.delete(reference_img, 3, 2)
    np.testing.assert_equal(reference_img, observation[0])
    self.assertEqual(observation[1], 123456789)

    # Close the console.
    console.close()


if __name__ == '__main__':
  absltest.main()
