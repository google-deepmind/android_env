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

"""Logging handler for AndroidEnv Playground."""

import logging
import threading

from android_env.playground import state as state_lib
from android_env.playground import websocket


class _LogState(threading.local):
  active: bool = False


class PlaygroundLogHandler(logging.Handler):
  """Custom logging handler to store logs in PlaygroundState and stream via WS."""

  def __init__(self, state: state_lib.PlaygroundState):
    super().__init__()
    self.state = state
    self._is_logging = _LogState()

  def emit(self, record: logging.LogRecord):
    if self._is_logging.active:
      return
    # Avoid feedback loops and lock contention from internal networking logs.
    if getattr(record, 'filename', '') in ('websocket.py', 'server.py'):
      return
    self._is_logging.active = True
    try:
      try:
        msg = self.format(record)
      except (
          TypeError,
          ValueError,
          AttributeError,
          KeyError,
          RuntimeError,
          IndexError,
      ):
        self.handleError(record)
        return

      log_entry = {
          'message': str(msg),
          'level': str(record.levelname),
          'timestamp': record.created,
      }
      self.state.add_log(log_entry)
      websocket.try_send_logs(self.state, [log_entry])
    finally:
      self._is_logging.active = False
