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

"""Tests for android_env.wrappers.discrete_action_wrapper."""

from unittest import mock

from absl.testing import absltest
from android_env import env_interface
from android_env.components import action_type as action_type_lib
from android_env.wrappers import discrete_action_wrapper
from dm_env import specs
import numpy as np

ActionType = action_type_lib.ActionType


def _make_array_spec(shape, dtype, name):
  assert len(shape) == 1
  return specs.BoundedArray(
      name=name,
      shape=shape,
      dtype=dtype,
      minimum=np.zeros(shape),
      maximum=(shape[0] - 1) * np.ones(shape),  # maximum is inclusive.
  )


def _valid_shape(action):
  assert len(action) == 2, action
  assert not action['action_type'].shape, (
      'action: %r, shape: %r' %
      (action['action_type'], action['action_type'].shape))
  assert action['touch_position'].shape == (
      2,), ('action: %r, shape: %r' %
            (action['touch_position'], action['touch_position'].shape))


def _valid_types(action, types):
  for a, t in zip(action.values(), types):
    assert a.dtype == t, '%r is not of dtype %r' % (a, t)


class DiscreteActionWrapperTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._num_action_types = 3  # Only TOUCH, LIFT, REPEAT.
    self._base_action_spec = {
        'action_type': specs.DiscreteArray(
            num_values=self._num_action_types, name='action_type'),
        'touch_position': _make_array_spec(
            shape=(2,), dtype=np.float32, name='touch_position'),
    }
    self.base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    self.base_env.action_spec.return_value = self._base_action_spec

  def test_num_actions(self):
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env, action_grid=(3, 3), redundant_actions=True)
    # 27 = 3 * 3 * 2     (H * W * self._num_action_types).
    self.assertEqual(27, wrapped_env.num_actions)

  def test_num_actions_non_redundant(self):
    # Check that with `redundant_actions`==False we get an additive term instead
    # of a multiplier in the number of actions.
    non_redudant_wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env, action_grid=(3, 3), redundant_actions=False)
    # 11 = 3 * 3 + 2     (H * W + (self._num_action_types - 1)).
    self.assertEqual(11, non_redudant_wrapped_env.num_actions)

  def test_reset(self):
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env, redundant_actions=True)
    fake_timestep = 'ts'
    self.base_env.reset.return_value = fake_timestep
    ts = wrapped_env.reset()
    self.base_env.reset.assert_called_once()
    self.assertEqual(fake_timestep, ts)

  def test_step_no_noise(self):
    height = 4
    width = 3
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env,
        action_grid=(height, width),
        noise=0.0,
        redundant_actions=True)
    self.assertEqual(height * width * self._num_action_types,
                     wrapped_env.num_actions)

    vertical_half_step = 1. / float(height) / 2.
    horizontal_half_step = 1. / float(width) / 2.

    delta = 0.0001

    # Testing the four corners with each finger position
    def get_verifier(expected_action_type, lower_x, lower_y):

      def verifier(x):
        _valid_shape(x)
        _valid_types(x, [np.int32, np.float32])
        self.assertEqual(
            expected_action_type, x['action_type'])
        if lower_y:
          self.assertAlmostEqual(
              vertical_half_step, x['touch_position'][1], delta=delta)
        else:
          self.assertAlmostEqual(
              1 - vertical_half_step, x['touch_position'][1], delta=delta)
        if lower_x:
          self.assertAlmostEqual(
              horizontal_half_step, x['touch_position'][0], delta=delta)
        else:
          self.assertAlmostEqual(
              1 - horizontal_half_step, x['touch_position'][0], delta=delta)
        return True

      return verifier

    action_tests = {
        0: get_verifier(0, lower_x=True, lower_y=True),
        2: get_verifier(0, lower_x=False, lower_y=True),
        9: get_verifier(0, lower_x=True, lower_y=False),
        11: get_verifier(0, lower_x=False, lower_y=False),

        12: get_verifier(1, lower_x=True, lower_y=True),
        14: get_verifier(1, lower_x=False, lower_y=True),
        21: get_verifier(1, lower_x=True, lower_y=False),
        23: get_verifier(1, lower_x=False, lower_y=False),

        24: get_verifier(2, lower_x=True, lower_y=True),
        26: get_verifier(2, lower_x=False, lower_y=True),
        33: get_verifier(2, lower_x=True, lower_y=False),
        35: get_verifier(2, lower_x=False, lower_y=False),
    }

    fake_timestep = 'ts'
    self.base_env.step.return_value = fake_timestep

    for action_id, verifier in action_tests.items():
      ts = wrapped_env.step({'action_id': action_id})
      verifier(self.base_env.step.call_args[0][0])
      self.assertEqual(fake_timestep, ts)

  def test_step_redundant_actions_invalid_action_id(self):
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env,
        action_grid=(4, 3),
        noise=0.0,
        redundant_actions=True)
    with self.assertRaises(AssertionError):
      _ = wrapped_env.step({'action_id': 36})

  def test_step_no_noise_no_redudant_actions(self):
    height = 4
    width = 3
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env,
        action_grid=(height, width),
        noise=0.0,
        redundant_actions=False)
    self.assertEqual(height * width + (self._num_action_types - 1),
                     wrapped_env.num_actions)

    vertical_half_step = 1. / float(height) / 2.
    horizontal_half_step = 1. / float(width) / 2.

    delta = 0.0001

    # Testing the four corners with each finger position
    def get_verifier(expected_action_type, lower_x, lower_y):

      def verifier(x):
        _valid_shape(x)
        _valid_types(x, [np.int32, np.float32])
        self.assertEqual(expected_action_type, x['action_type'])
        # If the action type == TOUCH, then check the coordinate values.
        if x['action_type'] == ActionType.TOUCH:
          if lower_y:
            self.assertAlmostEqual(
                vertical_half_step, x['touch_position'][1], delta=delta)
          else:
            self.assertAlmostEqual(
                1 - vertical_half_step, x['touch_position'][1], delta=delta)
          if lower_x:
            self.assertAlmostEqual(
                horizontal_half_step, x['touch_position'][0], delta=delta)
          else:
            self.assertAlmostEqual(
                1 - horizontal_half_step, x['touch_position'][0], delta=delta)
        return True

      return verifier

    action_tests = {
        # Touch type actions
        0: get_verifier(0, lower_x=True, lower_y=True),
        2: get_verifier(0, lower_x=False, lower_y=True),
        9: get_verifier(0, lower_x=True, lower_y=False),
        11: get_verifier(0, lower_x=False, lower_y=False),
        # Actions > grid_size return non-touch actions with (0,0) coordinates.
        12: get_verifier(1, lower_x=False, lower_y=False),
        13: get_verifier(2, lower_x=False, lower_y=False),
    }

    fake_timestep = 'ts'
    self.base_env.step.return_value = fake_timestep

    for action_id, verifier in action_tests.items():
      ts = wrapped_env.step({'action_id': action_id})
      verifier(self.base_env.step.call_args[0][0])
      self.assertEqual(fake_timestep, ts)

  def test_step_no_redundant_actions_invalid_action_id(self):
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env,
        action_grid=(4, 3),
        noise=0.0,
        redundant_actions=False)
    with self.assertRaises(AssertionError):
      _ = wrapped_env.step({'action_id': 14})

  def test_step_with_noise(self):
    height = 4
    width = 3
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env, action_grid=(height, width), noise=1.0)
    self.assertEqual(height * width * self._num_action_types,
                     wrapped_env.num_actions)

    vertical_grid_step = 1. / float(height)
    horizontal_grid_step = 1. / float(width)

    # Testing the four corners with each finger position
    def get_verifier(expected_up_down, lower_x, lower_y):

      def verifier(x):
        _valid_shape(x)
        _valid_types(x, [np.int32, np.float32])
        self.assertEqual(expected_up_down, x['action_type'])
        if lower_y:
          self.assertGreater(vertical_grid_step, x['touch_position'][1])
        else:
          self.assertLess(1 - vertical_grid_step, x['touch_position'][1])
        if lower_x:
          self.assertGreater(horizontal_grid_step, x['touch_position'][0])
        else:
          self.assertLess(1 - horizontal_grid_step, x['touch_position'][0])
        return True

      return verifier

    action_tests = {
        0: get_verifier(0, lower_x=True, lower_y=True),
        2: get_verifier(0, lower_x=False, lower_y=True),
        9: get_verifier(0, lower_x=True, lower_y=False),
        11: get_verifier(0, lower_x=False, lower_y=False),

        12: get_verifier(1, lower_x=True, lower_y=True),
        14: get_verifier(1, lower_x=False, lower_y=True),
        21: get_verifier(1, lower_x=True, lower_y=False),
        23: get_verifier(1, lower_x=False, lower_y=False),

        24: get_verifier(2, lower_x=True, lower_y=True),
        26: get_verifier(2, lower_x=False, lower_y=True),
        33: get_verifier(2, lower_x=True, lower_y=False),
        35: get_verifier(2, lower_x=False, lower_y=False),
    }

    fake_timestep = 'ts'
    self.base_env.step.return_value = fake_timestep

    for action_id, verifier in action_tests.items():
      ts = wrapped_env.step({'action_id': action_id})
      verifier(self.base_env.step.call_args[0][0])
      self.assertEqual(fake_timestep, ts)

  def test_parent_spec_type(self):
    base_action_spec = {
        'action_type': specs.DiscreteArray(
            num_values=self._num_action_types, name='action_type'),
        'touch_position': _make_array_spec(
            shape=(2,), dtype=np.float64, name='touch_position'),
    }
    base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    base_env.action_spec.return_value = base_action_spec

    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        base_env, noise=0.0)

    fake_timestep = 'ts'
    base_env.step.return_value = fake_timestep

    def verifier(x):
      _valid_types(x, [np.int32, np.float64])
      return True

    ts = wrapped_env.step({'action_id': 1})
    verifier(base_env.step.call_args[0][0])
    self.assertEqual(fake_timestep, ts)

  def test_observation_spec(self):
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env)
    fake_obs_spec = 'fake_obs_spec'
    self.base_env.observation_spec.return_value = fake_obs_spec
    observation_spec = wrapped_env.observation_spec()
    self.base_env.observation_spec.assert_called_once()
    self.assertEqual(fake_obs_spec, observation_spec)

  def test_action_spec(self):
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env, action_grid=(4, 5), redundant_actions=True)
    expected_action_spec = {
        'action_id':
            specs.DiscreteArray(
                num_values=4 * 5 * self._num_action_types, name='action_type')
    }
    self.assertEqual(expected_action_spec, wrapped_env.action_spec())

  def test_action_spec_non_redundant(self):
    wrapped_env = discrete_action_wrapper.DiscreteActionWrapper(
        self.base_env, action_grid=(4, 5), redundant_actions=False)
    num_non_touch_actions = self._num_action_types - 1
    expected_action_spec = {
        'action_id':
            specs.DiscreteArray(
                num_values=4 * 5 + num_non_touch_actions, name='action_type')
    }
    self.assertEqual(expected_action_spec, wrapped_env.action_spec())

  def test_assert_base_env_action_spec_too_short(self):
    self.base_env.action_spec.return_value = {
        'action_type': specs.DiscreteArray(
            num_values=self._num_action_types, name='action_type'),
    }
    with self.assertRaises(AssertionError):
      _ = discrete_action_wrapper.DiscreteActionWrapper(self.base_env)

  def test_assert_base_env_action_spec_too_long(self):
    self.base_env.action_spec.return_value = {
        'action_type': specs.DiscreteArray(
            num_values=self._num_action_types, name='action_type'),
        'touch_position': _make_array_spec(
            shape=(2,), dtype=np.float32, name='touch_position'),
        'too_long': _make_array_spec(
            shape=(1,), dtype=np.float32, name='too_long'),
    }
    with self.assertRaises(AssertionError):
      _ = discrete_action_wrapper.DiscreteActionWrapper(self.base_env)

  def test_assert_base_env_action_spec_wrong_shapes(self):
    self.base_env.action_spec.return_value = {
        'action_type': _make_array_spec(
            shape=(2,), dtype=np.float32, name='action_type'),
        'touch_position': _make_array_spec(
            shape=(1,), dtype=np.float32, name='touch_position')
    }
    with self.assertRaises(AssertionError):
      _ = discrete_action_wrapper.DiscreteActionWrapper(self.base_env)

  def test_assert_base_env_ok(self):
    self.base_env.action_spec.return_value = {
        'action_type': specs.DiscreteArray(
            num_values=self._num_action_types, name='action_type'),
        'touch_position': _make_array_spec(
            shape=(2,), dtype=np.float32, name='touch_position'),
    }
    _ = discrete_action_wrapper.DiscreteActionWrapper(self.base_env)


if __name__ == '__main__':
  absltest.main()
