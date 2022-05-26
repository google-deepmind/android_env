# coding=utf-8
# Copyright 2022 DeepMind Technologies Limited.
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

from typing import Any, Dict

from absl.testing import absltest
from android_env import environment
from android_env.components import action_type
from android_env.wrappers import last_action_wrapper
import dm_env
from dm_env import specs
import numpy as np


class FakeEnv(environment.AndroidEnv):
  """A class that we can use to inject custom observations and specs."""

  def __init__(self, obs_spec):
    self._obs_spec = obs_spec
    self._next_obs = None
    self._latest_action = {}

  def reset(self) -> dm_env.TimeStep:
    return self._next_timestep

  def step(self, action: Any) -> dm_env.TimeStep:
    self._latest_action = action
    return self._next_timestep

  def observation_spec(self) -> Dict[str, specs.Array]:
    return self._obs_spec

  def action_spec(self) -> Dict[str, specs.Array]:
    assert False, 'This should not be called by tests.'

  def set_next_timestep(self, timestep):
    self._next_timestep = timestep


def _simple_spec():
  return specs.Array(
      shape=np.array([120, 80, 3]), dtype=np.uint8, name='pixels')


def _simple_timestep():
  observation = np.ones(shape=[120, 80, 3])
  return dm_env.TimeStep(
      step_type=dm_env.StepType.MID,
      reward=3.14,
      discount=0.9,
      observation={'pixels': observation})


class LastActionWrapperTest(absltest.TestCase):

  def test_concat_to_pixels(self):
    obs_spec = {'pixels': _simple_spec()}
    fake_env = FakeEnv(obs_spec)
    fake_env.set_next_timestep(_simple_timestep())

    wrapper = last_action_wrapper.LastActionWrapper(
        fake_env, concat_to_pixels=True)
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (120, 80, 4))

    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (120, 80, 4))
    last_action_layer = reset_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 0)

    step_timestep = wrapper.step(action={
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),  # (W x H)
    })
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 4))  # (H x W)
    last_action_layer = step_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (90, 20))

    step_timestep = wrapper.step(action={
        'action_type': action_type.ActionType.LIFT,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),
    })
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 4))
    last_action_layer = step_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 0)

    step_timestep = wrapper.step(action={
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([0.25, 1.0], dtype=np.float32),
    })
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 4))
    last_action_layer = step_image[:, :, -1]
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (119, 20))

  def test_no_concat_to_pixels(self):
    obs_spec = {'pixels': _simple_spec()}
    fake_env = FakeEnv(obs_spec)
    fake_env.set_next_timestep(_simple_timestep())

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

    step_timestep = wrapper.step(action={
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),
    })
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 3))
    last_action_layer = step_timestep.observation['last_action']
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (90, 20))

    step_timestep = wrapper.step(action={
        'action_type': action_type.ActionType.LIFT,
        'touch_position': np.array([0.25, 0.75], dtype=np.float32),
    })
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 3))
    last_action_layer = step_timestep.observation['last_action']
    self.assertEqual(np.sum(last_action_layer), 0)

    step_timestep = wrapper.step(action={
        'action_type': action_type.ActionType.TOUCH,
        'touch_position': np.array([1.0, 0.75], dtype=np.float32),
    })
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (120, 80, 3))
    last_action_layer = step_timestep.observation['last_action']
    self.assertEqual(np.sum(last_action_layer), 255)
    y, x = np.where(last_action_layer == 255)
    self.assertEqual((y.item(), x.item()), (90, 79))

if __name__ == '__main__':
  absltest.main()
