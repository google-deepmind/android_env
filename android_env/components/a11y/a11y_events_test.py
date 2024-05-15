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

"""Tests for a11y_events."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components.a11y import a11y_events
from android_env.proto.a11y import a11y_pb2
import numpy as np

from google.protobuf import any_pb2


def _event_request(d: dict[str, str]) -> a11y_pb2.EventRequest:
  event_request = a11y_pb2.EventRequest()
  for k, v in d.items():
    event_request.event[k] = v
  return event_request


def _event_request_as_any(d: dict[str, str]) -> any_pb2.Any:
  event_request = _event_request(d)
  response = any_pb2.Any()
  response.Pack(event_request)
  return response


class A11yEventsTest(parameterized.TestCase):

  @parameterized.parameters(
      dict(task_extras={}),
      dict(
          task_extras={'no_full_event': [{'1': '1'}, {'2': '2'}, {'3': '3'}]},
      ),
      dict(
          task_extras={'full_event': np.array([])},
      ),
      dict(
          task_extras={},
      ),
  )
  def test_no_events_in_task_extras(self, task_extras):
    events = a11y_events.extract_events_from_task_extras(task_extras)
    self.assertEmpty(events)

  @parameterized.parameters(
      dict(
          task_extras={'full_event': [{'1': '1'}, {'2': '2'}]},
          expected_events=[{'1': '1'}, {'2': '2'}],
      ),
      dict(
          task_extras={'full_event': [{}]},
          expected_events=[{}],
      ),
      dict(
          task_extras={
              'full_event_wrong_key': [1, 2, 3],
              'full_event': [{'1': '1'}, {'2': '2'}, {'3': '3'}],
          },
          expected_events=[{'1': '1'}, {'2': '2'}, {'3': '3'}],
      ),
  )
  def test_task_extras(self, task_extras, expected_events):
    event_requests = [_event_request(e) for e in task_extras['full_event']]
    task_extras['full_event'] = np.stack(event_requests, axis=0)
    events = a11y_events.extract_events_from_task_extras(task_extras)
    self.assertEqual(len(events), len(expected_events))
    for i, event in enumerate(expected_events):
      self.assertEqual(len(event), len(expected_events[i]))
      for k, v in event.items():
        self.assertIn(k, expected_events[i])
        self.assertEqual(v, expected_events[i][k])

  def test_events_key_has_dict_event_requrests(self):
    event_requests = [
        _event_request({'1': '1'}),
        {'2': '2'},
        _event_request({'3': '3'}),
    ]
    expected_events = [
        {'1': '1'},
        {'2': '2'},
        {'3': '3'},
    ]
    task_extras = {'full_event': np.stack(event_requests, axis=0)}
    events = a11y_events.extract_events_from_task_extras(task_extras)
    self.assertEqual(len(events), len(expected_events))
    for i, event in enumerate(expected_events):
      self.assertEqual(len(event), len(expected_events[i]))
      for k, v in event.items():
        self.assertIn(k, expected_events[i])
        self.assertEqual(v, expected_events[i][k])

  def test_events_key_has__event_requrests_packed_as_any(self):
    event_requests = [
        _event_request_as_any({'1': '1'}),
        {'2': '2'},
        _event_request_as_any({'3': '3'}),
    ]
    expected_events = [
        {'1': '1'},
        {'2': '2'},
        {'3': '3'},
    ]
    task_extras = {'full_event': np.stack(event_requests, axis=0)}
    events = a11y_events.extract_events_from_task_extras(task_extras)
    self.assertEqual(len(events), len(expected_events))
    for i, event in enumerate(expected_events):
      self.assertEqual(len(event), len(expected_events[i]))
      for k, v in event.items():
        self.assertIn(k, expected_events[i])
        self.assertEqual(v, expected_events[i][k])

  def test_events_key_has_non_event_requrests(self):
    event_requests = [
        _event_request({'1': '1'}),
        3,  # Not an even and not a dict.
        _event_request({'3': '3'}),
    ]
    task_extras = {'full_event': np.stack(event_requests, axis=0)}
    with self.assertRaises(TypeError):
      _ = a11y_events.extract_events_from_task_extras(task_extras)

  @parameterized.parameters(
      dict(task_extras={}, expected_extras={}),
      dict(
          task_extras={
              'no_full_event': 42,
          },
          expected_extras={
              'no_full_event': 42,
          },
      ),
      dict(
          task_extras={'full_event': np.array([1, 2]), 'no_full_event': 43},
          expected_extras={'full_event': np.array([2]), 'no_full_event': 43},
      ),
      dict(
          task_extras={'full_event': np.array([1, 2, 3])},
          expected_extras={'full_event': np.array([3])},
      ),
      dict(
          task_extras={'full_event': np.array([]), 'no_full_event': 44},
          expected_extras={'full_event': np.array([]), 'no_full_event': 44},
      ),
  )
  def test_keep_latest_only(self, task_extras, expected_extras):
    a11y_events.keep_latest_event_only(task_extras)
    self.assertEqual(len(task_extras), len(expected_extras))
    for k, v in task_extras.items():
      self.assertIn(k, expected_extras)
      if k == 'full_event':
        np.testing.assert_array_equal(v, expected_extras['full_event'])
      else:
        self.assertEqual(v, expected_extras[k])
    pass


if __name__ == '__main__':
  absltest.main()
