# coding=utf-8
# Copyright 2021 DeepMind Technologies Limited.
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


from android_env.proto import task_pb2
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


def orient_pixels(
    frame: np.ndarray,
    orientation: task_pb2.AdbCall.Rotate.Orientation) -> np.ndarray:
  """Rotates screen pixels according to the given orientation."""
  if orientation == task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_90:
    frame = np.rot90(frame, k=3, axes=(0, 1))
  elif orientation == task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_180:
    frame = np.rot90(frame, k=2, axes=(0, 1))
  elif orientation == task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_270:
    frame = np.rot90(frame, k=1, axes=(0, 1))
  return frame
