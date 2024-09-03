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

"""Tests for pixel_fns."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import pixel_fns
from dm_env import specs
import numpy as np


class UtilsTest(parameterized.TestCase):

  @parameterized.parameters(
      ([0.5, 0.5], [320, 480], (160, 240)),
      ([0.25, 0.75], [320, 480], (80, 360)),
      ([0.0, 0.0], [320, 480], (0, 0)),
      ([1.0, 1.0], [320, 480], (319, 479)),
      )
  def test_touch_position_to_pixel_position(
      self, touch_pos, width_height, pixel_pos):
    self.assertEqual(
        pixel_fns.touch_position_to_pixel_position(
            np.array(touch_pos), width_height
        ),
        pixel_pos,
    )

  def test_transpose_pixels(self):
    image = np.reshape(np.array(range(12)), (3, 2, 2))
    expected = [[[0, 1], [4, 5], [8, 9]], [[2, 3], [6, 7], [10, 11]]]
    self.assertEqual(pixel_fns.transpose_pixels(image).shape, (2, 3, 2))
    self.assertTrue((pixel_fns.transpose_pixels(image) == expected).all())

  def test_orient_pixels(self):
    image = np.reshape(np.array(range(12)), (3, 2, 2))

    expected_90 = [[[8, 9], [4, 5], [0, 1]], [[10, 11], [6, 7], [2, 3]]]
    rot_90 = 1  # LANDSCAPE_90
    rotated = pixel_fns.orient_pixels(image, rot_90)
    self.assertEqual(rotated.shape, (2, 3, 2))
    self.assertTrue((rotated == expected_90).all())

    expected_180 = [[[10, 11], [8, 9]], [[6, 7], [4, 5]], [[2, 3], [0, 1]]]
    rot_180 = 2  # PORTRAIT_180
    rotated = pixel_fns.orient_pixels(image, rot_180)
    self.assertEqual(rotated.shape, (3, 2, 2))
    self.assertTrue((rotated == expected_180).all())

    expected_270 = [[[2, 3], [6, 7], [10, 11]], [[0, 1], [4, 5], [8, 9]]]
    rot_270 = 3  # LANDSCAPE_270
    rotated = pixel_fns.orient_pixels(image, rot_270)
    self.assertEqual(rotated.shape, (2, 3, 2))
    self.assertTrue((rotated == expected_270).all())

    rot_0 = 0  # PORTRAIT_0
    rotated = pixel_fns.orient_pixels(image, rot_0)
    self.assertEqual(rotated.shape, (3, 2, 2))
    self.assertTrue((rotated == image).all())

  def test_convert_int_to_float_bounded_array(self):
    spec = specs.BoundedArray(
        shape=(4,),
        dtype=np.int32,
        minimum=[0, 1, 10, -2],
        maximum=[5, 5, 20, 2],
        name='bounded_array')
    data = np.array([2, 2, 10, 0], dtype=np.int32)
    float_data = pixel_fns.convert_int_to_float(data, spec)
    np.testing.assert_equal(
        np.array([2.0 / 5.0, 1.0 / 4.0, 0.0, 0.5], dtype=np.float32), float_data
    )

  def test_convert_int_to_float_bounded_array_broadcast(self):
    spec = specs.BoundedArray(
        shape=(3,), dtype=np.int16, minimum=2, maximum=4, name='bounded_array')
    data = np.array([2, 3, 4], dtype=np.int16)
    float_data = pixel_fns.convert_int_to_float(data, spec)
    np.testing.assert_equal(
        np.array([0.0, 0.5, 1.0], dtype=np.float32), float_data)

  def test_convert_int_to_float_no_bounds(self):
    spec = specs.Array(
        shape=(3,),
        dtype=np.int8,  # int8 implies min=-128, max=127
        name='bounded_array')
    data = np.array([-128, 0, 127], dtype=np.int16)
    float_data = pixel_fns.convert_int_to_float(data, spec)
    np.testing.assert_equal(
        np.array([0.0, 128. / 255., 1.0], dtype=np.float32), float_data)


if __name__ == '__main__':
  absltest.main()
