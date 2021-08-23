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

"""Tests for android_env.components.utils."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import utils
from android_env.proto import task_pb2
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
    self.assertEqual(utils.touch_position_to_pixel_position(
        np.array(touch_pos), width_height), pixel_pos)

  def test_transpose_pixels(self):
    image = np.reshape(np.array(range(12)), (3, 2, 2))
    expected = [[[0, 1], [4, 5], [8, 9]], [[2, 3], [6, 7], [10, 11]]]
    self.assertEqual(utils.transpose_pixels(image).shape, (2, 3, 2))
    self.assertTrue((utils.transpose_pixels(image) == expected).all())

  def test_orient_pixels(self):
    image = np.reshape(np.array(range(12)), (3, 2, 2))

    expected_90 = [[[8, 9], [4, 5], [0, 1]], [[10, 11], [6, 7], [2, 3]]]
    rot_90 = task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_90
    rotated = utils.orient_pixels(image, rot_90)
    self.assertEqual(rotated.shape, (2, 3, 2))
    self.assertTrue((rotated == expected_90).all())

    expected_180 = [[[10, 11], [8, 9]], [[6, 7], [4, 5]], [[2, 3], [0, 1]]]
    rot_180 = task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_180
    rotated = utils.orient_pixels(image, rot_180)
    self.assertEqual(rotated.shape, (3, 2, 2))
    self.assertTrue((rotated == expected_180).all())

    expected_270 = [[[2, 3], [6, 7], [10, 11]], [[0, 1], [4, 5], [8, 9]]]
    rot_270 = task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_270
    rotated = utils.orient_pixels(image, rot_270)
    self.assertEqual(rotated.shape, (2, 3, 2))
    self.assertTrue((rotated == expected_270).all())

    rot_0 = task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_0
    rotated = utils.orient_pixels(image, rot_0)
    self.assertEqual(rotated.shape, (3, 2, 2))
    self.assertTrue((rotated == image).all())

if __name__ == '__main__':
  absltest.main()
