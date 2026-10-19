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

"""Frame processing functions for AndroidEnv Playground."""

import io
from android_env.playground import coordinates
import numpy as np
from PIL import Image


def process_frame(
    pixels: np.ndarray,
    orientation: int,
) -> bytes:
  """Processes raw emulator pixels (rotates, crops) to JPEG bytes."""
  # Rotate pixels if needed based on orientation
  if orientation == 1:  # LANDSCAPE_90
    pixels = np.rot90(pixels, k=1)
  elif orientation == 3:  # LANDSCAPE_270
    pixels = np.rot90(pixels, k=3)
  elif orientation == 2:  # PORTRAIT_180
    pixels = np.rot90(pixels, k=2)

  # If landscape, crop to 16:9 aspect ratio
  if orientation in {1, 3}:
    h_v, w_v = pixels.shape[:2]
    crop_y_start, crop_y_end, crop_x_start, crop_x_end = (
        coordinates.get_crop_metrics((h_v, w_v))
    )
    pixels = pixels[crop_y_start:crop_y_end, crop_x_start:crop_x_end]

  img = Image.fromarray(pixels)
  output = io.BytesIO()
  img.save(output, format='JPEG')
  return output.getvalue()
