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

"""Tests for android_env.wrappers.image_rescale_wrapper."""

from typing import Any
from unittest import mock

from absl.testing import absltest
from android_env import env_interface
from android_env.wrappers import image_rescale_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _simple_spec():
  return specs.BoundedArray(
      shape=np.array([300, 300, 3]),
      dtype=np.uint8,
      name='pixels',
      minimum=0,
      maximum=255)


def _simple_timestep():
  observation = np.ones(shape=[300, 300, 3])
  return dm_env.TimeStep(
      step_type=dm_env.StepType.MID,
      reward=3.14,
      discount=0.9,
      observation={'pixels': observation})


class ImageRescaleWrapperTest(absltest.TestCase):

  def test_100x50_grayscale(self):
    fake_timestep = _simple_timestep()
    fake_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    fake_env.observation_spec.return_value = {'pixels': _simple_spec()}
    fake_env.reset.return_value = fake_timestep
    fake_env.step.return_value = fake_timestep

    wrapper = image_rescale_wrapper.ImageRescaleWrapper(
        fake_env, zoom_factors=(1.0 / 3, 1.0 / 6.0), grayscale=True)
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (100, 50, 1))
    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (100, 50, 1))
    step_timestep = wrapper.step(action='fake_action')
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (100, 50, 1))

  def test_150x60_full_channels(self):
    fake_timestep = _simple_timestep()
    fake_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    fake_env.observation_spec.return_value = {'pixels': _simple_spec()}
    fake_env.reset.return_value = fake_timestep
    fake_env.step.return_value = fake_timestep

    wrapper = image_rescale_wrapper.ImageRescaleWrapper(
        fake_env, zoom_factors=(1.0 / 2.0, 1.0 / 5.0))
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (150, 60, 3))
    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (150, 60, 3))
    step_timestep = wrapper.step(action='fake_action')
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (150, 60, 3))

  def test_list_zoom_factor(self):
    fake_timestep = _simple_timestep()
    fake_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    fake_env.observation_spec.return_value = {'pixels': _simple_spec()}
    fake_env.reset.return_value = fake_timestep
    fake_env.step.return_value = fake_timestep

    wrapper = image_rescale_wrapper.ImageRescaleWrapper(
        fake_env, zoom_factors=[0.5, 0.2])
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (150, 60, 3))
    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (150, 60, 3))
    step_timestep = wrapper.step(action='fake_action')
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (150, 60, 3))

if __name__ == '__main__':
  absltest.main()
