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

"""Wraps the AndroidEnv environment to provide swipe actions."""

from collections.abc import Mapping, Sequence
from typing import Any, cast

from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import numpy as np


class SwipeActionWrapper(base_wrapper.BaseWrapper):
  """AndroidEnv with swipe actions.

  Converts a single swipe action (start position, end position) into a sequence
  of TOUCH steps with linearly interpolated positions, followed by a LIFT at the
  end position.
  """

  def __init__(
      self,
      env: env_interface.AndroidEnvInterface,
      *,
      num_steps: int = 10,
  ) -> None:
    """Initializes the instance.

    Args:
      env: The underlying environment.
      num_steps: The number of TOUCH steps used to interpolate between the start
        and end positions.
    """
    super().__init__(env)
    self._assert_base_env()
    if num_steps < 1:
      raise ValueError(f'num_steps must be >= 1, got {num_steps}.')
    self._num_steps = num_steps
    self._env_steps = 0
    self._touch_position_spec = cast(
        specs.BoundedArray, self._env.action_spec()['touch_position']
    )
    self._action_type_dtype = self._env.action_spec()['action_type'].dtype

  def _assert_base_env(self) -> None:
    parent_action_spec = self._env.action_spec()
    assert len(parent_action_spec) == 2
    assert not parent_action_spec['action_type'].shape
    assert parent_action_spec['touch_position'].shape == (2,)

  def stats(self) -> dict[str, Any]:
    """Returns a dictionary of metrics logged by the environment."""
    logs = self._env.stats()
    logs.update({'env_steps': self._env_steps})
    return logs

  def _process_action(
      self, action: Mapping[str, np.ndarray]
  ) -> Sequence[dict[str, np.ndarray]]:
    start = np.asarray(action['start_position'], dtype=np.float32)
    end = np.asarray(action['end_position'], dtype=np.float32)
    touch_dtype = self._touch_position_spec.dtype

    alphas = np.linspace(0.0, 1.0, self._num_steps, dtype=np.float32)
    positions = start + alphas[:, np.newaxis] * (end - start)

    actions = []
    for position in positions:
      actions.append({
          'action_type': np.array(action_type.ActionType.TOUCH).astype(
              self._action_type_dtype
          ),
          'touch_position': position.astype(touch_dtype),
      })

    actions.append({
        'action_type': np.array(action_type.ActionType.LIFT).astype(
            self._action_type_dtype
        ),
        'touch_position': end.astype(touch_dtype),
    })
    return actions

  def step(self, action: Mapping[str, np.ndarray]) -> dm_env.TimeStep:
    """Takes a step in the environment."""
    actions = self._process_action(action)
    total_reward = 0.0
    step_type = dm_env.StepType.MID
    discount = None
    observation = None
    for sub_action in actions:
      step_type, reward, discount, observation = self._env.step(sub_action)
      self._env_steps += 1
      if reward is not None:
        total_reward += reward
      if step_type == dm_env.StepType.LAST:
        return dm_env.TimeStep(
            step_type=step_type,
            reward=total_reward,
            discount=discount,
            observation=observation,
        )
    return dm_env.TimeStep(
        step_type=step_type,
        reward=total_reward,
        discount=discount,
        observation=observation,
    )

  def action_spec(self) -> dict[str, specs.Array]:
    touch_spec = self._touch_position_spec
    return {
        'start_position': specs.BoundedArray(
            shape=(2,),
            dtype=touch_spec.dtype,
            minimum=touch_spec.minimum,
            maximum=touch_spec.maximum,
            name='start_position',
        ),
        'end_position': specs.BoundedArray(
            shape=(2,),
            dtype=touch_spec.dtype,
            minimum=touch_spec.minimum,
            maximum=touch_spec.maximum,
            name='end_position',
        ),
    }
