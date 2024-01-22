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

"""Tests for android_env.wrappers.gym_wrapper."""

from unittest import mock

from absl.testing import absltest
from android_env import env_interface
from android_env.wrappers import gym_wrapper
import dm_env
from dm_env import specs
from gym import spaces
import numpy as np


class GymInterfaceWrapperTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    self._base_env.action_spec.return_value = {
        'action_type':
            specs.DiscreteArray(
                num_values=3,
                name='action_type'),
        'touch_position':
            specs.BoundedArray(
                shape=(2,),
                dtype=np.float32,
                minimum=[0.0, 0.0],
                maximum=[1.0, 1.0],
                name='touch_position'),
    }
    self._base_env.observation_spec.return_value = {
        'pixels':
            specs.Array(
                shape=(480, 320, 3),
                dtype=np.uint8,
                name='pixels'),
        'timedelta':
            specs.Array(shape=(), dtype=np.int64, name='timedelta'),
        'orientation':
            specs.Array(
                shape=np.array([4]),
                dtype=np.uint8,
                name='orientation'),
    }
    self._wrapped_env = gym_wrapper.GymInterfaceWrapper(self._base_env)
    self._fake_ts = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        observation={'pixels': np.ones(shape=(2, 3))},
        reward=10.0,
        discount=1.0)

  def test_render(self):
    self._base_env.step.return_value = self._fake_ts
    _ = self._wrapped_env.step(action=np.zeros(shape=(1,)))
    image = self._wrapped_env.render(mode='rgb_array')
    self.assertTrue(np.array_equal(image, np.ones(shape=(2, 3))))

  def test_render_error(self):
    with self.assertRaises(ValueError):
      _ = self._wrapped_env.render(mode='human')

  def test_reset(self):
    self._base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        observation={'pixels': np.ones(shape=(2, 3))},
        reward=10.0,
        discount=1.0)
    obs = self._wrapped_env.reset()
    self._base_env.reset.assert_called_once()
    self.assertTrue(np.array_equal(obs['pixels'], np.ones(shape=(2, 3))))

  def test_step(self):
    self._base_env.step.return_value = self._fake_ts
    obs, _, _, _ = self._wrapped_env.step(action=np.zeros(shape=(1,)))
    self._base_env.step.assert_called_once()
    self.assertTrue(np.array_equal(obs['pixels'], np.ones(shape=(2, 3))))

  def test_spec_to_space(self):

    spec = specs.Array(
        shape=(2, 3),
        dtype=np.float32)
    space = self._wrapped_env._spec_to_space(spec)
    self.assertEqual(space, spaces.Box(
        low=-np.inf, high=np.inf, shape=spec.shape, dtype=spec.dtype))

    spec = specs.BoundedArray(
        shape=(),
        dtype=np.float32,
        minimum=4,
        maximum=5)
    space = self._wrapped_env._spec_to_space(spec)
    self.assertEqual(space, spaces.Box(
        low=4, high=5, shape=spec.shape, dtype=spec.dtype))

    spec = specs.DiscreteArray(num_values=4)
    space = self._wrapped_env._spec_to_space(spec)
    self.assertEqual(space, spaces.Box(
        low=0, high=3, shape=(), dtype=np.int32))


if __name__ == '__main__':
  absltest.main()
