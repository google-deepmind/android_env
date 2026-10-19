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

"""Tests for frame processing and image transformation in AndroidEnv Playground."""

import io
from absl.testing import absltest
from android_env.playground import frame_processing
import numpy as np
from PIL import Image


class FrameProcessingTest(absltest.TestCase):

  def test_process_frame_portrait(self):
    pixels = np.zeros((1280, 720, 3), dtype=np.uint8)
    pixels[:, :, 0] = 255  # Red

    jpeg_bytes = frame_processing.process_frame(pixels, 0)
    img = Image.open(io.BytesIO(jpeg_bytes))
    self.assertEqual(img.size, (720, 1280))
    data = np.array(img)
    np.testing.assert_allclose(data[10, 10], [255, 0, 0], atol=5)

  def test_process_frame_landscape_crop_and_rotate(self):
    pixels = np.zeros((2209, 1080, 3), dtype=np.uint8)
    pixels[0:144, :, 2] = 255  # Blue
    pixels[144:2064, :, 1] = 255  # Green
    pixels[2064:2209, :, 2] = 255  # Blue

    jpeg_bytes = frame_processing.process_frame(pixels, 1)
    img = Image.open(io.BytesIO(jpeg_bytes))
    self.assertEqual(img.size, (1920, 1080))

    data = np.array(img)
    np.testing.assert_allclose(data[10, 10], [0, 255, 0], atol=5)
    np.testing.assert_allclose(data[180, 320], [0, 255, 0], atol=5)
    self.assertTrue(np.all(data[:, :, 2] < 50))

  def test_process_frame_portrait_180(self):
    pixels = np.zeros((1280, 720, 3), dtype=np.uint8)
    pixels[:, :, 1] = 255  # Green

    jpeg_bytes = frame_processing.process_frame(pixels, 2)
    img = Image.open(io.BytesIO(jpeg_bytes))
    self.assertEqual(img.size, (720, 1280))

  def test_process_frame_landscape_270(self):
    pixels = np.zeros((2209, 1080, 3), dtype=np.uint8)
    pixels[144:2064, :, 0] = 255  # Red

    jpeg_bytes = frame_processing.process_frame(pixels, 3)
    img = Image.open(io.BytesIO(jpeg_bytes))
    self.assertEqual(img.size, (1920, 1080))


if __name__ == '__main__':
  absltest.main()
