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

"""Tests for android_env.wrappers.float_pixels_wrapper."""

from unittest import mock

from absl.testing import absltest
from android_env.wrappers import float_pixels_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _make_array_spec(shape, dtype=np.float32, name=None):
  return specs.Array(
      shape=shape,
      dtype=dtype,
      name=name,
  )


def _make_bounded_array_spec(
    shape, dtype=np.float32, name=None, maximum=1.0, minimum=0.0):
  return specs.BoundedArray(
      shape=shape,
      dtype=dtype,
      name=name,
      maximum=maximum,
      minimum=minimum,
  )


def _simple_timestep(obs_shape, obs_type):
  return dm_env.TimeStep(
      step_type=dm_env.StepType.MID,
      reward=3.14,
      discount=0.9,
      observation=(np.ones(shape=obs_shape, dtype=obs_type),),
  )


class FloatPixelsWrapperTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.pixels_shape = (3, 4)
    base_pixel_spec = _make_array_spec(
        shape=self.pixels_shape, dtype=np.uint8, name='pixels')
    self.other_obs_spec = _make_array_spec(
        shape=(1,), dtype=np.float32, name='other_obs')
    base_observation_spec = {
        'pixels': base_pixel_spec,
        'other_obs': self.other_obs_spec
    }
    self.base_env = mock.create_autospec(dm_env.Environment)
    self.base_env.observation_spec.return_value = base_observation_spec

    self.base_timestep = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=3.14,
        discount=0.9,
        observation={
            'pixels': np.ones(shape=self.pixels_shape, dtype=np.uint8),
            'other_obs': [42.2]})
    self.base_env.step.return_value = self.base_timestep
    self.base_env.reset.return_value = self.base_timestep

  def test_float_pixels_wrapper_spec(self):
    expected_pixel_spec = _make_bounded_array_spec(
        shape=self.pixels_shape,
        dtype=np.float32,
        name='pixels',
        minimum=0.0,
        maximum=1.0)

    wrapped_env = float_pixels_wrapper.FloatPixelsWrapper(self.base_env)

    self.assertLen(wrapped_env.observation_spec(), 2)
    self.assertEqual(expected_pixel_spec,
                     wrapped_env.observation_spec()['pixels'])
    self.assertEqual(self.other_obs_spec,
                     wrapped_env.observation_spec()['other_obs'])

  def test_float_pixels_wrapper_step(self):
    wrapped_env = float_pixels_wrapper.FloatPixelsWrapper(self.base_env)
    ts = wrapped_env.step({'fake_action': np.array([1, 2, 3])})

    self.assertEqual(self.base_timestep.step_type, ts.step_type)
    self.assertEqual(self.base_timestep.reward, ts.reward)
    self.assertEqual(self.base_timestep.discount, ts.discount)
    self.assertEqual(self.base_timestep.observation['other_obs'],
                     ts.observation['other_obs'])
    expected_pixel_value = 1. / 255.  # original values are unit8
    expected_pixels = np.ones(
        self.pixels_shape, dtype=np.float32) * expected_pixel_value
    np.testing.assert_equal(expected_pixels, ts.observation['pixels'])

  def test_float_pixels_wrapper_reset(self):
    wrapped_env = float_pixels_wrapper.FloatPixelsWrapper(self.base_env)
    ts = wrapped_env.reset()

    self.assertEqual(self.base_timestep.step_type, ts.step_type)
    self.assertEqual(self.base_timestep.reward, ts.reward)
    self.assertEqual(self.base_timestep.discount, ts.discount)
    self.assertEqual(self.base_timestep.observation['other_obs'],
                     ts.observation['other_obs'])
    expected_pixel_value = 1. / 255.  # original values are unit8
    expected_pixels = np.ones(
        self.pixels_shape, dtype=np.float32) * expected_pixel_value
    np.testing.assert_equal(expected_pixels, ts.observation['pixels'])

  def test_float_pixels_wrapper_already_float(self):
    base_pixel_spec = _make_array_spec(
        shape=self.pixels_shape, dtype=np.float64, name='pixels')
    base_observation_spec = {
        'pixels': base_pixel_spec,
        'other_obs': self.other_obs_spec
    }
    base_env = mock.create_autospec(dm_env.Environment)
    base_env.observation_spec.return_value = base_observation_spec

    wrapped_env = float_pixels_wrapper.FloatPixelsWrapper(base_env)

    # If the pixels are already float values, then obs_spec does not change.
    self.assertEqual(base_env.observation_spec(),
                     wrapped_env.observation_spec())

    # The wrapper should not touch the timestep in this case.
    fake_timestep = ('step_type', 'reward', 'discount', 'obs')
    base_env.step.return_value = fake_timestep
    ts = wrapped_env.step({'fake_action': np.array([1, 2, 3])})
    self.assertEqual(fake_timestep, ts)


if __name__ == '__main__':
  absltest.main()
