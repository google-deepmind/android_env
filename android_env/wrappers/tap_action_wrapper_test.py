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

"""Tests for tap_action_wrapper."""

from unittest import mock

from absl.testing import absltest
from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import tap_action_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _make_array_spec(shape, dtype, name):
  return specs.BoundedArray(
      name=name,
      shape=shape,
      dtype=dtype,
      minimum=np.zeros(shape),
      maximum=np.ones(shape),  # maximum is inclusive.
  )


class TapActionWrapperTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._base_action_spec = {
        'action_type': specs.DiscreteArray(
            num_values=3, name='action_type'),
        'touch_position': _make_array_spec(
            shape=(2,), dtype=np.float32, name='touch_position'),
    }
    self.base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    self.base_env.action_spec.return_value = self._base_action_spec

  def test_process_action_repeat(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=3)
    action = {
        'action_type': np.array(action_type.ActionType.REPEAT, dtype=np.int32),
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    }
    actions = wrapped_env._process_action(action)
    self.assertLen(actions, wrapped_env._num_frames + 1)
    self.assertEqual(action, actions[-1])

  def test_process_action_lift(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=3)
    action = {
        'action_type': np.array(action_type.ActionType.LIFT, dtype=np.int32),
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    }
    actions = wrapped_env._process_action(action)
    self.assertLen(actions, wrapped_env._num_frames + 1)
    self.assertEqual(action, actions[-1])

  def test_process_action_touch(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=3)
    action = {
        'action_type': np.array(action_type.ActionType.TOUCH, dtype=np.int32),
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    }
    actions = wrapped_env._process_action(action)
    self.assertLen(actions, wrapped_env._num_frames + 1)
    self.assertEqual(
        actions[-1]['action_type'], np.array(action_type.ActionType.LIFT)
    )

  def test_reset(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=5)
    fake_timestep = 'ts'
    self.base_env.reset.return_value = fake_timestep
    ts = wrapped_env.reset()
    self.base_env.reset.assert_called_once()
    self.assertEqual(fake_timestep, ts)

  def test_step(self):
    # Arrange.
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=5)
    fake_timestep = dm_env.TimeStep(
        step_type='fake_type',
        reward=0.0,
        discount=1.0,
        observation='fake_obs')
    self.base_env.step.return_value = fake_timestep
    self.base_env.stats.return_value = {}

    # Act.
    ts = wrapped_env.step({
        'action_type': np.array(action_type.ActionType.REPEAT, dtype=np.int32),
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    })
    stats = wrapped_env.stats()

    # Assert.
    self.assertEqual(wrapped_env._num_frames+1, self.base_env.step.call_count)
    self.assertIsInstance(ts, dm_env.TimeStep)
    self.assertIsInstance(stats, dict)
    self.assertIn('env_steps', stats)
    self.assertEqual(stats['env_steps'], 6)

  def test_observation_spec(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=5)
    fake_obs_spec = 'fake_obs_spec'
    self.base_env.observation_spec.return_value = fake_obs_spec
    observation_spec = wrapped_env.observation_spec()
    self.base_env.observation_spec.assert_called_once()
    self.assertEqual(fake_obs_spec, observation_spec)

  def test_action_spec(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=5)
    self.base_env.action_spec.return_value = self._base_action_spec
    action_spec = wrapped_env.action_spec()
    self.base_env.action_spec.assert_called()
    self.assertEqual(self.base_env.action_spec(),
                     action_spec)

  def test_stats(self):
    """Checks that returned stats have expected properties."""

    # Arrange.
    self.base_env.stats.return_value = {
        'some_key': 12345,
        'another_key': 5.4321,
    }
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_frames=5
    )

    # Act.
    stats = wrapped_env.stats()

    # Assert.
    self.assertIsInstance(stats, dict)
    # Original entries should still be present.
    self.assertIn('some_key', stats)
    self.assertEqual(stats['some_key'], 12345)
    self.assertIn('another_key', stats)
    self.assertEqual(stats['another_key'], 5.4321)
    # TapActionWrapper inserts its own `env_steps`.
    self.assertIn('env_steps', stats)
    self.assertEqual(stats['env_steps'], 0)


if __name__ == '__main__':
  absltest.main()
