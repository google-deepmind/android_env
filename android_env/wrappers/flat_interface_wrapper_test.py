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

"""Tests for android_env.wrappers.flat_interface_wrapper."""

from typing import cast
from unittest import mock

from absl.testing import absltest
from android_env.wrappers import flat_interface_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _make_array_spec(shape, dtype=np.float32, name=None, maximum=3, minimum=0):
  return specs.BoundedArray(
      shape=shape,
      dtype=dtype,
      name=name,
      maximum=np.ones(shape) * maximum,
      minimum=np.ones(shape) * minimum)


def _make_timestep(observation):
  return dm_env.TimeStep(
      step_type='fake_step_type',
      reward='fake_reward',
      discount='fake_discount',
      observation=observation,
  )


class FlatInterfaceWrapperTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.action_shape = (1,)
    self.base_action_spec: dict[str, specs.DiscreteArray] = {
        'action_id': specs.DiscreteArray(name='action_id', num_values=4)
    }
    self.int_obs_shape = (3, 4, 2)
    self.float_obs_shape = (2,)
    self.base_observation_spec = {
        'pixels': _make_array_spec(
            shape=self.int_obs_shape, dtype=np.uint8, name='pixels'),
        'obs1': _make_array_spec(
            shape=self.float_obs_shape, dtype=np.float32, name='obs1'),
    }
    # Expected.
    self.expected_observation_spec = _make_array_spec(
        shape=self.int_obs_shape, dtype=np.uint8, name='pixels')
    self.image_obs = np.ones(self.int_obs_shape, dtype=np.uint8)
    self.expected_timestep = _make_timestep(self.image_obs)

    # Expected for no new action layer shape.
    expected_new_shape_no_action_layer = (3, 4, 1)
    self.expected_observation_spec_no_action_layer = _make_array_spec(
        shape=expected_new_shape_no_action_layer, dtype=np.uint8, name='pixels')
    self.expected_timestep_no_action_layer = _make_timestep(
        np.ones(expected_new_shape_no_action_layer, dtype=np.uint8))

    # Base environment.
    self.other_obs = np.ones(self.float_obs_shape, dtype=np.float32)
    self.base_timestep = _make_timestep({
        'pixels': self.image_obs,
        'obs1': self.other_obs})
    self.base_env = mock.create_autospec(dm_env.Environment)
    self.base_env.action_spec.return_value = self.base_action_spec
    self.base_env.observation_spec.return_value = self.base_observation_spec
    self.base_env.reset.return_value = self.base_timestep
    self.base_env.step.return_value = self.base_timestep

  def test_reset(self):
    wrapped_env = flat_interface_wrapper.FlatInterfaceWrapper(self.base_env)
    ts = wrapped_env.reset()
    self.base_env.reset.assert_called_once()
    self.assertEqual(self.expected_timestep, ts)

  def test_reset_no_action_layer(self):
    wrapped_env = flat_interface_wrapper.FlatInterfaceWrapper(
        self.base_env, keep_action_layer=False)
    ts = wrapped_env.reset()
    self.base_env.reset.assert_called_once()
    self.assertEqual(
        self.expected_timestep_no_action_layer.observation.tolist(),
        ts.observation.tolist())

  def test_step(self):
    wrapped_env = flat_interface_wrapper.FlatInterfaceWrapper(self.base_env)
    action = 2
    ts = wrapped_env.step(action)

    def verifier(x):
      self.assertIsInstance(x, dict)
      self.assertIsInstance(x['action_id'], int)
      self.assertEqual(x['action_id'], action)
      return True
    verifier(self.base_env.step.call_args[0][0])
    self.assertEqual(self.expected_timestep, ts)

  def test_step_no_action_layer(self):
    wrapped_env = flat_interface_wrapper.FlatInterfaceWrapper(
        self.base_env, keep_action_layer=False)
    action = 2
    ts = wrapped_env.step(action)

    def verifier(x):
      self.assertIsInstance(x, dict)
      self.assertIsInstance(x['action_id'], int)
      self.assertEqual(x['action_id'], action)
      return True

    verifier(self.base_env.step.call_args[0][0])
    self.assertEqual(
        self.expected_timestep_no_action_layer.observation.tolist(),
        ts.observation.tolist())

  def test_observation_spec(self):
    wrapped_env = flat_interface_wrapper.FlatInterfaceWrapper(self.base_env)
    observation_spec = wrapped_env.observation_spec()
    self.base_env.observation_spec.assert_called_once()
    self.assertEqual(self.expected_observation_spec, observation_spec)

  def test_observation_spec_no_action_layer(self):
    wrapped_env = flat_interface_wrapper.FlatInterfaceWrapper(
        self.base_env, keep_action_layer=False)
    observation_spec = wrapped_env.observation_spec()
    self.base_env.observation_spec.assert_called_once()
    self.assertEqual(self.expected_observation_spec_no_action_layer,
                     observation_spec)

  def test_action_spec(self):
    wrapped_env = flat_interface_wrapper.FlatInterfaceWrapper(self.base_env)
    action_spec = cast(specs.BoundedArray, wrapped_env.action_spec())
    parent_action_spec = self.base_action_spec['action_id']

    self.assertEqual(parent_action_spec.name, action_spec.name)
    self.assertEqual((), action_spec.shape)
    self.assertEqual(np.int32, action_spec.dtype)
    self.assertEqual(0, action_spec.minimum)

  def test_bad_action_spec_structured_action(self):
    bad_base_env = mock.create_autospec(dm_env.Environment)
    bad_base_env.action_spec.return_value = {
        'action_id': _make_array_spec((1,)),
        'too_many': _make_array_spec((1,))
    }
    with self.assertRaises(AssertionError):
      _ = flat_interface_wrapper.FlatInterfaceWrapper(bad_base_env)


if __name__ == '__main__':
  absltest.main()
