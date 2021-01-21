"""Tests for android_env.components.utils."""

import os

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import utils
from android_env.proto import task_pb2
from dm_env import specs
import ml_collections as collections
import numpy as np


class UtilsTest(parameterized.TestCase):

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

  def test_instantiate_class(self):
    # Instantiate an arbitrary class by name and verify that it's not None.
    array_spec = utils.instantiate_class(
        'dm_env.specs.Array', shape=(1, 2, 3), dtype=np.uint16)
    self.assertIsNotNone(array_spec)
    # Also verify that it produced what we expect.
    self.assertEqual(array_spec, specs.Array(shape=(1, 2, 3), dtype=np.uint16))

  def test_flatten_dict_empty(self):
    self.assertEqual(utils.flatten_dict({}), {})

  def test_flatten_dict_already_flat(self):
    d = {'hello': 123, 'world': 'foo'}
    self.assertEqual(utils.flatten_dict(d), d)

  def test_flatten_dict_one_level(self):
    self.assertEqual(
        utils.flatten_dict({
            'hello': {
                'world': 123
            },
            'dont_touch_this': 456
        }), {
            'hello.world': 123,
            'dont_touch_this': 456
        })

  def test_flatten_dict_two_levels(self):
    self.assertEqual(
        utils.flatten_dict({
            'hello': {
                'world': {
                    'foo': 123,
                    'bar': 789
                },
                'korg': 'triton'
            },
            'dont_touch_this': 456
        }), {
            'hello.world.foo': 123,
            'hello.world.bar': 789,
            'hello.korg': 'triton',
            'dont_touch_this': 456
        })

  def test_get_class_default_params(self):

    class TestClass():

      def __init__(self, arg0, arg1='arg1', arg2=324, arg3=None, **kwargs):
        pass

    kwargs = utils.get_class_default_params(TestClass)
    self.assertEqual({'arg1': 'arg1', 'arg2': 324, 'arg3': None}, kwargs)

  def test_merge_settings(self):
    config = collections.ConfigDict({
        'int_arg': 1,
        'bool_arg': True,
        'tuple_arg': (3, 3),
        'float_arg': 2.3,
        'dict_arg': {
            'a': 'x',
            'b': (2, 3),
            'c': 'foo'
        },
        'list_arg': [2, 3, 4],
        'nested_tuple_arg': ((2, 3), (4, 5, 6)),
        'nested_list_arg': [[2, 3], [4, 5, 6]],
        'extra_nested_list_arg': [[2, 2], [2]],
        'extra_arg': 'extra',
    })
    # Settings is expected to be a flat dictionary of strings.
    settings = {
        'int_arg': '3',
        'bool_arg': 'false',
        'tuple_arg.1': '3',
        'tuple_arg.2': '4',
        'float_arg': '3.4',
        'dict_arg.b.1': '5',
        'dict_arg.a': 'y',
        'list_arg.1': '5',
        'list_arg.2': '6',
        'nested_tuple_arg.1.1': '7.3',
        'nested_tuple_arg.1.2': '8',
        'nested_tuple_arg.1.3': '9',
        'nested_tuple_arg.2.1': '1',
        'nested_tuple_arg.2.2': '2',
        'nested_list_arg.1.1': '1',
        'nested_list_arg.1.2': '1',
        'nested_list_arg.1.3': '1',
        'nested_list_arg.2.1': '1',
        'nested_list_arg.2.2': '1',
    }
    kwargs = utils.merge_settings(config, settings)
    expected = {
        'int_arg': 3,
        'bool_arg': False,
        'tuple_arg': [3, 4],
        'float_arg': 3.4,
        'dict_arg': {
            'a': 'y',
            'b': [5,],
            'c': 'foo',
        },
        'list_arg': [5, 6],
        'nested_tuple_arg': [[7.3, 8, 9], [1, 2]],
        'nested_list_arg': [[1, 1, 1], [1, 1]],
        'extra_nested_list_arg': [[2, 2], [2]],
        'extra_arg': 'extra',
    }
    for k, v in kwargs.items():
      self.assertEqual(expected[k], v)
    self.assertEqual(expected, kwargs)

  def test_expand_vars(self):
    os.environ['VAR1'] = 'value1'
    dictionary = {
        'not_expanded1': 'VAR1',
        'not_expanded2': 100,
        'not_expanded3': ['$VAR1', '${VAR1}'],
        'not_expanded4': '${ENV_VAR_THAT_DOES_NOT_EXIST}',
        'not_expanded5': '${ENV_VAR_THAT_DOES_NOT_EXIST:=default_value}',
        'expanded1': '$VAR1',
        'expanded2': '${VAR1}',
        'expanded3': 'text$VAR1/text',
        'expanded4': 'text${VAR1}moretext',
        'expanded5': 'text${VAR1}moretext$VAR1',
        '${VAR1}notexpandedinkeys': 'foo',
        'nested_dict': {
            'expanded': '$VAR1',
            'not_expanded': 'VAR1',
            'nested_nested_dict': {
                'expanded': '$VAR1'
            },
        },
    }
    output = utils.expand_vars(dictionary)
    expected_output = {
        'not_expanded1': 'VAR1',
        'not_expanded2': 100,
        'not_expanded3': ['$VAR1', '${VAR1}'],
        'not_expanded4': '${ENV_VAR_THAT_DOES_NOT_EXIST}',
        'not_expanded5': '${ENV_VAR_THAT_DOES_NOT_EXIST:=default_value}',
        'expanded1': 'value1',
        'expanded2': 'value1',
        'expanded3': 'textvalue1/text',
        'expanded4': 'textvalue1moretext',
        'expanded5': 'textvalue1moretextvalue1',
        '${VAR1}notexpandedinkeys': 'foo',
        'nested_dict': {
            'expanded': 'value1',
            'not_expanded': 'VAR1',
            'nested_nested_dict': {
                'expanded': 'value1'
            },
        },
    }
    self.assertEqual(expected_output, output)

  def test_generate_empty_from_spec_dict(self):
    spec = {
        'array':
            specs.Array(shape=(3, 4), dtype=np.uint8),
        'bounded_array':
            specs.BoundedArray(
                shape=(2,),
                dtype=np.float64,
                minimum=[0.0, 0.0],
                maximum=[1.0, 1.0],
                name='bounded_array'),
        'discrete_array':
            specs.DiscreteArray(3, np.int64),
    }
    empty_obs = utils.get_empty_dict_from_spec(spec)
    self.assertLen(empty_obs, 3)
    np.testing.assert_equal(empty_obs['array'], np.zeros((3, 4), np.uint8))
    np.testing.assert_equal(empty_obs['bounded_array'],
                            np.zeros((2,), np.float64))
    np.testing.assert_equal(empty_obs['discrete_array'], np.zeros((), np.int64))

  def test_convert_int_to_float_bounded_array(self):
    spec = specs.BoundedArray(
        shape=(4,),
        dtype=np.int32,
        minimum=[0, 1, 10, -2],
        maximum=[5, 5, 20, 2],
        name='bounded_array')
    data = np.array([2, 2, 10, 0], dtype=np.int32)
    float_data = utils.convert_int_to_float(data, spec, np.float64)
    np.testing.assert_equal(
        np.array([2. / 5., 1. / 4., 0., 0.5], dtype=np.float64), float_data)

  def test_convert_int_to_float_bounded_array_broadcast(self):
    spec = specs.BoundedArray(
        shape=(3,), dtype=np.int16, minimum=2, maximum=4, name='bounded_array')
    data = np.array([2, 3, 4], dtype=np.int16)
    float_data = utils.convert_int_to_float(data, spec, np.float32)
    np.testing.assert_equal(
        np.array([0.0, 0.5, 1.0], dtype=np.float32), float_data)

  def test_convert_int_to_float_no_bounds(self):
    spec = specs.Array(
        shape=(3,),
        dtype=np.int8,  # int8 implies min=-128, max=127
        name='bounded_array')
    data = np.array([-128, 0, 127], dtype=np.int16)
    float_data = utils.convert_int_to_float(data, spec, np.float32)
    np.testing.assert_equal(
        np.array([0.0, 128. / 255., 1.0], dtype=np.float32), float_data)

  def test_maybe_discrete_not_bounded(self):
    spec = specs.Array(shape=(1,), dtype=np.int8, name='array')
    self.assertEqual(utils.maybe_convert_to_discrete(spec), spec)

  def test_maybe_discrete_wrong_shape(self):
    spec = specs.BoundedArray(
        shape=(3,),
        dtype=np.int32,
        minimum=np.zeros(shape=(), dtype=np.int32),
        maximum=np.ones(shape=(), dtype=np.int32),
        name='bounded_array')
    self.assertEqual(utils.maybe_convert_to_discrete(spec), spec)

  def test_maybe_discrete_not_zero(self):
    spec = specs.BoundedArray(
        shape=(1,),
        dtype=np.int32,
        minimum=np.ones(shape=(1,), dtype=np.int32),
        maximum=np.ones(shape=(1,), dtype=np.int32),
        name='bounded_array')
    self.assertEqual(utils.maybe_convert_to_discrete(spec), spec)

  def test_maybe_discrete_float(self):
    spec = specs.BoundedArray(
        shape=(1,),
        dtype=np.float32,
        minimum=np.zeros(shape=(1,), dtype=np.float32),
        maximum=np.ones(shape=(1,), dtype=np.float32),
        name='bounded_array')
    self.assertEqual(utils.maybe_convert_to_discrete(spec), spec)

  def test_maybe_discrete_correct(self):
    spec = specs.BoundedArray(
        shape=(1,),
        dtype=np.int32,
        minimum=np.zeros(shape=(1,), dtype=np.int32),
        maximum=np.ones(shape=(1,), dtype=np.int32),
        name='bounded_array')
    self.assertIsInstance(
        utils.maybe_convert_to_discrete(spec), specs.DiscreteArray)

  def test_maybe_discrete_correct_scalar(self):
    spec = specs.BoundedArray(
        shape=(),
        dtype=np.int32,
        minimum=np.zeros(shape=(), dtype=np.int32),
        maximum=np.ones(shape=(), dtype=np.int32),
        name='bounded_array')
    self.assertIsInstance(
        utils.maybe_convert_to_discrete(spec), specs.DiscreteArray)

  def test_maybe_convert_discrete(self):
    spec = specs.BoundedArray(
        shape=(),
        dtype=np.int32,
        minimum=np.zeros(shape=(), dtype=np.int32),
        maximum=np.ones(shape=(), dtype=np.int32),
        name='bounded_array')
    self.assertEqual(utils.maybe_convert_discrete(spec), spec)

  def test_maybe_convert_discrete_correct(self):
    spec = specs.DiscreteArray(num_values=5, name='discrete_array')
    self.assertEqual(utils.maybe_convert_discrete(spec).shape, (1,))

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


if __name__ == '__main__':
  absltest.main()
