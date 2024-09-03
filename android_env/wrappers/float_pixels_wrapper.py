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

"""Converts pixel observation to from int to float32 between 0.0 and 1.0."""

from android_env.components import pixel_fns
from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import numpy as np


class FloatPixelsWrapper(base_wrapper.BaseWrapper):
  """Wraps AndroidEnv for Panultimate agent."""

  def __init__(self, env: dm_env.Environment):
    super().__init__(env)
    self._input_spec = self._env.observation_spec()['pixels']
    self._should_convert_int_to_float = np.issubdtype(self._input_spec.dtype,
                                                      np.integer)

  def _process_observation(
      self, observation: dict[str, np.ndarray]
  ) -> dict[str, np.ndarray]:
    if self._should_convert_int_to_float:
      float_pixels = pixel_fns.convert_int_to_float(
          observation['pixels'], self._input_spec
      )
      observation['pixels'] = float_pixels
    return observation

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    step_type, reward, discount, observation = timestep
    return dm_env.TimeStep(
        step_type=step_type,
        reward=reward,
        discount=discount,
        observation=self._process_observation(observation))

  def reset(self) -> dm_env.TimeStep:
    return self._process_timestep(self._env.reset())

  def step(self, action: dict[str, np.ndarray]) -> dm_env.TimeStep:
    return self._process_timestep(self._env.step(action))

  def observation_spec(self) -> dict[str, specs.Array]:
    if self._should_convert_int_to_float:
      observation_spec = self._env.observation_spec()
      observation_spec['pixels'] = specs.BoundedArray(
          shape=self._env.observation_spec()['pixels'].shape,
          dtype=np.float32,
          minimum=0.0,
          maximum=1.0,
          name=self._env.observation_spec()['pixels'].name)
      return observation_spec
    return self._env.observation_spec()
