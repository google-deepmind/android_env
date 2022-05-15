# coding=utf-8
# Copyright 2022 DeepMind Technologies Limited.
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

from typing import Sequence, Tuple


import numpy as np


def touch_position_to_pixel_position(
    touch_position: np.ndarray,
    width_height: Sequence[int],
) -> Tuple[int, int]:
  """Maps touch position in [0,1] to the corresponding pixel on the screen."""
  touch_pixels = (touch_position * width_height).astype(np.int32)
  cap_idx = lambda v, idx_len: min(v, idx_len - 1)
  return tuple(map(cap_idx, touch_pixels, width_height))


def transpose_pixels(frame: np.ndarray) -> np.ndarray:
  """Converts image from shape (H, W, C) to (W, H, C) and vice-versa."""
  return np.transpose(frame, axes=(1, 0, 2))


def orient_pixels(frame: np.ndarray, orientation: int) -> np.ndarray:
  """Rotates screen pixels according to the given orientation."""
  if orientation == 0:  # PORTRAIT_90
    return frame
  elif orientation == 1:  # LANDSCAPE_90
    return np.rot90(frame, k=3, axes=(0, 1))
  elif orientation == 2:  # PORTRAIT_180
    return np.rot90(frame, k=2, axes=(0, 1))
  elif orientation == 3:  # LANDSCAPE_270
    return np.rot90(frame, k=1, axes=(0, 1))
  else:
    raise ValueError(
        'Orientation must be an integer in [0, 3] but is %r' % orientation)
