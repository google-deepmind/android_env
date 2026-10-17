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

"""Coordinate mapping functions for AndroidEnv Playground."""

import numpy as np


def get_crop_metrics(raw_shape: tuple[int, int]) -> tuple[int, int, int, int]:
  """Returns (crop_y_start, crop_y_end, crop_x_start, crop_x_end) for landscape."""
  h_v, w_v = raw_shape[:2]
  target_ar = 16.0 / 9.0
  current_ar = w_v / h_v

  if current_ar > target_ar:
    # Too wide, crop width
    crop_w = int(h_v * target_ar)
    crop_x_start = (w_v - crop_w) // 2
    crop_x_end = crop_x_start + crop_w
    return 0, h_v, crop_x_start, crop_x_end
  else:
    # Too tall (or matches), crop height
    crop_h = int(w_v / target_ar)
    crop_y_start = (h_v - crop_h) // 2
    crop_y_end = crop_y_start + crop_h
    return crop_y_start, crop_y_end, 0, w_v


def map_client_coordinates(
    x: float,
    y: float,
    orientation: int,
    raw_shape: tuple[int, int],
) -> np.ndarray:
  """Maps client-side normalized coordinates to raw emulator coordinates."""
  pos = np.array([x, y], dtype=np.float32)

  # Adjust coordinates based on cropping in landscape mode.
  if orientation in {1, 3}:
    h_rot, w_rot = raw_shape[1], raw_shape[0]
    crop_y_start, crop_y_end, crop_x_start, crop_x_end = get_crop_metrics(
        (h_rot, w_rot)
    )
    if crop_x_start > 0 or crop_x_end < w_rot:
      crop_width = crop_x_end - crop_x_start
      pos[0] = (crop_x_start + pos[0] * crop_width) / w_rot
    if crop_y_start > 0 or crop_y_end < h_rot:
      crop_height = crop_y_end - crop_y_start
      pos[1] = (crop_y_start + pos[1] * crop_height) / h_rot

  # Coordinate mapping based on orientation
  if orientation == 1:  # LANDSCAPE_90
    pos = np.array([1.0 - pos[1], pos[0]], dtype=np.float32)
  elif orientation == 3:  # LANDSCAPE_270
    pos = np.array([pos[1], 1.0 - pos[0]], dtype=np.float32)
  elif orientation == 2:  # PORTRAIT_180
    pos = np.array([1.0 - pos[0], 1.0 - pos[1]], dtype=np.float32)

  return pos
