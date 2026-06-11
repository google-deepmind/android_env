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

"""Fake implementation of LogStream for testing."""

from collections.abc import Callable, Generator, Iterable, Sequence
import queue
from android_env.components import log_stream


class FakeLogStream(log_stream.LogStream):
  """Fake implementation of LogStream for testing."""

  def __init__(
      self,
      verbose: bool = False,
      log_generator: Iterable[str] | None = None,
      filter_fn: Callable[[Sequence[str], str], bool] | None = None,
  ):
    super().__init__(verbose=verbose)
    self._log_generator = log_generator
    self._filter_fn = filter_fn
    self._queue = queue.Queue()
    self._stream_is_alive = True

  def _get_stream_output(self) -> Generator[str, None, None]:
    if self._log_generator is not None:
      for line in self._log_generator:
        if not self._stream_is_alive:
          break
        if self._filter_fn and not self._filter_fn(self._filters, line):
          continue
        yield line
    else:
      while self._stream_is_alive:
        try:
          # Use a timeout to allow checking if the stream is still alive.
          line = self._queue.get(timeout=0.1)
          if self._filter_fn and not self._filter_fn(self._filters, line):
            continue
          yield line
        except queue.Empty:
          continue

  def stop_stream(self) -> None:
    self._stream_is_alive = False
    if hasattr(self._log_generator, 'kill'):
      self._log_generator.kill()
    elif hasattr(self._log_generator, 'close'):
      self._log_generator.close()

  def reset(self) -> None:
    self._stream_is_alive = True
    self._queue = queue.Queue()
    if hasattr(self._log_generator, 'reset'):
      self._log_generator.reset()

  @property
  def stream_is_alive(self) -> bool:
    return self._stream_is_alive

  def send_value(self, value: str) -> None:
    self._queue.put(value)

  def send_values(self, values: Iterable[str]) -> None:
    for val in values:
      self._queue.put(val)
