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

"""Tests for a11y_forests."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components.a11y import a11y_forests
from android_env.proto.a11y import android_accessibility_forest_pb2
import numpy as np

from google.protobuf import any_pb2


def _pack_any(proto_message) -> any_pb2.Any:
  response = any_pb2.Any()
  response.Pack(proto_message)
  return response


def _empty_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  return android_accessibility_forest_pb2.AndroidAccessibilityForest()


def _one_empty_window_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  forest.windows.add()
  return forest


def _two_window_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  window = forest.windows.add()
  window.tree.nodes.add(
      class_name='foo', is_clickable=True, hint_text='Foo hint'
  )
  forest.windows.add()
  return forest


class A11YForestsTest(parameterized.TestCase):

  @parameterized.parameters(
      dict(task_extras={}, expected_forests=[], convert_to_np=[]),
      dict(
          task_extras={'accessibility_tree': []},
          convert_to_np=['accessibility_tree'],
          expected_forests=[],
      ),
      dict(
          task_extras={
              'not_accessibility_tree': [
                  _empty_forest(),
                  _one_empty_window_forest(),
                  _two_window_forest(),
              ],
          },
          convert_to_np=['not_accessibility_tree'],
          expected_forests=[],
      ),
      dict(
          task_extras={
              'accessibility_tree': [
                  _empty_forest(),
                  {'not_a_forest_key': 'nor_a_forest_value'},
                  _two_window_forest(),
              ]
          },
          convert_to_np=['accessibility_tree'],
          expected_forests=[_empty_forest(), _two_window_forest()],
      ),
      dict(
          task_extras={
              'accessibility_tree': [
                  {'not_a_forest_key': 'nor_a_forest_value'},
                  3,
                  4,
                  {'not_a_forest_key': _empty_forest()},
              ],
          },
          convert_to_np=['accessibility_tree'],
          expected_forests=[],
      ),
      dict(
          task_extras={'accessibility_tree': []},
          convert_to_np=['accessibility_tree'],
          expected_forests=[],
      ),
      dict(
          task_extras={
              'accessibility_tree_wrong_key': [1, 2, 3],
              'accessibility_tree': [
                  _empty_forest(),
                  None,
                  None,
                  _one_empty_window_forest(),
                  _two_window_forest(),
              ],
          },
          convert_to_np=['accessibility_tree', 'accessibility_tree_wrong_key'],
          expected_forests=[
              _empty_forest(),
              _one_empty_window_forest(),
              _two_window_forest(),
          ],
      ),
      dict(
          task_extras={
              'accessibility_tree_wrong_key': [1, 2, 3],
              'accessibility_tree': [
                  None,
                  _pack_any(_empty_forest()),
                  _pack_any(_one_empty_window_forest()),
                  _pack_any(_two_window_forest()),
              ],
          },
          convert_to_np=['accessibility_tree', 'accessibility_tree_wrong_key'],
          expected_forests=[
              _empty_forest(),
              _one_empty_window_forest(),
              _two_window_forest(),
          ],
      ),
      dict(
          task_extras={
              'accessibility_tree': [
                  _pack_any(_empty_forest()),
                  {'not_a_forest_key': 'nor_a_forest_value'},
                  None,
                  _two_window_forest(),
                  None,
              ]
          },
          convert_to_np=['accessibility_tree'],
          expected_forests=[_empty_forest(), _two_window_forest()],
      ),
  )
  def test_task_extras(self, task_extras, expected_forests, convert_to_np):
    for k in convert_to_np:
      if task_extras[k]:
        task_extras[k] = np.stack(task_extras[k], axis=0)
      else:
        task_extras[k] = np.array([])
    forests = a11y_forests.extract_forests_from_task_extras(task_extras)
    self.assertEqual(len(forests), len(expected_forests))
    for idx, f in enumerate(forests):
      self.assertEqual(f, expected_forests[idx])

  @parameterized.parameters(
      dict(task_extras={}, expected_extras={}),
      dict(
          task_extras={
              'no_accessibility_tree': 42,
          },
          expected_extras={
              'no_accessibility_tree': 42,
          },
      ),
      dict(
          task_extras={'accessibility_tree': []},
          expected_extras={'accessibility_tree': []},
      ),
      dict(
          task_extras={
              'accessibility_tree': [
                  _empty_forest(),
                  _one_empty_window_forest(),
              ],
              'no_accessibility_tree': 43,
          },
          expected_extras={
              'accessibility_tree': [_one_empty_window_forest()],
              'no_accessibility_tree': 43,
          },
      ),
      dict(
          task_extras={
              'accessibility_tree': [
                  _empty_forest(),
                  _one_empty_window_forest(),
                  _two_window_forest(),
              ]
          },
          expected_extras={'accessibility_tree': [_two_window_forest()]},
      ),
      dict(
          task_extras={
              'accessibility_tree': [],
              'no_accessibility_tree': 44,
          },
          expected_extras={
              'accessibility_tree': [],
              'no_accessibility_tree': 44,
          },
      ),
  )
  def test_keep_latest_only(self, task_extras, expected_extras):
    if 'accessibility_tree' in task_extras:
      if task_extras['accessibility_tree']:
        task_extras['accessibility_tree'] = np.stack(
            task_extras['accessibility_tree'], axis=0
        )
      else:
        task_extras['accessibility_tree'] = np.array([])

    a11y_forests.keep_latest_forest_only(task_extras)
    self.assertSameElements(task_extras.keys(), expected_extras.keys())
    for k in task_extras.keys():
      if k == 'accessibility_tree':
        self.assertEqual(len(task_extras[k]), len(expected_extras[k]))
        for idx, f in enumerate(task_extras[k]):
          self.assertEqual(f, expected_extras[k][idx])
      else:
        self.assertEqual(task_extras[k], expected_extras[k])
    pass


if __name__ == '__main__':
  absltest.main()
