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

"""A class that launches a thread to read Android logcat outputs."""

import re
import threading
# `typing.Pattern` has been deprecated in Python 3.9 in favor of `re.Pattern`,
# but it is not available even in slightly older Python versions.
# Please see https://www.python.org/dev/peps/pep-0585/
from typing import Callable, Match, NamedTuple, Optional, Pattern

from absl import logging
from android_env.components import log_stream as log_stream_lib
from android_env.components import thread_function
from android_env.proto import task_pb2


class EventListener(NamedTuple):
  regexp: Pattern[str]
  handler_fn: Callable[[Pattern[str], Match[str]], None]


class LogcatThread(thread_function.ThreadFunction):
  """Reads ADB logcat entries in a separate thread."""

  def __init__(
      self,
      log_stream: log_stream_lib.LogStream,
      log_parsing_config: task_pb2.LogParsingConfig,
      name: str = 'logcat'):
    """Initializes this LogcatThread with optional filters.

    Please see https://developer.android.com/studio/command-line/logcat for more
    info on `logcat`.

    Args:
      log_stream: Stream of logs from simulator.
      log_parsing_config: Determines the types of messages we want logcat to
        match. Contains `filters` and `log_regexps`.
      name: Name of the thread.
    """

    self._regexps = log_parsing_config.log_regexps
    self._listeners = {}
    self._desired_event = None
    self._thread_event = threading.Event()
    self._max_buffer_size = 100
    self._log_stream = log_stream
    self._log_stream.set_log_filters(list(log_parsing_config.filters))

    self._stdout = self._log_stream.get_stream_output()

    super().__init__(block_input=True, block_output=False, name=name)

  def add_event_listener(self, event_listener: EventListener) -> None:
    """Adds `fn` to the list of handlers to call when `event` occurs."""
    event_regexp = event_listener.regexp
    if event_regexp not in self._listeners:
      self._listeners[event_regexp] = []
    self._listeners[event_regexp].append(event_listener.handler_fn)

  def remove_event_listener(self, event_listener: EventListener) -> None:
    """Removes `fn` from the list of handlers to call when `event` occurs."""
    event_regexp = event_listener.regexp
    if event_regexp not in self._listeners:
      logging.error('Event: %r is not registered.', event_regexp)
      return
    self._listeners[event_regexp].remove(event_listener.handler_fn)

  def wait(self,
           event: Optional[Pattern[str]] = None,
           timeout_sec: Optional[float] = None) -> None:
    """Blocks (caller) execution for up to `timeout_sec` until `event` is fired.

    Args:
      event: Event to wait for. If None, any new event will cause this function
        to return.
      timeout_sec: Maximum time to block waiting for an event.
    """
    self._desired_event = event
    self._thread_event.wait(timeout=timeout_sec)
    self._thread_event.clear()

  def kill(self):
    self._log_stream.stop_stream()

    super().kill()

  def main(self) -> None:
    # pylint: disable=g-line-too-long
    # Format is: "TIME_SEC PID TID PRIORITY TAG: MESSAGE"
    #
    # Example:
    #  '         1553110400.424  5583  5658 D NostalgicRacer: com.google.example.games.nostalgicracer.views.renderers.OpenGLRenderDriver@912fb8.onSurfaceChanged 480x320'    #
    #
    # If a log_prefix is given, then the format becomes:
    # "TIME_SEC PID TID PRIORITY TAG: LOG_PREFIX MESSAGE"
    # pylint: enable=g-line-too-long

    regexp = r"""
      ^                                   # Beginning of the line.
      [ ]+(?P<timestamp>[0-9]+\.[0-9]+)   # Spaces and a float.
      [ ]+(?P<pid>[0-9]+)                 # Spaces and an int.
      [ ]+(?P<tid>[0-9]+)                 # Spaces and an int.
      [ ]+(?P<priority>.)                 # Spaces and any single character.
      [ ]+(?P<tag>[^:]*):                 # Spaces and any char that's not ':'.
    """

    regexp += r"""[ ](?P<message>.*)$"""
    logline_re = re.compile(regexp, re.VERBOSE)

    for line in self._stdout:
      # We never hand back control to ThreadFunction._run() so we need to
      # explicitly check for self._should_run here.
      if not self._should_run:
        break

      if not line:  # Skip empty lines.
        continue

      # We're currently only consuming `message`, but we may use the other
      # fields in the future.
      matches = logline_re.match(line)
      if not matches or len(matches.groups()) != 6:
        continue

      content = matches.group('message')
      for ev, listeners in self._listeners.items():
        ev_matches = ev.match(content)
        if ev_matches:
          # Unblock consumers that may be waiting for events.
          if not self._thread_event.is_set():
            if self._desired_event:
              if self._desired_event == ev:
                self._thread_event.set()
            else:
              self._thread_event.set()

          # Notify listeners.
          for listener in listeners:
            listener(ev, ev_matches)
