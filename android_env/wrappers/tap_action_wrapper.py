# coding=utf-8
# Copyright 2026 DeepMind Technologies Limited.
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

from collections.abc import Mapping, Sequence
from typing import Any

from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import base_wrapper
import dm_env
import numpy as np


class TapActionWrapper(base_wrapper.BaseWrapper):
  """AndroidEnv with tap actions."""

  def __init__(
      self,
      env: env_interface.AndroidEnvInterface,
      *,
      num_steps: int = 5,
      touch_only: bool = False,
  ) -> None:
    """Initializes the instance.

    Args:
      env: The underlying environment.
      num_steps: The number of steps on the underlying environment to hold the
        tap for.
      touch_only: If True, the action spec is restricted to only allow
        specifying touch position.
    """
    super().__init__(env)
    assert 'action_type' in env.action_spec()
    self._touch_only = touch_only
    self._num_steps = num_steps
    self._env_steps = 0

  def stats(self) -> dict[str, Any]:
    """Returns a dictionary of metrics logged by the environment."""
    logs = self._env.stats()
    logs.update({'env_steps': self._env_steps})
    return logs

  def _process_action(
      self, action: Mapping[str, np.ndarray]
  ) -> Sequence[dict[str, np.ndarray]]:
    if self._touch_only:
      assert action['action_type'] == 0
      touch_action = dict(action)
      touch_action['action_type'] = np.array(
          action_type.ActionType.TOUCH
      ).astype(self.action_spec()['action_type'].dtype)
      actions = [touch_action] * self._num_steps
      lift_action = dict(action)
      lift_action['action_type'] = np.array(action_type.ActionType.LIFT).astype(
          self.action_spec()['action_type'].dtype
      )
      actions.append(lift_action)

    else:
      if action['action_type'] == action_type.ActionType.TOUCH:
        actions = [dict(action)] * self._num_steps
        lift_action = dict(action)
        lift_action['action_type'] = np.array(
            action_type.ActionType.LIFT
        ).astype(self.action_spec()['action_type'].dtype)
        actions.append(lift_action)
      else:
        actions = [dict(action)] * (self._num_steps + 1)

    return actions

  def step(self, action: Mapping[str, np.ndarray]) -> dm_env.TimeStep:
    """Takes a step in the environment."""
    actions = self._process_action(action)
    total_reward = 0.0
    step_type = dm_env.StepType.MID
    discount = None
    observation = None
    for action in actions:
      step_type, reward, discount, observation = self._env.step(action)
      self._env_steps += 1
      if reward is not None:
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
