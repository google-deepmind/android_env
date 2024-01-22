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

"""Wraps the AndroidEnv environment to make its interface flat."""

from typing import Any

from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import numpy as np

RGB_CHANNELS = (0, 1, 2)


def _extract_screen_pixels(obs: np.ndarray):
  """Get only screen pixels by removing previous action layer."""
  is_grayscale_image = obs.shape[-1] == 2
  if is_grayscale_image:
    return np.expand_dims(obs[..., 0], -1)
  return obs[..., RGB_CHANNELS]


def _get_no_action_observation_spec(obs_spec: specs.BoundedArray):
  """Create an observation spec without the action layer."""
  shape = np.array(obs_spec.shape)
  shape[2] -= 1
  minimum = obs_spec.minimum
  maximum = obs_spec.maximum
  is_scalar = lambda x: np.isscalar(x) or np.ndim(x) == 0
  if not is_scalar(minimum):
    minimum = _extract_screen_pixels(minimum)
  if not is_scalar(maximum):
    maximum = _extract_screen_pixels(maximum)
  return obs_spec.replace(shape=shape, minimum=minimum, maximum=maximum)


class FlatInterfaceWrapper(base_wrapper.BaseWrapper):
  """Simple interface for AndroidEnv.

  Removes the structure from observations and actions, keeping only the pixel
  observations. Also exposes action as an int32 scalar, making it easier to use
  with conventional discrete agents. This wrapper expects a discretized action
  space.
  """

  def __init__(self,
               env: dm_env.Environment,
               flat_actions: bool = True,
               flat_observations: bool = True,
               keep_action_layer: bool = True):
    super().__init__(env)
    self._flat_actions = flat_actions
    self._flat_observations = flat_observations
    self._keep_action_layer = keep_action_layer
    self._action_name = list(self._env.action_spec())[0]
    self._assert_base_env()

  def _assert_base_env(self):
    base_action_spec = self._env.action_spec()
    assert len(base_action_spec) == 1, self._env.action_spec()
    assert isinstance(base_action_spec, dict)
    assert isinstance(base_action_spec[self._action_name], specs.BoundedArray)

  def _process_action(self, action: int | np.ndarray | dict[str, Any]):
    if self._flat_actions:
      return {self._action_name: action}
    else:
      return action

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    if self._flat_observations:
      step_type, reward, discount, observation = timestep
      # Keep only the pixels.
      pixels = observation['pixels']
      pixels = pixels if self._keep_action_layer else _extract_screen_pixels(
          pixels)
      return dm_env.TimeStep(
          step_type=step_type,
          reward=reward,
          discount=discount,
          observation=pixels)
    else:
      return timestep

  def reset(self) -> dm_env.TimeStep:
    timestep = self._env.reset()
    return self._process_timestep(timestep)

  def step(self, action: int) -> dm_env.TimeStep:
    timestep = self._env.step(self._process_action(action))
    return self._process_timestep(timestep)

  def observation_spec(self) -> specs.Array | dict[str, specs.Array]:  # pytype: disable=signature-mismatch  # overriding-return-type-checks
    if self._flat_observations:
      pixels_spec = self._env.observation_spec()['pixels']
      if not self._keep_action_layer:
        return _get_no_action_observation_spec(pixels_spec)
      return pixels_spec
    else:
      return self._env.observation_spec()

  def action_spec(self) -> specs.BoundedArray | dict[str, specs.Array]:  # pytype: disable=signature-mismatch  # overriding-return-type-checks
    if self._flat_actions:
      return self._env.action_spec()[self._action_name]
    else:
      return self._env.action_spec()
