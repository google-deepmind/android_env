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

"""Abstract class for handling a stream of logs from a simulator."""

import abc
from collections.abc import Generator, Sequence
import threading
from absl import logging


class LogStream(metaclass=abc.ABCMeta):
  """Manages the stream of logs output by a simulator."""

  def __init__(self, verbose: bool = False):
    self._verbose = verbose
    self._filters = []
    self._should_stream = threading.Event()

  def get_stream_output(self) -> Generator[str, None, None]:
    """Starts log process and returns the stream of logs."""
    for line in self._get_stream_output():
      if self._verbose:
        logging.info('line: %r', line)
      if self._should_stream.is_set():
        yield line

  @abc.abstractmethod
  def _get_stream_output(self):
    """Starts log process and returns the stream of logs."""
    pass

  @abc.abstractmethod
  def stop_stream(self) -> None:
    """Terminates the log stream.

    NOTE: This should only be called _after_ `get_stream_output()`.
    """

  def pause_stream(self) -> None:
    """No lines are yielded while the event is not set."""
    logging.info('Pausing LogStream.')
    self._should_stream.clear()

  def resume_stream(self) -> None:
    """The stream will continue yielding lines if the event is set."""
    logging.info('Resuming LogStream.')
    self._should_stream.set()

  def set_log_filters(self, log_filters: Sequence[str]):
    """Sets the filters for the log stream."""
    self._filters = list(log_filters) + ['*:S']
