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

from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import swipe_action_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _make_array_spec(shape, dtype, name):
  return specs.BoundedArray(
      name=name,
      shape=shape,
      dtype=dtype,
      minimum=np.zeros(shape),
      maximum=np.ones(shape),
  )


class SwipeActionWrapperTest(parameterized.TestCase):

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

  def test_process_action_interpolation(self):
    num_steps = 5
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=num_steps
    )
    start = np.array([0.0, 0.0], dtype=np.float32)
    end = np.array([1.0, 1.0], dtype=np.float32)
    action = {'start_position': start, 'end_position': end}

    actions = wrapped_env._process_action(action)
    self.assertLen(actions, num_steps + 1)

    expected_alphas = [0.0, 0.25, 0.5, 0.75, 1.0]
    for i, alpha in enumerate(expected_alphas):
      expected_position = start * (1.0 - alpha) + end * alpha
      np.testing.assert_allclose(
          actions[i]['touch_position'], expected_position, rtol=1e-6
      )
      self.assertEqual(
          actions[i]['action_type'], action_type.ActionType.TOUCH
      )

    self.assertEqual(actions[-1]['action_type'], action_type.ActionType.LIFT)
    np.testing.assert_allclose(actions[-1]['touch_position'], end, rtol=1e-6)

  def test_process_action_single_step(self):
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=1
    )
    start = np.array([0.2, 0.3], dtype=np.float32)
    end = np.array([0.8, 0.9], dtype=np.float32)
    actions = wrapped_env._process_action({
        'start_position': start,
        'end_position': end,
    })

    self.assertLen(actions, 2)
    np.testing.assert_allclose(actions[0]['touch_position'], start, rtol=1e-6)
    self.assertEqual(actions[0]['action_type'], action_type.ActionType.TOUCH)
    np.testing.assert_allclose(actions[1]['touch_position'], end, rtol=1e-6)
    self.assertEqual(actions[1]['action_type'], action_type.ActionType.LIFT)

  def test_invalid_num_steps(self):
    with self.assertRaisesRegex(ValueError, 'num_steps must be >= 1'):
      swipe_action_wrapper.SwipeActionWrapper(self.base_env, num_steps=0)

  def test_reset(self):
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=5
    )
    fake_timestep = 'ts'
    self.base_env.reset.return_value = fake_timestep
    ts = wrapped_env.reset()
    self.base_env.reset.assert_called_once()
    self.assertEqual(fake_timestep, ts)

  def test_step(self):
    num_steps = 5
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=num_steps
    )
    fake_timestep = dm_env.TimeStep(
        step_type='fake_type', reward=0.0, discount=1.0, observation='fake_obs'
    )
    self.base_env.step.return_value = fake_timestep
    self.base_env.stats.return_value = {}

    ts = wrapped_env.step({
        'start_position': np.array([0.0, 0.0], dtype=np.float32),
        'end_position': np.array([1.0, 1.0], dtype=np.float32),
    })
    stats = wrapped_env.stats()

    self.assertEqual(num_steps + 1, self.base_env.step.call_count)
    self.assertIsInstance(ts, dm_env.TimeStep)
    self.assertIsInstance(stats, dict)
    self.assertIn('env_steps', stats)
    self.assertEqual(stats['env_steps'], num_steps + 1)

  def test_step_terminal(self):
    num_steps = 5
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=num_steps
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
        'start_position': np.array([0.0, 0.5], dtype=np.float32),
        'end_position': np.array([1.0, 0.5], dtype=np.float32),
    })

    self.assertEqual(3, self.base_env.step.call_count)
    self.assertIs(ts.step_type, dm_env.StepType.LAST)
    self.assertEqual(ts.reward, 1.0)

  def test_step_accumulates_reward(self):
    num_steps = 3
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=num_steps
    )
    self.base_env.step.side_effect = [
        dm_env.TimeStep(dm_env.StepType.MID, 0.1, 1.0, 'obs'),
        dm_env.TimeStep(dm_env.StepType.MID, 0.2, 1.0, 'obs'),
        dm_env.TimeStep(dm_env.StepType.MID, 0.3, 1.0, 'obs'),
        dm_env.TimeStep(dm_env.StepType.MID, 0.4, 1.0, 'obs'),
    ]
    self.base_env.stats.return_value = {}

    ts = wrapped_env.step({
        'start_position': np.array([0.0, 0.0], dtype=np.float32),
        'end_position': np.array([1.0, 0.0], dtype=np.float32),
    })

    self.assertAlmostEqual(ts.reward, 1.0)

  def test_observation_spec(self):
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=5
    )
    fake_obs_spec = 'fake_obs_spec'
    self.base_env.observation_spec.return_value = fake_obs_spec
    observation_spec = wrapped_env.observation_spec()
    self.base_env.observation_spec.assert_called_once()
    self.assertEqual(fake_obs_spec, observation_spec)

  def test_action_spec(self):
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=5
    )
    action_spec = wrapped_env.action_spec()
    self.assertCountEqual(
        action_spec.keys(), ['start_position', 'end_position']
    )
    for key in ('start_position', 'end_position'):
      spec = action_spec[key]
      self.assertIsInstance(spec, specs.BoundedArray)
      self.assertEqual(spec.shape, (2,))
      self.assertEqual(spec.dtype, np.float32)

  def test_stats(self):
    self.base_env.stats.return_value = {
        'some_key': 12345,
        'another_key': 5.4321,
    }
    wrapped_env = swipe_action_wrapper.SwipeActionWrapper(
        self.base_env, num_steps=5
    )

    stats = wrapped_env.stats()

    self.assertIn('some_key', stats)
    self.assertEqual(stats['some_key'], 12345)
    self.assertIn('env_steps', stats)
    self.assertEqual(stats['env_steps'], 0)


if __name__ == '__main__':
  absltest.main()
