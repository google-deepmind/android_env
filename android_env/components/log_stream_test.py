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

"""Tests for log_stream."""

from absl.testing import absltest
from android_env.components import log_stream


class FakeLogStream(log_stream.LogStream):

  def __init__(self, filter_name: str):
    super().__init__()
    self._filter_name = filter_name

  def _get_stream_output(self):
    """Starts a log process and returns the stream of logs."""
    lines = [
        f'{self._filter_name} fake_line_1',
        'fake_line_2',
        f'{self._filter_name} fake_line_3',
        f'{self._filter_name} fake_line_4',
        'fake_line_5',
        'fake_line_6',
    ]
    for line in lines:
      if f'{self._filter_name}:V' in self._filters:
        if self._filter_name in line:
          yield line
      else:
        yield line

  def stop_stream(self):
    """Stops the log stream from the simulator."""
    pass


class LogStreamTest(absltest.TestCase):

  def test_get_stream_output(self):
    filter_name = 'AndroidRLTask'
    stream = FakeLogStream(filter_name=filter_name)
    stream.resume_stream()
    stream_output = stream.get_stream_output()
    expected_lines = [
        f'{filter_name} fake_line_1',
        'fake_line_2',
        f'{filter_name} fake_line_3',
        f'{filter_name} fake_line_4',
        'fake_line_5',
        'fake_line_6',
    ]
    for line, expected_line in zip(stream_output, expected_lines):
      self.assertEqual(line, expected_line)

  def test_set_log_filters(self):
    filter_name = 'AndroidRLTask'
    stream = FakeLogStream(filter_name=filter_name)
    stream.set_log_filters([f'{filter_name}:V'])
    stream.resume_stream()
    stream_output = stream.get_stream_output()
    expected_lines = [
        f'{filter_name} fake_line_1',
        f'{filter_name} fake_line_3',
        f'{filter_name} fake_line_4',
    ]
    for line, expected_line in zip(stream_output, expected_lines):
      self.assertEqual(line, expected_line)

  def test_pause_resume_stream(self):
    filter_name = 'AndroidRLTask'
    stream = FakeLogStream(filter_name=filter_name)
    stream.resume_stream()
    stream_output = stream.get_stream_output()
    expected_lines = [
        f'{filter_name} fake_line_1',
        'fake_line_2',
        f'{filter_name} fake_line_3',
        f'{filter_name} fake_line_4',
        'fake_line_5',
        'fake_line_6',
    ]
    for line, expected_line in zip(stream_output, expected_lines):
      self.assertEqual(line, expected_line)
    # If the stream is paused, we expect no lines to be yielded.
    stream.pause_stream()
    stream_output = list(stream.get_stream_output())
    self.assertEmpty(stream_output)
    # If the stream is resumed, we expect to see all lines yielded.
    stream.resume_stream()
    stream_output = stream.get_stream_output()
    for line, expected_line in zip(stream_output, expected_lines):
      self.assertEqual(line, expected_line)


if __name__ == '__main__':
  absltest.main()
