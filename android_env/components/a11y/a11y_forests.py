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

from android_env.proto.a11y import android_accessibility_forest_pb2
import numpy as np

from google.protobuf import any_pb2


_A11Y_FORESTS_KEY = 'accessibility_tree'


def package_forests_to_task_extras(
    forests: list[android_accessibility_forest_pb2.AndroidAccessibilityForest],
) -> Mapping[str, np.ndarray]:
  if not forests:
    return {}
  forests = np.stack(forests, axis=0)
  return {_A11Y_FORESTS_KEY: forests}


def task_extras_has_forests(task_extras: Mapping[str, Any]) -> bool:
  """Checks that the task_extras has any a11y forest information."""
  if _A11Y_FORESTS_KEY not in task_extras:
    return False

  payload = task_extras[_A11Y_FORESTS_KEY]
  if not isinstance(payload, np.ndarray) or payload.ndim != 1:
    raise ValueError(
        f'{_A11Y_FORESTS_KEY} task extra should be a numpy array with one'
        f' dimension. payload: {payload}'
    )

  if payload.size == 0:
    return False

  if any(isinstance(f, any_pb2.Any) for f in payload):
    # Forests were packed as Any.
    return True

  return any(
      isinstance(f, android_accessibility_forest_pb2.AndroidAccessibilityForest)
      for f in payload
  )


def convert_to_forest(
    forest: android_accessibility_forest_pb2.AndroidAccessibilityForest
    | any_pb2.Any
    | None,
) -> android_accessibility_forest_pb2.AndroidAccessibilityForest | None:
  """Takes an object and attempts to convert it to a forest."""
  if forest is None:
    return None

  if isinstance(forest, any_pb2.Any):
    output = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    new_any = any_pb2.Any()
    new_any.CopyFrom(forest)
    new_any.Unpack(output)
    return output
  elif isinstance(
      forest, android_accessibility_forest_pb2.AndroidAccessibilityForest
  ):
    return forest
  else:
    return None


def extract_forests_from_task_extras(
    task_extras: Mapping[str, Any] | None = None,
) -> list[android_accessibility_forest_pb2.AndroidAccessibilityForest]:
  """Inspects task_extras and extracts all accessibility forests detected.

  Args:
    task_extras: Task extras forwarded by AndroidEnv. If 'full_event' is not a
      key in task_extras, then this function returns an empty string. Otherwise,
      full_event is expected to be list to be a numpy array with one dimension,
      and contains a list of dictionary describing accessibility forests that
      are present in the given task extras.

  Returns:
    List of all forests detected
  """
  if task_extras is None or not task_extras_has_forests(task_extras):
    return []

  forests = []
  for f in task_extras[_A11Y_FORESTS_KEY]:
    f = convert_to_forest(f)
    if f is not None:
      forests.append(f)
  return forests


def keep_latest_forest_only(task_extras: dict[str, Any]):
  """Removes all a11y forests except the last one observed."""
  if _A11Y_FORESTS_KEY not in task_extras.keys():
    return

  payload = task_extras[_A11Y_FORESTS_KEY]
  if not isinstance(payload, np.ndarray) or payload.ndim != 1:
    raise ValueError(
        f'{_A11Y_FORESTS_KEY} task extra should be a numpy array with one'
        f' dimension. payload: {payload}'
    )

  if payload.size == 0:
    return

  task_extras[_A11Y_FORESTS_KEY] = payload[-1:]
