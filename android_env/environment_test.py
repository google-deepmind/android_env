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

"""Unit tests for AndroidEnv."""

from unittest import mock

from absl.testing import absltest
from android_env import environment
from android_env.components import config_classes
from android_env.components import coordinator as coordinator_lib
from android_env.components import task_manager as task_manager_lib
from android_env.components.simulators import base_simulator
from android_env.components.simulators.fake import fake_simulator
from android_env.proto import adb_pb2
from android_env.proto import state_pb2
import dm_env
import numpy as np


def _create_mock_coordinator() -> coordinator_lib.Coordinator:
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
  return coordinator


def _create_fake_simulator() -> fake_simulator.FakeSimulator:
  return fake_simulator.FakeSimulator(
      config=config_classes.FakeSimulatorConfig(screen_dimensions=(123, 456))
  )


class AndroidEnvTest(absltest.TestCase):

  def test_specs(self):
    simulator = _create_fake_simulator()
    coordinator = _create_mock_coordinator()
    task_manager = mock.create_autospec(task_manager_lib.TaskManager)
    env = environment.AndroidEnv(
        simulator=simulator, coordinator=coordinator, task_manager=task_manager
    )

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

  def test_reset_and_step(self):
    simulator = _create_fake_simulator()
    coordinator = _create_mock_coordinator()
    task_manager = mock.create_autospec(task_manager_lib.TaskManager)
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
    env = environment.AndroidEnv(
        simulator=simulator, coordinator=coordinator, task_manager=task_manager
    )
    coordinator.rl_reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=0.0,
        discount=0.0,
        observation={
            'pixels': np.random.rand(987, 654, 3),
            'timedelta': 123456,
            'orientation': np.array((1, 0, 0, 0)),
            'extras': {
                'click': np.array([[246]], dtype=np.int64)
            }
        },
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

    coordinator.stats.return_value = {'my_measurement': 135}
    task_manager.stats.return_value = {'another_measurement': 79}

    # Step again in the environment and check expectations again.
    pixels = np.random.rand(987, 654, 3)
    latest_observation = {
        'pixels': pixels,
        'timedelta': 123456,
        'orientation': np.array((1, 0, 0, 0)),
        'extras': {
            'click': np.array([[246]], dtype=np.int64)
        }
    }
    coordinator.rl_step.return_value = dm_env.transition(
        reward=0.0,
        discount=0.0,
        observation=latest_observation,
    )
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
    self.assertNotEmpty(env.stats())
    self.assertNotEmpty(env.raw_observation)
    self.assertNotIn('extras', env.raw_observation)
    self.assertNotEmpty(env.raw_action)

    # If the observation is None, we want to return the latest observation.
    coordinator.rl_step.return_value = dm_env.truncation(
        reward=0.0,
        observation=None,
    )
    ts = env.step({'action_type': 1, 'touch_position': (10, 20)})
    self.assertIsInstance(ts, dm_env.TimeStep)
    # Assert the observation matches the latest observation.
    obs = ts.observation
    self.assertIn('pixels', obs)
    self.assertEqual(obs['pixels'].shape, (987, 654, 3))
    np.testing.assert_equal(obs['pixels'], pixels)
    self.assertIn('timedelta', obs)
    self.assertEqual(obs['timedelta'], 123456)
    self.assertIn('orientation', obs)
    self.assertEqual(obs['orientation'].shape, (4,))
    np.testing.assert_equal(obs['orientation'], (1, 0, 0, 0))

  def test_adb_call(self):
    simulator = _create_fake_simulator()
    coordinator = _create_mock_coordinator()
    task_manager = mock.create_autospec(task_manager_lib.TaskManager)
    env = environment.AndroidEnv(
        simulator=simulator, coordinator=coordinator, task_manager=task_manager
    )
    call = adb_pb2.AdbRequest(
        force_stop=adb_pb2.AdbRequest.ForceStop(package_name='blah'))
    expected_response = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK)
    coordinator.execute_adb_call.return_value = expected_response

    response = env.execute_adb_call(call)

    self.assertEqual(response, expected_response)
    coordinator.execute_adb_call.assert_called_once_with(call)

  def test_load_state(self):
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    coordinator = _create_mock_coordinator()
    task_manager = mock.create_autospec(task_manager_lib.TaskManager)
    env = environment.AndroidEnv(
        simulator=simulator, coordinator=coordinator, task_manager=task_manager
    )
    expected_response = state_pb2.LoadStateResponse(
        status=state_pb2.LoadStateResponse.Status.OK
    )
    request = state_pb2.LoadStateRequest(args={'foo': 'bar'})
    simulator.load_state.return_value = expected_response
    response = env.load_state(request)
    self.assertEqual(response, expected_response)
    simulator.load_state.assert_called_once_with(request)
    task_manager.stop.assert_called_once()
    task_manager.start.assert_called_once()

  def test_save_state(self):
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    coordinator = _create_mock_coordinator()
    task_manager = mock.create_autospec(task_manager_lib.TaskManager)
    env = environment.AndroidEnv(
        simulator=simulator, coordinator=coordinator, task_manager=task_manager
    )
    expected_response = state_pb2.SaveStateResponse(
        status=state_pb2.SaveStateResponse.Status.OK
    )
    request = state_pb2.SaveStateRequest(args={'foo': 'bar'})
    simulator.save_state.return_value = expected_response
    response = env.save_state(request)
    self.assertEqual(response, expected_response)
    simulator.save_state.assert_called_once_with(request)

  def test_double_close(self):
    simulator = _create_fake_simulator()
    coordinator = _create_mock_coordinator()
    task_manager = mock.create_autospec(task_manager_lib.TaskManager)
    env = environment.AndroidEnv(
        simulator=simulator, coordinator=coordinator, task_manager=task_manager
    )
    env.close()
    env.close()
    coordinator.close.assert_called_once()


if __name__ == '__main__':
  absltest.main()
