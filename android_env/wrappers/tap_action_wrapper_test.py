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

import typing
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
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


class TapActionWrapperTest(parameterized.TestCase):

  def setUp(self):
    super().setUp()
    self._base_action_spec = {
        'action_type': specs.DiscreteArray(num_values=3, name='action_type'),
        'touch_position': _make_array_spec(
            shape=(2,), dtype=np.float32, name='touch_position'
        ),
    }
    self.base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    self.base_env.action_spec.return_value = self._base_action_spec

  @parameterized.named_parameters(
      dict(
          testcase_name='repeat',
          input_action_type=action_type.ActionType.REPEAT,
          touch_only=False,
          expected_action_types=[action_type.ActionType.REPEAT] * 4,
      ),
      dict(
          testcase_name='lift',
          input_action_type=action_type.ActionType.LIFT,
          touch_only=False,
          expected_action_types=[action_type.ActionType.LIFT] * 4,
      ),
      dict(
          testcase_name='touch',
          input_action_type=action_type.ActionType.TOUCH,
          touch_only=False,
          expected_action_types=[action_type.ActionType.TOUCH] * 3
          + [action_type.ActionType.LIFT],
      ),
      dict(
          testcase_name='touch_only',
          input_action_type=0,
          touch_only=True,
          expected_action_types=[action_type.ActionType.TOUCH] * 3
          + [action_type.ActionType.LIFT],
      ),
  )
  def test_process_action(
      self, input_action_type, touch_only, expected_action_types
  ):
    num_steps = 3
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=num_steps, touch_only=touch_only
    )
    touch_pos = np.array([0.5, 0.5], dtype=np.float32)
    action = {
        'action_type': np.array(input_action_type, dtype=np.int32),
        'touch_position': touch_pos,
    }
    actions = wrapped_env._process_action(action)
    self.assertLen(actions, num_steps + 1)

    actual_action_types = [
        processed_action['action_type'] for processed_action in actions
    ]
    expected_action_types_array = np.array(
        expected_action_types, dtype=np.int32
    )
    np.testing.assert_array_equal(
        np.array(actual_action_types).flatten(),
        expected_action_types_array.flatten(),
    )

    actual_touch_positions = [
        processed_action['touch_position'] for processed_action in actions
    ]
    expected_touch_positions = [touch_pos] * (num_steps + 1)
    np.testing.assert_array_equal(
        np.array(actual_touch_positions), np.array(expected_touch_positions)
    )

  def test_reset(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=5
    )
    fake_timestep = 'ts'
    self.base_env.reset.return_value = fake_timestep
    ts = wrapped_env.reset()
    self.base_env.reset.assert_called_once()
    self.assertEqual(fake_timestep, ts)

  def test_step(self):

    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=5
    )
    fake_timestep = dm_env.TimeStep(
        step_type='fake_type', reward=0.0, discount=1.0, observation='fake_obs'
    )
    self.base_env.step.return_value = fake_timestep
    self.base_env.stats.return_value = {}

    ts = wrapped_env.step({
        'action_type': np.array(action_type.ActionType.REPEAT, dtype=np.int32),
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    })
    stats = wrapped_env.stats()

    self.assertEqual(wrapped_env._num_steps + 1, self.base_env.step.call_count)
    self.assertIsInstance(ts, dm_env.TimeStep)
    self.assertIsInstance(stats, dict)
    self.assertIn('env_steps', stats)
    self.assertEqual(stats['env_steps'], 6)

  def test_observation_spec(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=5
    )
    fake_obs_spec = 'fake_obs_spec'
    self.base_env.observation_spec.return_value = fake_obs_spec
    observation_spec = wrapped_env.observation_spec()
    self.base_env.observation_spec.assert_called_once()
    self.assertEqual(fake_obs_spec, observation_spec)

  def test_action_spec(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=5
    )
    self.base_env.action_spec.return_value = self._base_action_spec
    action_spec = wrapped_env.action_spec()
    self.base_env.action_spec.assert_called()
    self.assertEqual(self.base_env.action_spec(),
                     action_spec)

  def test_stats(self):
    """Checks that returned stats have expected properties."""

    self.base_env.stats.return_value = {
        'some_key': 12345,
        'another_key': 5.4321,
    }
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=5
    )

    stats = wrapped_env.stats()

    self.assertIsInstance(stats, dict)
    # Original entries should still be present.
    self.assertIn('some_key', stats)
    self.assertEqual(stats['some_key'], 12345)
    self.assertIn('another_key', stats)
    self.assertEqual(stats['another_key'], 5.4321)
    # TapActionWrapper inserts its own `env_steps`.
    self.assertIn('env_steps', stats)
    self.assertEqual(stats['env_steps'], 0)

  def test_action_spec_touch_only(self):
    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=5, touch_only=True
    )
    action_spec = wrapped_env.action_spec()
    self.assertCountEqual(action_spec.keys(), ['action_type', 'touch_position'])
    action_type_spec = action_spec['action_type']
    self.assertIsInstance(action_type_spec, specs.DiscreteArray)
    discrete_action_type_spec = typing.cast(
        specs.DiscreteArray, action_type_spec
    )
    self.assertEqual(discrete_action_type_spec.num_values, 1)

  def test_step_terminal(self):

    wrapped_env = tap_action_wrapper.TapActionWrapper(
        self.base_env, num_steps=5
    )
    normal_timestep = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=0.0,
        discount=1.0,
        observation='fake_obs',
    )
    terminal_timestep = dm_env.TimeStep(
        step_type=dm_env.StepType.LAST,
        reward=1.0,
        discount=0.0,
        observation='final_obs',
    )

    self.base_env.step.side_effect = [
        normal_timestep,
        normal_timestep,
        terminal_timestep,
    ]
    self.base_env.stats.return_value = {}

    ts = wrapped_env.step({
        'action_type': np.array(action_type.ActionType.REPEAT, dtype=np.int32),
        'touch_position': np.array([0.5, 0.5], dtype=np.float32),
    })

    self.assertEqual(3, self.base_env.step.call_count)
    self.assertIs(ts.step_type, dm_env.StepType.LAST)
    self.assertEqual(ts.reward, 1.0)


if __name__ == '__main__':
  absltest.main()
