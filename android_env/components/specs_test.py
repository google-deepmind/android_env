# coding=utf-8
# Copyright 2023 DeepMind Technologies Limited.
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

  def test_base_task_extras_spec(self):
    array_spec_1 = task_pb2.ArraySpec()
    array_spec_1.name = 'my_extra_1'
    array_spec_1.shape.extend([10, 10])
    array_spec_1.dtype = task_pb2.ArraySpec.FLOAT

    array_spec_2 = task_pb2.ArraySpec()
    array_spec_2.name = 'my_extra_2'
    array_spec_2.shape.extend([1])
    array_spec_2.dtype = task_pb2.ArraySpec.UINT8

    fake_task = task_pb2.Task()
    fake_task.extras_spec.extend([array_spec_1, array_spec_2])
    task_extras_spec = specs.base_task_extras_spec(fake_task)
    for spec in task_extras_spec.values():
      self.assertIsInstance(spec, dm_env_specs.Array)

    self.assertEqual(task_extras_spec['my_extra_1'].shape, (10, 10))
    self.assertEqual(task_extras_spec['my_extra_2'].shape, (1,))
    self.assertEqual(task_extras_spec['my_extra_1'].dtype, np.float32)
    self.assertEqual(task_extras_spec['my_extra_2'].dtype, np.uint8)

  @parameterized.parameters(
      ('name_1', [480, 320, 3], task_pb2.ArraySpec.FLOAT, np.float32),
      ('name_2', [100, 100, 3], task_pb2.ArraySpec.INT32, np.int32),
      ('name_3', [123, 456, 3], task_pb2.ArraySpec.UINT8, np.uint8),
      ('name_4', [480, 320, 1], task_pb2.ArraySpec.BOOL, np.bool_),
      ('', [480, 320], task_pb2.ArraySpec.STRING_U25, np.dtype(('<U25'))),
      ('dict_spec', [100, 100], task_pb2.ArraySpec.OBJECT, np.object_),
  )
  def test_convert_spec(self, name, shape, dtype, expected_dtype):
    fake_array_spec = task_pb2.ArraySpec()
    fake_array_spec.name = name
    fake_array_spec.dtype = dtype
    fake_array_spec.shape.extend(shape)
    fake_task = task_pb2.Task()
    fake_task.extras_spec.extend([fake_array_spec])
    task_extras_spec = specs.base_task_extras_spec(fake_task)
    for spec in task_extras_spec.values():
      self.assertIsInstance(spec, dm_env_specs.Array)

    self.assertEqual(task_extras_spec[name].shape, tuple(shape))
    self.assertEqual(task_extras_spec[name].dtype, expected_dtype)


if __name__ == '__main__':
  absltest.main()
