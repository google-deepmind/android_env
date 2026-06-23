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

import timeit
from absl import flags
from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import pixel_fns
from dm_env import specs
import numpy as np

# Benchmarks take ~2 minutes to run, so they are disabled by default.
# Run with --test_arg=--run_benchmarks to enable.
_RUN_BENCHMARKS = flags.DEFINE_bool(
    'run_benchmarks', False, 'Whether to run microbenchmarks.'
)


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


class PixelFnsBenchmark(absltest.TestCase):
  """Microbenchmarks for pixel functions.

  These are implemented as unit tests but are skipped by default because they
  are slow. They are useful for verifying optimizations.

  NOTE: We use inlined strings with `timeit.Timer` instead of callables
  (lambdas) to avoid Python function call overhead in the measurement loop.
  For very fast operations like `transpose_pixels` (view) which take ~1 us,
  the ~100ns lambda overhead would introduce a significant (~10%) measurement
  error.
  """

  def setUp(self):
    super().setUp()
    if not _RUN_BENCHMARKS.value:
      self.skipTest('Benchmark disabled. Run with --test_arg=--run_benchmarks')

  def test_touch_position_to_pixel_position(self):
    setup = (
        'from android_env.components import pixel_fns; import numpy as np; '
        'touch_pos = np.array([0.5, 0.5]); width_height = [1080, 1920]'
    )
    stmt = 'pixel_fns.touch_position_to_pixel_position(touch_pos, width_height)'
    t = timeit.Timer(stmt, setup=setup)
    number = 100000
    res = t.timeit(number=number)
    print(
        f'BenchmarkTouchPositionToPixelPosition {number}'
        f' {res / number * 1e9:.0f} ns/op'
    )

  def test_transpose_pixels(self):
    for size in [(320, 480), (1080, 1920)]:
      setup = (
          'from android_env.components import pixel_fns; import numpy as np;'
          f' img = np.zeros(({size[1]}, {size[0]}, 3), dtype=np.uint8)'
      )
      stmt = 'pixel_fns.transpose_pixels(img)'
      t = timeit.Timer(stmt, setup=setup)
      number = 1000
      res = t.timeit(number=number)
      name_view = f'TransposePixels_{size[0]}x{size[1]}_view'
      print(f'Benchmark{name_view} {number} {res / number * 1e9:.0f} ns/op')

      stmt_copy = 'pixel_fns.transpose_pixels(img).copy()'
      t_copy = timeit.Timer(stmt_copy, setup=setup)
      res_copy = t_copy.timeit(number=number)
      name_copy = f'TransposePixels_{size[0]}x{size[1]}_copy'
      print(
          f'Benchmark{name_copy} {number} {res_copy / number * 1e9:.0f} ns/op'
      )

  def test_orient_pixels(self):
    for size in [(320, 480), (1080, 1920)]:
      for orientation in [1, 2, 3]:
        setup = (
            'from android_env.components import pixel_fns; import numpy as np; '
            f'img = np.zeros(({size[1]}, {size[0]}, 3), dtype=np.uint8); '
            f'orientation = {orientation}'
        )
        stmt = 'pixel_fns.orient_pixels(img, orientation)'
        t = timeit.Timer(stmt, setup=setup)
        number = 1000
        res = t.timeit(number=number)
        name_view = f'OrientPixels_{size[0]}x{size[1]}_rot{orientation}_view'
        print(f'Benchmark{name_view} {number} {res / number * 1e9:.0f} ns/op')

        stmt_copy = 'pixel_fns.orient_pixels(img, orientation).copy()'
        t_copy = timeit.Timer(stmt_copy, setup=setup)
        res_copy = t_copy.timeit(number=number)
        name_copy = f'OrientPixels_{size[0]}x{size[1]}_rot{orientation}_copy'
        print(
            f'Benchmark{name_copy} {number} {res_copy / number * 1e9:.0f} ns/op'
        )

  def test_convert_int_to_float(self):
    for size in [(320, 480), (1080, 1920)]:
      setup = (
          'from android_env.components import pixel_fns\nimport numpy as'
          ' np\nfrom dm_env import specs\nspec ='
          f' specs.BoundedArray(shape=({size[1]}, {size[0]}, 3),'
          ' dtype=np.uint8, minimum=0, maximum=255)\ndata ='
          f' np.random.randint(0, 255, size=({size[1]}, {size[0]}, 3),'
          ' dtype=np.uint8)\n'
      )
      stmt = 'pixel_fns.convert_int_to_float(data, spec)'
      t = timeit.Timer(stmt, setup=setup)
      number = 100
      res = t.timeit(number=number)
      name = f'ConvertIntToFloat_{size[0]}x{size[1]}_BoundedArray'
      print(f'Benchmark{name} {number} {res / number * 1e9:.0f} ns/op')


if __name__ == '__main__':
  absltest.main()
