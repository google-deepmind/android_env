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

"""Unit tests for AndroidEnv."""

from absl.testing import absltest
from android_env import android_env
from android_env.components import coordinator as coordinator_lib
import dm_env
import mock
import numpy as np


class AndroidEnvTest(absltest.TestCase):

  def test_specs(self):
    coordinator = mock.create_autospec(coordinator_lib.Coordinator)
    coordinator.action_spec.return_value = {
        'action_type':
            dm_env.specs.DiscreteArray(num_values=3),
        'touch_position':
            dm_env.specs.BoundedArray(
                shape=(2,), dtype=np.float32, minimum=0.0, maximum=1.0),
    }
    coordinator.observation_spec.return_value = {
        'pixels': dm_env.specs.Array(shape=(123, 456, 3), dtype=np.uint8),
        'timedelta': dm_env.specs.Array(shape=(), dtype=np.int64),
        'orientation': dm_env.specs.Array(shape=(4,), dtype=np.uint8),
    }
    coordinator.task_extras_spec.return_value = {
        'click': dm_env.specs.Array(shape=(), dtype=np.int64),
    }
    env = android_env.AndroidEnv(coordinator)

    # Check action spec.
    self.assertNotEmpty(env.action_spec())
    self.assertIn('action_type', env.action_spec())
    self.assertIsInstance(env.action_spec()['action_type'],
                          dm_env.specs.DiscreteArray)
    self.assertIn('touch_position', env.action_spec())
    self.assertIsInstance(env.action_spec()['touch_position'],
                          dm_env.specs.BoundedArray)

    # Check observation spec.
    self.assertNotEmpty(env.observation_spec())
    self.assertIn('pixels', env.observation_spec())
    self.assertIsInstance(env.observation_spec()['pixels'], dm_env.specs.Array)
    # The `pixels` entry in the observation spec should match the screen size of
    # the simulator with three color channels (RGB).
    self.assertEqual(env.observation_spec()['pixels'].shape, (123, 456, 3))
    self.assertIn('timedelta', env.observation_spec())
    self.assertIsInstance(env.observation_spec()['timedelta'],
                          dm_env.specs.Array)
    # The `timedelta` should be a scalar.
    self.assertEqual(env.observation_spec()['timedelta'].shape, ())
    self.assertIn('orientation', env.observation_spec())
    # The `orientation` should be a one-hot vector with four dimensions.
    self.assertIsInstance(env.observation_spec()['orientation'],
                          dm_env.specs.Array)
    self.assertEqual(env.observation_spec()['orientation'].shape, (4,))

    # Check extras spec.
    self.assertNotEmpty(env.task_extras_spec())
    self.assertIn('click', env.task_extras_spec())
    self.assertEqual(env.task_extras_spec()['click'].shape, ())
    self.assertEqual(env.task_extras_spec()['click'].dtype, np.int64)

  def test_reset_and_step(self):
    coordinator = mock.create_autospec(coordinator_lib.Coordinator)
    coordinator.action_spec.return_value = {
        'action_type':
            dm_env.specs.DiscreteArray(num_values=3),
        'touch_position':
            dm_env.specs.BoundedArray(
                shape=(2,), dtype=np.float32, minimum=0.0, maximum=1.0),
    }
    coordinator.observation_spec.return_value = {
        'pixels': dm_env.specs.Array(shape=(123, 456, 3), dtype=np.uint8),
        'timedelta': dm_env.specs.Array(shape=(), dtype=np.int64),
        'orientation': dm_env.specs.Array(shape=(4,), dtype=np.uint8),
    }
    coordinator.task_extras_spec.return_value = {
        'click': dm_env.specs.Array(shape=(1,), dtype=np.int64),
    }
    env = android_env.AndroidEnv(coordinator)
    coordinator.execute_action.return_value = (
        {
            'pixels': np.random.rand(987, 654, 3),
            'timedelta': 123456,
            'orientation': np.array((1, 0, 0, 0)),
        },  # Observation
        0.0,  # Reward.
        {
            'click': np.array([[246]], dtype=np.int64)
        },  # Task extras.
        False  # Episode ended?
    )

    ts = env.reset()
    self.assertIsInstance(ts, dm_env.TimeStep)
    # After a `reset()` the TimeStep should follow some expectations.
    self.assertTrue(ts.first())
    self.assertEqual(ts.reward, 0.0)
    self.assertEqual(ts.discount, 0.0)
    obs = ts.observation
    self.assertIn('pixels', obs)
    self.assertEqual(obs['pixels'].shape, (987, 654, 3))
    self.assertIn('timedelta', obs)
    self.assertEqual(obs['timedelta'], 123456)
    self.assertIn('orientation', obs)
    self.assertEqual(obs['orientation'].shape, (4,))
    np.testing.assert_equal(obs['orientation'], (1, 0, 0, 0))

    # Extras should also be provided.
    extras = env.task_extras()
    self.assertIn('click', extras)
    self.assertEqual(extras['click'], np.array([246], dtype=np.int64))

    coordinator.get_logs.return_value = {
        'my_measurement': 135,
    }

    # Step again in the environment and check expectations again.
    ts = env.step({'action_type': 1, 'touch_position': (10, 20)})
    self.assertIsInstance(ts, dm_env.TimeStep)
    # The StepType now should NOT be FIRST.
    self.assertFalse(ts.first())
    self.assertEqual(ts.reward, 0.0)
    self.assertEqual(ts.discount, 0.0)
    obs = ts.observation
    self.assertIn('pixels', obs)
    self.assertEqual(obs['pixels'].shape, (987, 654, 3))
    self.assertIn('timedelta', obs)
    self.assertEqual(obs['timedelta'], 123456)
    self.assertIn('orientation', obs)
    self.assertEqual(obs['orientation'].shape, (4,))
    np.testing.assert_equal(obs['orientation'], (1, 0, 0, 0))

    # Extras should still be provided.
    extras = env.task_extras()
    self.assertIn('click', extras)
    self.assertEqual(extras['click'], np.array([246], dtype=np.int64))

    # At this point these methods and properties should return something.
    self.assertNotEmpty(env.android_logs())
    self.assertNotEmpty(env.raw_observation)
    self.assertNotEmpty(env.raw_action)

if __name__ == '__main__':
  absltest.main()
