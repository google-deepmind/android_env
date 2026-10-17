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

"""Unit tests for the custom PlaygroundLogHandler log streaming component."""

import logging
import socket
from unittest import mock

from absl.testing import absltest
from android_env.playground import log_handler
from android_env.playground import state as state_lib


class LogHandlerTest(absltest.TestCase):

  def test_playground_log_handler(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock

    handler = log_handler.PlaygroundLogHandler(state)
    logger = logging.getLogger('test_logger')
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)

    logger.info('Test log entry')

    logs = state.get_logs()
    self.assertLen(logs, 1)
    self.assertEqual(logs[0]['message'], 'Test log entry')
    self.assertEqual(logs[0]['level'], 'INFO')

    mock_sock.sendall.assert_called_once()
    logger.removeHandler(handler)

  def test_playground_log_handler_prevents_reentrant_emit(self):
    state = state_lib.PlaygroundState()
    handler = log_handler.PlaygroundLogHandler(state)
    record = logging.makeLogRecord({'msg': 'First log', 'levelname': 'INFO'})

    def recursive_send_logs(unused_state, unused_logs):
      handler.emit(record)

    with mock.patch.object(
        log_handler.websocket, 'try_send_logs', side_effect=recursive_send_logs
    ):
      handler.emit(record)

    self.assertLen(state.get_logs(), 1)

  def test_playground_log_handler_format_error(self):
    state = state_lib.PlaygroundState()
    handler = log_handler.PlaygroundLogHandler(state)
    bad_record = logging.makeLogRecord(
        {'msg': 'Bad format %d', 'args': ('not_an_int',), 'levelname': 'INFO'}
    )
    with mock.patch.object(handler, 'handleError', autospec=True) as mock_err:
      handler.emit(bad_record)
      mock_err.assert_called_once_with(bad_record)
    self.assertEmpty(state.get_logs())

    good_record = logging.makeLogRecord(
        {'msg': 'Recovered', 'levelname': 'INFO'}
    )
    handler.emit(good_record)
    self.assertLen(state.get_logs(), 1)

  def test_playground_log_handler_skips_internal_websocket_logs(self):
    state = state_lib.PlaygroundState()
    mock_sock = mock.create_autospec(socket.socket, instance=True)
    state.active_ws = mock_sock

    handler = log_handler.PlaygroundLogHandler(state)
    ws_record = logging.makeLogRecord({
        'msg': 'ACK timeout, resetting waiting_for_ack',
        'levelname': 'WARNING',
        'pathname': '/path/to/websocket.py',
    })
    ws_record.filename = 'websocket.py'
    handler.emit(ws_record)

    mock_sock.sendall.assert_not_called()
    self.assertEmpty(state.get_logs())


if __name__ == '__main__':
  absltest.main()
