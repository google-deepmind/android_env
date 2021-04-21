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

"""A utility class to run a function in a separate daemon thread."""

import abc
import enum
import queue
import threading

from absl import logging


class ThreadFunction(metaclass=abc.ABCMeta):
  """Base class that encapsulates long-lived functions in a separate thread."""

  class Signal(enum.IntEnum):
    """Defines commands we can use to communicate with the internal thread."""
    # The thread should be stopped to allow for graceful termination.
    KILL = 1

  def __init__(self, block_input: bool, block_output: bool, name: str):
    """Initializes this ThreadFunction.

    Args:
      block_input: Whether to block this thread when reading its input queue.
      block_output: Whether to block this thread when writing to its
          output queue.
      name: Name of the thread. Used to keep track of threads in logging.
    """
    self._block_input = block_input
    self._block_output = block_output
    self._name = name

    self._input_queue = queue.Queue()
    self._output_queue = queue.Queue()
    self._should_run = True
    self._internal_thread = threading.Thread(target=self._run)
    self._internal_thread.daemon = True
    self._internal_thread.start()

  def read(self, block: bool = True, timeout: float = None):
    """'Public' method for clients to read values _from_ this thread.

    Args:
      block: Whether the client should block.
      timeout: Timeout for getting output from the queue, in seconds.
    Returns:
      The value produced by the underlying thread.
    """
    try:
      return self._output_queue.get(block=block, timeout=timeout)
    except queue.Empty:
      return None

  def write(self, value, block: bool = True, timeout: float = None):
    """'Public' method for clients to write values _to_ this thread.

    Args:
      value: The value to send to the underlying thread.
      block: Whether the client should block.
      timeout: Timeout for setting input in the queue, in seconds.
    Returns:
      The value produced by the underlying thread.
    """
    self._input_queue.put(value, block=block, timeout=timeout)

  @abc.abstractmethod
  def main(self):
    """main() function that subclasses need to override."""
    pass

  def kill(self):
    """Shorthand for clients to terminate this thread."""
    logging.info('Killing %s thread', self._name)
    # Sending a kill signal to clean up blocked read_values.
    self.write(ThreadFunction.Signal.KILL, block=True)
    # Stopping the _run loop.
    self._should_run = False

  def _run(self):
    """'Private' method that reruns main() until explicit termination."""
    logging.info('Starting %s thread.', self._name)
    while self._should_run:
      self.main()
    logging.info('Finished %s thread.', self._name)

  def _read_value(self):
    """'Protected' method for subclasses to read values from their input."""
    try:
      return self._input_queue.get(block=self._block_input)
    except queue.Empty:
      pass  # Ignore empty queues. Keep going.

  def _write_value(self, value):
    """'Protected' method for subclasses to write values to their output."""
    self._output_queue.put(value, block=self._block_output)
