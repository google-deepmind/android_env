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

"""Tests for android_env.wrappers.last_action_wrapper."""

from typing import Any
from unittest import mock

from absl.testing import absltest
from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import last_action_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _simple_spec():
  return specs.BoundedArray(
      shape=np.array([120, 80, 3]),
      dtype=np.uint8,
      name='pixels',
      minimum=0,
      maximum=255)


def _simple_timestep():
  observation = np.ones(shape=[120, 80, 3])
  return dm_env.TimeStep(
      step_type=dm_env.StepType.MID,
      reward=3.14,
      discount=0.9,
      observation={'pixels': observation})


class LastActionWrapperTest(absltest.TestCase):

  def test_concat_to_pixels(self):
    fake_timestep = _simple_timestep()
    fake_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    fake_env.observation_spec.return_value = {'pixels': _simple_spec()}
    fake_env.reset.return_value = fake_timestep
    fake_env.step.return_value = fake_timestep

    wrapper = last_action_wrapper.LastActionWrapper(
        fake_env, concat_to_pixels=True)
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (120, 80, 4))

    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (120, 80, 4))
    last_action_layer = reset_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 0)

    action1 = {
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),  # (W x H)
    }
    type(fake_env).raw_action = mock.PropertyMock(return_value=action1)
    step_timestep = wrapper.step(action=action1)
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 4))  # (H x W)
    last_action_layer = step_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (90, 20))

    action2 = {
        'action_type': action_type.ActionType.LIFT,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),
    }
    type(fake_env).raw_action = mock.PropertyMock(return_value=action2)
    step_timestep = wrapper.step(action=action2)
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 4))
    last_action_layer = step_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 0)

    action3 = {
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([0.25, 1.0], dtype=np.float32),
    }
    type(fake_env).raw_action = mock.PropertyMock(return_value=action3)
    step_timestep = wrapper.step(action=action3)
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 4))
    last_action_layer = step_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (119, 20))

  def test_no_concat_to_pixels(self):
    fake_timestep = _simple_timestep()
    fake_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    fake_env.observation_spec.return_value = {'pixels': _simple_spec()}
    fake_env.reset.return_value = fake_timestep
    fake_env.step.return_value = fake_timestep

    wrapper = last_action_wrapper.LastActionWrapper(
        fake_env, concat_to_pixels=False)
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (120, 80, 3))
    self.assertEqual(wrapper.observation_spec()['last_action'].shape, (120, 80))

    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (120, 80, 3))
    last_action_layer = reset_timestep.observation['last_action']
    self.assertEqual(np.sum(last_action_layer), 0)

    action1 = {
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),
    }
    type(fake_env).raw_action = mock.PropertyMock(return_value=action1)
    step_timestep = wrapper.step(action=action1)
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 3))
    last_action_layer = step_timestep.observation['last_action']
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (90, 20))

    action2 = {
        'action_type': action_type.ActionType.LIFT,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),
    }
    type(fake_env).raw_action = mock.PropertyMock(return_value=action2)
    step_timestep = wrapper.step(action=action2)
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 3))
    last_action_layer = step_timestep.observation['last_action']
    self.assertEqual(np.sum(last_action_layer), 0)

    action3 = {
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([1.0, 0.75], dtype=np.float32),
    }
    type(fake_env).raw_action = mock.PropertyMock(return_value=action3)
    step_timestep = wrapper.step(action=action3)
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 3))
    last_action_layer = step_timestep.observation['last_action']
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (90, 79))

if __name__ == '__main__':
  absltest.main()
