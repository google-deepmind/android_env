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

"""Wraps the AndroidEnv environment to rescale the observations."""

from collections.abc import Sequence

from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import numpy as np
from PIL import Image


# Taken from https://pillow.readthedocs.io/en/3.2.x/reference/Image.html#PIL.Image.Image.convert
#
# This array maps an RGB image to a grayscale image using the ITU-R 709
# specification which is good for computer displays and HDTV.
RGB_TO_GRAYSCALE_COEFFICIENTS = [0.2126, 0.7152, 0.0722]


class ImageRescaleWrapper(base_wrapper.BaseWrapper):
  """AndroidEnv with rescaled observations."""

  def __init__(
      self,
      env: dm_env.Environment,
      zoom_factors: Sequence[float] | None = (0.5, 0.5),
      grayscale: bool = False,
  ):
    super().__init__(env)
    assert 'pixels' in self._env.observation_spec()
    assert self._env.observation_spec()['pixels'].shape[-1] in [1, 3], (
        'Number of pixel channels should be 1 or 3.')
    self._grayscale = grayscale
    if zoom_factors is None:
      zoom_factors = (1.0, 1.0)
    # We only zoom the width and height of each layer, and we explicitly do not
    # want to zoom the number of channels so we just multiply it by 1.0.
    self._zoom_factors = tuple(zoom_factors) + (1.0,)

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    observation = timestep.observation
    processed_observation = observation.copy()
    processed_observation['pixels'] = self._process_pixels(
        observation['pixels'])
    return timestep._replace(observation=processed_observation)

  def _process_pixels(self, raw_observation: np.ndarray) -> np.ndarray:
    # We expect `raw_observation` to have shape (W, H, 3) - 3 for RGB
    new_shape = np.array(
        self._zoom_factors[0:2] * np.array(raw_observation.shape[0:2]),
        dtype=np.int32)[::-1]
    if self._grayscale:
      # When self._grayscale == True, we squash the RGB into a single layer
      image = np.dot(raw_observation, RGB_TO_GRAYSCALE_COEFFICIENTS)
    else:
      image = raw_observation
    return self._resize_image_array(image, new_shape)

  def _resize_image_array(
      self, grayscale_or_rbg_array: np.ndarray, new_shape: np.ndarray
  ) -> np.ndarray:
    """Resize color or grayscale/action_layer array to new_shape."""
    assert new_shape.ndim == 1
    assert len(new_shape) == 2
    resized_array = np.array(
        Image.fromarray(grayscale_or_rbg_array.astype('uint8')).resize(
            tuple(new_shape)
        )
    )
    if resized_array.ndim == 2:
      return np.expand_dims(resized_array, axis=-1)
    return resized_array

  def reset(self) -> dm_env.TimeStep:
    timestep = self._env.reset()
    return self._process_timestep(timestep)

  def step(self, action) -> dm_env.TimeStep:
    timestep = self._env.step(action)
    return self._process_timestep(timestep)

  def observation_spec(self) -> dict[str, specs.Array]:
    parent_spec = self._env.observation_spec().copy()
    out_shape = np.multiply(parent_spec['pixels'].shape,
                            self._zoom_factors).astype(np.int32)
    if self._grayscale:
      # In grayscale mode we want the output shape to be [W, H, 1]
      out_shape[-1] = 1
    parent_spec['pixels'] = specs.BoundedArray(
        shape=out_shape,
        dtype=parent_spec['pixels'].dtype,
        name=parent_spec['pixels'].name,
        minimum=parent_spec['pixels'].minimum,
        maximum=parent_spec['pixels'].maximum)
    return parent_spec
