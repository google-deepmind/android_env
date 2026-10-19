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

"""Tests for coordinate mapping and cropping in AndroidEnv Playground."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.playground import coordinates
import numpy as np


class CoordinatesTest(parameterized.TestCase):

  @parameterized.parameters(
      ((1080, 2209), (0, 1080, 144, 2064)),
      ((720, 1280), (0, 720, 0, 1280)),
      ((768, 1024), (96, 672, 0, 1024)),
  )
  def test_get_crop_metrics(self, raw_shape, expected):
    self.assertEqual(coordinates.get_crop_metrics(raw_shape), expected)

  def test_map_client_coordinates_portrait(self):
    raw_shape = (1280, 720)
    pos = coordinates.map_client_coordinates(0.1, 0.2, 0, raw_shape)
    np.testing.assert_allclose(pos, [0.1, 0.2])

  def test_map_client_coordinates_portrait_180(self):
    raw_shape = (1280, 720)
    pos = coordinates.map_client_coordinates(0.1, 0.2, 2, raw_shape)
    np.testing.assert_allclose(pos, [0.9, 0.8])

  def test_map_client_coordinates_landscape_90_wide(self):
    raw_shape = (2209, 1080)
    pos = coordinates.map_client_coordinates(0.5, 0.5, 1, raw_shape)
    np.testing.assert_allclose(pos, [0.5, 1104.0 / 2209.0], rtol=1e-5)

  def test_map_client_coordinates_landscape_270_tall(self):
    raw_shape = (1024, 768)
    pos = coordinates.map_client_coordinates(0.5, 0.5, 3, raw_shape)
    np.testing.assert_allclose(pos, [0.5, 0.5])


if __name__ == '__main__':
  absltest.main()
