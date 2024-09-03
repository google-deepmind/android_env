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

"""Extends Android observation with the latest action taken."""

from android_env.components import action_type
from android_env.components import pixel_fns
from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import numpy as np


class LastActionWrapper(base_wrapper.BaseWrapper):
  """Extends Android observations with information about the last action taken.

  The position of the last action is denoted by a single white pixel (with a
  value of 255) in a channel of all black pixels (with a value of 0).
  As this wrapper makes use of temporarily stored information about the
  last action taken, it is important to apply on the environment side rather
  than the agent side. Recommended not to apply before an ImageRescaleWrapper,
  to avoid distortion of the single pixel denoting the action position.
  """

  def __init__(self,
               env: dm_env.Environment,
               concat_to_pixels: bool = True):
    """Initializes the internal state of this wrapper.

    Args:
      env: the environment to wrap.
      concat_to_pixels: If True, will add a channel to the pixel observation.
        If False, will pass the action as an extra observation.
    """
    super().__init__(env)
    self._concat_to_pixels = concat_to_pixels
    self._screen_dimensions = self._env.observation_spec()['pixels'].shape[:2]

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    observation = timestep.observation.copy()
    processed_observation = self._process_observation(observation)
    return timestep._replace(observation=processed_observation)

  def _process_observation(
      self, observation: dict[str, np.ndarray]
  ) -> dict[str, np.ndarray]:
    """Extends observation with last_action data."""
    processed_observation = observation.copy()
    last_action_layer = self._get_last_action_layer(observation['pixels'])
    if self._concat_to_pixels:
      pixels = observation['pixels'].copy()
      processed_pixels = np.dstack((pixels, last_action_layer))
      processed_observation['pixels'] = processed_pixels
    else:
      processed_observation['last_action'] = last_action_layer
    return processed_observation

  def _get_last_action_layer(self, pixels: np.ndarray) -> np.ndarray:
    """Makes sure the rescaling doesn't distort the last_action layer."""

    last_action = self._env.raw_action
    last_action_layer = np.zeros(self._screen_dimensions, dtype=pixels.dtype)

    if ('action_type' in last_action and
        last_action['action_type'] == action_type.ActionType.TOUCH):
      touch_position = last_action['touch_position']
      x, y = pixel_fns.touch_position_to_pixel_position(
          touch_position, width_height=self._screen_dimensions[::-1]
      )
      last_action_layer[y, x] = 255

    return last_action_layer

  def reset(self) -> dm_env.TimeStep:
    timestep = self._env.reset()
    return self._process_timestep(timestep)

  def step(self, action) -> dm_env.TimeStep:
    timestep = self._env.step(action)
    return self._process_timestep(timestep)

  def observation_spec(self) -> dict[str, specs.Array]:
    parent_spec = self._env.observation_spec().copy()
    shape = parent_spec['pixels'].shape
    if self._concat_to_pixels:
      parent_spec['pixels'] = specs.BoundedArray(
          shape=(shape[0], shape[1], shape[2] + 1),
          dtype=parent_spec['pixels'].dtype,
          name=parent_spec['pixels'].name,
          minimum=parent_spec['pixels'].minimum,
          maximum=parent_spec['pixels'].maximum)
    else:
      parent_spec.update({
          'last_action':
              specs.BoundedArray(
                  shape=(shape[0], shape[1]),
                  dtype=parent_spec['pixels'].dtype,
                  name='last_action',
                  minimum=parent_spec['pixels'].minimum,
                  maximum=parent_spec['pixels'].maximum)
      })
    return parent_spec
