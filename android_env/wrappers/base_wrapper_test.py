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

"""Tests for android_env.wrappers.base_wrapper."""

from unittest import mock

from absl import logging
from absl.testing import absltest
from android_env import env_interface
from android_env.proto import state_pb2
from android_env.wrappers import base_wrapper


class BaseWrapperTest(absltest.TestCase):

  @mock.patch.object(logging, 'info')
  def test_base_function_forwarding(self, mock_info):
    base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    wrapped_env = base_wrapper.BaseWrapper(base_env)
    mock_info.assert_called_with('Wrapping with %s', 'BaseWrapper')

    fake_ts = 'fake_ts'
    base_env.reset.return_value = fake_ts
    self.assertEqual(fake_ts, wrapped_env.reset())
    base_env.reset.assert_called_once()

    fake_ts = 'fake_ts'
    fake_action = 'fake_action'
    base_env.step.return_value = fake_ts
    self.assertEqual(fake_ts, wrapped_env.step(fake_action))
    base_env.step.assert_called_once_with(fake_action)

    fake_extras = 'fake_task_extras'
    base_env.task_extras.return_value = fake_extras
    self.assertEqual(fake_extras, wrapped_env.task_extras(latest_only=True))
    base_env.task_extras.assert_called_once_with(latest_only=True)

    fake_obs_spec = 'fake_obs_spec'
    base_env.observation_spec.return_value = fake_obs_spec
    self.assertEqual(fake_obs_spec, wrapped_env.observation_spec())
    base_env.observation_spec.assert_called_once()

    fake_action_spec = 'fake_action_spec'
    base_env.action_spec.return_value = fake_action_spec
    self.assertEqual(fake_action_spec, wrapped_env.action_spec())
    base_env.action_spec.assert_called_once()

    fake_raw_action = 'fake_raw_action'
    type(base_env).raw_action = mock.PropertyMock(return_value=fake_raw_action)
    self.assertEqual(fake_raw_action, wrapped_env.raw_action)

    fake_raw_observation = 'fake_raw_observation'
    type(base_env).raw_observation = mock.PropertyMock(
        return_value=fake_raw_observation)
    self.assertEqual(fake_raw_observation, wrapped_env.raw_observation)

    load_request = state_pb2.LoadStateRequest(args={})
    expected_response = state_pb2.LoadStateResponse(
        status=state_pb2.LoadStateResponse.Status.OK
    )
    base_env.load_state.return_value = expected_response
    self.assertEqual(wrapped_env.load_state(load_request), expected_response)
    base_env.load_state.assert_called_once_with(load_request)

    save_request = state_pb2.SaveStateRequest(args={})
    expected_response = state_pb2.SaveStateResponse(
        status=state_pb2.SaveStateResponse.Status.OK
    )
    base_env.save_state.return_value = expected_response
    self.assertEqual(wrapped_env.save_state(save_request), expected_response)
    base_env.save_state.assert_called_once_with(save_request)

    wrapped_env.close()
    base_env.close.assert_called_once()

    fake_return_value = 'fake'
    # AndroidEnv::some_random_function() does not exist and calling it should
    # raise an AttributeError.
    with self.assertRaises(AttributeError):
      base_env.some_random_function.return_value = fake_return_value

  def test_multiple_wrappers(self):
    base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    wrapped_env_1 = base_wrapper.BaseWrapper(base_env)
    wrapped_env_2 = base_wrapper.BaseWrapper(wrapped_env_1)

    wrapped_env_2.close()
    base_env.close.assert_called_once()

  def test_raw_env(self):
    base_env = 'fake_env'
    wrapped_env_1 = base_wrapper.BaseWrapper(base_env)
    wrapped_env_2 = base_wrapper.BaseWrapper(wrapped_env_1)
    self.assertEqual(base_env, wrapped_env_2.raw_env)

  def test_stats(self):
    base_env = mock.create_autospec(env_interface.AndroidEnvInterface)
    wrapped_env = base_wrapper.BaseWrapper(base_env)
    base_stats = {'base': 'stats'}
    base_env.stats.return_value = base_stats
    self.assertEqual(base_stats, wrapped_env.stats())

  @mock.patch.object(logging, 'info')
  def test_wrapped_stats(self, mock_info):
    base_env = mock.create_autospec(env_interface.AndroidEnvInterface)

    class LoggingWrapper1(base_wrapper.BaseWrapper):

      def _wrapper_stats(self):
        return {
            'wrapper1': 'stats',
            'shared': 1,
        }

    class LoggingWrapper2(base_wrapper.BaseWrapper):

      def _wrapper_stats(self):
        return {
            'wrapper2': 'stats',
            'shared': 2,
        }

    wrapped_env = LoggingWrapper2(LoggingWrapper1(base_env))
    mock_info.assert_has_calls([
        mock.call('Wrapping with %s', 'LoggingWrapper1'),
        mock.call('Wrapping with %s', 'LoggingWrapper2'),
    ])
    base_stats = {'base': 'stats'}
    base_env.stats.return_value = base_stats
    expected_stats = {
        'base': 'stats',
        'wrapper1': 'stats',
        'wrapper2': 'stats',
        'shared': 2,
    }

    self.assertEqual(expected_stats, wrapped_env.stats())


if __name__ == '__main__':
  absltest.main()
