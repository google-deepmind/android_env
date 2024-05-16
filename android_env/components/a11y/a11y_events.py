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

"""Tools for accessing accessibility events."""

from collections.abc import Mapping
from typing import Any

from absl import logging
from android_env.proto.a11y import a11y_pb2
import numpy as np

from google.protobuf import any_pb2


_A11Y_EVENT_KEY = 'full_event'


def package_events_to_task_extras(
    events: list[a11y_pb2.EventRequest],
) -> Mapping[str, np.ndarray]:
  if not events:
    return {}
  events = np.stack(events, axis=0)
  return {_A11Y_EVENT_KEY: events}


def extract_events_from_task_extras(
    task_extras: Mapping[str, Any] | None = None,
) -> list[Mapping[str, str]]:
  """Inspects task_extras and extracts all accessibility events detected.

  Args:
    task_extras: Task extras forwarded by AndroidEnv. If 'full_event' is not a
      key in task_extras, then this function returns an empty string. Otherwise,
      full_event is expected to be list to be a numpy array with one dimension,
      and contains a list of dictionary describing accessibility events that are
      present in the given task extras. e.g. 'event_type:
      TYPE_WINDOW_CONTENT_CHANGED // event_package_name:
      com.google.android.deskclock // source_class_name:
      android.widget.ImageView'.

  Returns:
    List of all events detected
  """
  if task_extras is None or _A11Y_EVENT_KEY not in task_extras:
    return []

  if (
      not isinstance(task_extras[_A11Y_EVENT_KEY], np.ndarray)
      or task_extras[_A11Y_EVENT_KEY].ndim != 1
  ):
    raise ValueError(
        f'{_A11Y_EVENT_KEY} task extra should be a numpy array with one'
        ' dimension.'
    )

  if task_extras[_A11Y_EVENT_KEY].size == 0:
    return []

  events = []
  for e in task_extras[_A11Y_EVENT_KEY]:
    if isinstance(e, a11y_pb2.EventRequest):
      events.append(dict(e.event))
    elif isinstance(e, dict):
      events.append(e)
      logging.warning(
          'The event should come only from the a11y_grpc_wrapper. '
          'Please verify that the upacking operation has not been '
          'called twice. See here for full task_extras: %s',
          task_extras,
      )
    elif isinstance(e, any_pb2.Any):
      ev = a11y_pb2.EventRequest()
      new_any = any_pb2.Any()
      new_any.CopyFrom(e)
      new_any.Unpack(ev)
      events.append(dict(ev.event))

    else:
      raise TypeError(
          f'Unexpected event type: {type(e)}. See here for full '
          f'task_extras: {task_extras}.'
      )

  return events


def keep_latest_event_only(task_extras: dict[str, Any]):
  """Removes all a11y events except the last one observed."""
  if task_extras is None or 'full_event' not in task_extras:
    return

  if (
      not isinstance(task_extras[_A11Y_EVENT_KEY], np.ndarray)
      or task_extras[_A11Y_EVENT_KEY].ndim != 1
  ):
    raise ValueError(
        f'{_A11Y_EVENT_KEY} task extra should be a numpy array with one'
        ' dimension.'
    )

  if task_extras[_A11Y_EVENT_KEY].size == 0:
    return []

  task_extras[_A11Y_EVENT_KEY] = task_extras[_A11Y_EVENT_KEY][-1:]
