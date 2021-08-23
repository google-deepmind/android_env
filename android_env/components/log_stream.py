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

"""Abstract class for handling a stream of logs from a simulator."""

import abc
from typing import List
from absl import logging


class LogStream(metaclass=abc.ABCMeta):
  """Manages the stream of logs output by a simulator."""

  def __init__(self, verbose: bool = False):
    self._verbose = verbose
    self._filters = []

  def get_stream_output(self):
    """Starts log process and returns the stream of logs."""
    for line in self._get_stream_output():
      if self._verbose:
        logging.info('line: %r', line)
      yield line

  @abc.abstractmethod
  def _get_stream_output(self):
    """Starts log process and returns the stream of logs."""
    pass

  @abc.abstractmethod
  def stop_stream(self):
    """Stops the log stream from the simulator."""
    pass

  def set_log_filters(self, log_filters: List[str]):
    """Sets the filters for the log stream."""
    self._filters = list(log_filters) + ['*:S']
