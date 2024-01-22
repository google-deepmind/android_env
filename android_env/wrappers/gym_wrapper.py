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

"""Wraps the AndroidEnv to expose an OpenAI Gym interface."""

from typing import Any

from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import gym
from gym import spaces
import numpy as np


class GymInterfaceWrapper(gym.Env):
  """AndroidEnv with OpenAI Gym interface."""

  def __init__(self, env: dm_env.Environment):
    self._env = env
    self.spec = None
    self.action_space = self._spec_to_space(self._env.action_spec())
    self.observation_space = self._spec_to_space(self._env.observation_spec())
    self.metadata = {'render.modes': ['rgb_array']}
    self._latest_observation = None

  def _spec_to_space(self, spec: specs.Array) -> spaces.Space:
    """Converts dm_env specs to OpenAI Gym spaces."""

    if isinstance(spec, list):
      return spaces.Tuple([self._spec_to_space(s) for s in spec])

    if isinstance(spec, dict):
      return spaces.Dict(
          {name: self._spec_to_space(s) for name, s in spec.items()}
      )

    if isinstance(spec, specs.DiscreteArray):
      return spaces.Box(
          shape=(),
          dtype=spec.dtype,
          low=0,
          high=spec.num_values-1)

    if isinstance(spec, specs.BoundedArray):
      return spaces.Box(
          shape=spec.shape,
          dtype=spec.dtype,
          low=spec.minimum,
          high=spec.maximum)

    if isinstance(spec, specs.Array):
      if spec.dtype == np.uint8:
        low = 0
        high = 255
      else:
        low = -np.inf
        high = np.inf
      return spaces.Box(shape=spec.shape, dtype=spec.dtype, low=low, high=high)

    raise ValueError('Unknown type for specs: {}'.format(spec))

  def render(self, mode='rgb_array'):
    """Renders the environment."""
    if mode == 'rgb_array':
      if self._latest_observation is None:
        return

      return self._latest_observation['pixels']
    else:
      raise ValueError('Only supported render mode is rgb_array.')

  def reset(self) -> np.ndarray:
    self._latest_observation = None
    timestep = self._env.reset()
    return timestep.observation

  def step(self, action: dict[str, int]) -> tuple[Any, ...]:
    """Take a step in the base environment."""
    timestep = self._env.step(action)
    observation = timestep.observation
    self._latest_observation = observation
    reward = timestep.reward
    done = timestep.step_type == dm_env.StepType.LAST
    info = {'discount': timestep.discount}
    return observation, reward, done, info
