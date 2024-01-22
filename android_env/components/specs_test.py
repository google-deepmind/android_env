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

"""Tests for specs.py."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import specs
from android_env.proto import task_pb2
from dm_env import specs as dm_env_specs
import numpy as np


class SpecsTest(parameterized.TestCase):

  def test_base_action_spec(self):
    action_spec = specs.base_action_spec(num_fingers=1)
    for spec in action_spec.values():
      self.assertIsInstance(spec, dm_env_specs.Array)
    self.assertEqual(action_spec['action_type'].shape, ())
    self.assertEqual(action_spec['action_type'].dtype, np.int32)
    self.assertEqual(action_spec['touch_position'].shape, (2,))
    self.assertEqual(action_spec['touch_position'].dtype, np.float32)

  def test_base_action_spec_with_key_events(self):
    action_spec = specs.base_action_spec(num_fingers=1, enable_key_events=True)
    for spec in action_spec.values():
      self.assertIsInstance(spec, dm_env_specs.Array)
    self.assertEqual(action_spec['action_type'].shape, ())
    self.assertEqual(action_spec['action_type'].dtype, np.int32)
    self.assertEqual(action_spec['touch_position'].shape, (2,))
    self.assertEqual(action_spec['touch_position'].dtype, np.float32)
    self.assertEqual(action_spec['keycode'].shape, ())
    self.assertEqual(action_spec['keycode'].dtype, np.int32)

  def test_base_action_spec_multitouch(self):
    action_spec = specs.base_action_spec(num_fingers=3)
    self.assertLen(action_spec.keys(), 6)
    for spec in action_spec.values():
      self.assertIsInstance(spec, dm_env_specs.Array)
    self.assertEqual(action_spec['action_type'].shape, ())
    self.assertEqual(action_spec['action_type'].dtype, np.int32)
    self.assertEqual(action_spec['touch_position'].shape, (2,))
    self.assertEqual(action_spec['touch_position'].dtype, np.float32)
    self.assertEqual(action_spec['action_type_2'].shape, ())
    self.assertEqual(action_spec['action_type_2'].dtype, np.int32)
    self.assertEqual(action_spec['touch_position_2'].shape, (2,))
    self.assertEqual(action_spec['touch_position_2'].dtype, np.float32)
    self.assertEqual(action_spec['action_type_3'].shape, ())
    self.assertEqual(action_spec['action_type_3'].dtype, np.int32)
    self.assertEqual(action_spec['touch_position_3'].shape, (2,))
    self.assertEqual(action_spec['touch_position_3'].dtype, np.float32)

  @parameterized.parameters(
      (480, 320),
      (100, 100),
      (1440, 1960),
  )
  def test_base_observation_spec(self, height, width):
    observation_spec = specs.base_observation_spec(height, width)
    for spec in observation_spec.values():
      self.assertIsInstance(spec, dm_env_specs.Array)
    self.assertEqual(observation_spec['pixels'].shape, (height, width, 3))
    self.assertEqual(observation_spec['pixels'].dtype, np.uint8)
    self.assertEqual(observation_spec['timedelta'].shape, ())
    self.assertEqual(observation_spec['timedelta'].dtype, np.int64)
    self.assertEqual(observation_spec['orientation'].shape, (4,))
    self.assertEqual(observation_spec['orientation'].dtype, np.uint8)


if __name__ == '__main__':
  absltest.main()
