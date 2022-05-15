# coding=utf-8
# Copyright 2022 DeepMind Technologies Limited.
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
from typing import Callable, Match, NamedTuple, Pattern

from absl import logging
from android_env.components import log_stream as log_stream_lib


class EventListener(NamedTuple):
  regexp: Pattern[str]
  handler_fn: Callable[[Pattern[str], Match[str]], None]


class LogcatThread:
  """Reads ADB logcat entries in a separate thread."""

  def __init__(self, log_stream: log_stream_lib.LogStream):
    """Initializes this LogcatThread with optional filters.

    Please see https://developer.android.com/studio/command-line/logcat for more
    info on `logcat`.

    Args:
      log_stream: Stream of logs from simulator.
    """

    self._listeners = {}
    self._line_ready = threading.Event()
    self._line_ready.set()
    self._log_stream = log_stream
    self._stdout = self._log_stream.get_stream_output()
    self._should_stop = threading.Event()
    self._thread = threading.Thread(target=self._process_logs)
    self._thread.daemon = True
    self._thread.start()

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

  def line_ready(self) -> threading.Event:
    """Indicates whether all listeners have been notified for a given line."""
    return self._line_ready

  def pause(self):
    self._log_stream.pause_stream()

  def resume(self):
    self._log_stream.resume_stream()

  def kill(self):
    self._should_stop.set()
    self._log_stream.stop_stream()
    self._thread.join(timeout=3.0)

  def _process_logs(self) -> None:
    """A loop that runs until `self._should_stop` is set()."""

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
      if self._should_stop.is_set():
        break

      if not line:  # Skip empty lines.
        continue

      # We're currently only consuming `message`, but we may use the other
      # fields in the future.
      matches = logline_re.match(line)
      if not matches or len(matches.groups()) != 6:
        continue

      # Make sure that values are not read until all listeners are notified.
      self._line_ready.clear()

      content = matches.group('message')
      for ev, listeners in self._listeners.items():
        ev_matches = ev.match(content)
        if ev_matches:
          # Notify listeners.
          for listener in listeners:
            listener(ev, ev_matches)

      self._line_ready.set()
