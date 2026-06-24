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

"""Utils for AndroidEnv."""

from collections.abc import Sequence

from dm_env import specs
import numpy as np


def touch_position_to_pixel_position(
    touch_position: np.ndarray,
    width_height: Sequence[int],
) -> tuple[int, int]:
  """Maps touch position in [0,1] to the corresponding pixel on the screen."""
  # Unpack and use pure Python math to avoid NumPy overhead for small 2D array.
  # Also avoids map/lambda overhead.
  x, y = touch_position
  w, h = width_height
  return (min(int(x * w), w - 1), min(int(y * h), h - 1))


def transpose_pixels(frame: np.ndarray) -> np.ndarray:
  """Converts image from shape (H, W, C) to (W, H, C) and vice-versa."""
  return np.transpose(frame, axes=(1, 0, 2))


def orient_pixels(frame: np.ndarray, orientation: int) -> np.ndarray:
  """Rotates screen pixels according to the given orientation."""

  # We use manual slicing and swapaxes instead of np.rot90 to avoid the
  # function call and argument parsing overhead of np.rot90.
  match orientation:
    case 0:  # PORTRAIT_90
      return frame
    case 1:  # LANDSCAPE_90
      return frame.swapaxes(0, 1)[:, ::-1]
    case 2:  # PORTRAIT_180
      return frame[::-1, ::-1, :]
    case 3:  # LANDSCAPE_270
      return frame.swapaxes(0, 1)[::-1, :]
    case _:
      raise ValueError(
          'Orientation must be an integer in [0, 3] but is %r' % orientation
      )


def convert_int_to_float(
    data: np.ndarray, data_spec: specs.Array
) -> np.ndarray:
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
  # Optimize performance by:
  # 1. Performing all calculations in float32 to avoid default float64
  #    precision overhead.
  # 2. Reusing the allocated float32 array for in-place operations to
  #    minimize memory allocation.
  # 3. Using multiplication instead of division.
  span = np.float32(value_max - value_min)
  inv_span = np.float32(1.0) / span
  out = data.astype(np.float32)  # Allocate output array once
  if np.all(value_min == 0):
    # Skip subtraction if minimum is 0 (common for image data).
    out *= inv_span  # In-place multiplication is faster than division
  else:
    out -= np.float32(value_min)  # In-place subtraction
    out *= inv_span
  return out
