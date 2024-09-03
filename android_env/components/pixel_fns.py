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

"""Utils for AndroidEnv."""

from collections.abc import Sequence

from dm_env import specs
import numpy as np


def touch_position_to_pixel_position(
    touch_position: np.ndarray,
    width_height: Sequence[int],
) -> tuple[int, int]:
  """Maps touch position in [0,1] to the corresponding pixel on the screen."""
  touch_pixels = (touch_position * width_height).astype(np.int32)
  cap_idx = lambda v, idx_len: min(v, idx_len - 1)
  return tuple(map(cap_idx, touch_pixels, width_height))


def transpose_pixels(frame: np.ndarray) -> np.ndarray:
  """Converts image from shape (H, W, C) to (W, H, C) and vice-versa."""
  return np.transpose(frame, axes=(1, 0, 2))


def orient_pixels(frame: np.ndarray, orientation: int) -> np.ndarray:
  """Rotates screen pixels according to the given orientation."""

  match orientation:
    case 0:  # PORTRAIT_90
      return frame
    case 1:  # LANDSCAPE_90
      return np.rot90(frame, k=3, axes=(0, 1))
    case 2:  # PORTRAIT_180
      return np.rot90(frame, k=2, axes=(0, 1))
    case 3:  # LANDSCAPE_270
      return np.rot90(frame, k=1, axes=(0, 1))
    case _:
      raise ValueError(
          'Orientation must be an integer in [0, 3] but is %r' % orientation
      )


def convert_int_to_float(data: np.ndarray, data_spec: specs.Array):
  """Converts an array of int values to floats between 0 and 1."""

  if not np.issubdtype(data.dtype, np.integer):
    raise TypeError(f'{data.dtype} is not an integer type')
  if isinstance(data_spec, specs.BoundedArray):
    value_min = data_spec.minimum
    value_max = data_spec.maximum
  else:
    # We use the int type to figure out the boundaries.
    iinfo = np.iinfo(data_spec.dtype)
    value_min = iinfo.min
    value_max = iinfo.max
  return np.float32(1.0 * (data - value_min) / (value_max - value_min))
