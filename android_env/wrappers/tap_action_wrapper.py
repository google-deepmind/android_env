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

"""Wraps the AndroidEnv environment to provide tap actions of a given duration."""

from collections.abc import Sequence

from android_env.components import action_type
from android_env.wrappers import base_wrapper
import dm_env
import numpy as np


class TapActionWrapper(base_wrapper.BaseWrapper):
  """AndroidEnv with tap actions."""

  def __init__(self,
               env: dm_env.Environment,
               num_frames: int = 5,
               touch_only: bool = False):
    super().__init__(env)
    assert 'action_type' in env.action_spec()
    self._touch_only = touch_only
    self._num_frames = num_frames
    self._env_steps = 0

  def stats(self):
    """Returns a dictionary of metrics logged by the environment."""
    logs = self._env.stats()
    logs.update({'env_steps': self._env_steps})
    return logs

  def _process_action(
      self, action: dict[str, np.ndarray]
  ) -> Sequence[dict[str, np.ndarray]]:
    if self._touch_only:
      assert action['action_type'] == 0
      touch_action = action.copy()
      touch_action['action_type'] = np.array(
          action_type.ActionType.TOUCH
      ).astype(self.action_spec()['action_type'].dtype)
      actions = [touch_action] * self._num_frames
      lift_action = action.copy()
      lift_action['action_type'] = np.array(action_type.ActionType.LIFT).astype(
          self.action_spec()['action_type'].dtype
      )
      actions.append(lift_action)

    else:
      if action['action_type'] == action_type.ActionType.TOUCH:
        actions = [action] * self._num_frames
        lift_action = action.copy()
        lift_action['action_type'] = np.array(
            action_type.ActionType.LIFT
        ).astype(self.action_spec()['action_type'].dtype)
        actions.append(lift_action)
      else:
        actions = [action] * (self._num_frames + 1)

    return actions

  def step(self, action: dict[str, np.ndarray]) -> dm_env.TimeStep:
    """Takes a step in the environment."""
    self._env_steps += self._num_frames + 1
    actions = self._process_action(action)
    total_reward = 0.0
    for idx in range(len(actions)):
      step_type, reward, discount, observation = self._env.step(actions[idx])
      if reward:
        total_reward += reward
      if step_type == dm_env.StepType.LAST:
        return dm_env.TimeStep(
            step_type=step_type,
            reward=total_reward,
            discount=discount,
            observation=observation)
    return dm_env.TimeStep(
        step_type=step_type,
        reward=total_reward,
        discount=discount,
        observation=observation)

  def action_spec(self) -> dict[str, dm_env.specs.Array]:
    if self._touch_only:
      return {
          'action_type':
              dm_env.specs.DiscreteArray(num_values=1, name='action_type'),
          'touch_position':
              self._env.action_spec()['touch_position'],
      }
    else:
      return self._env.action_spec()
