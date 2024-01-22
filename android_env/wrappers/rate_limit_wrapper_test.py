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

"""Tests for rate_limit_wrapper."""

import time
from typing import Any, Protocol
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import rate_limit_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _get_base_env():
  env = mock.create_autospec(env_interface.AndroidEnvInterface)
  env.action_spec.return_value = {
      'action_type':
          specs.DiscreteArray(
              num_values=len(action_type.ActionType),
              name='action_type'),
      'touch_position':
          specs.BoundedArray(
              shape=(2,),
              dtype=np.float32,
              minimum=[0.0, 0.0],
              maximum=[1.0, 1.0],
              name='touch_position'),
  }
  return env


class _FnWithTimestamps(Protocol):
  """A function with `timestamp` and `timestamps` attributes."""

  timestamp: float
  timestamps: list[float]


def _with_timestamp(fn: Any) -> _FnWithTimestamps:
  return fn


class RateLimitWrapperTest(parameterized.TestCase):

  @parameterized.named_parameters(
      ('zero_rate', 0),
      ('negative_rate', -50),
  )
  @mock.patch.object(time, 'sleep', autospec=True)
  def test_disabled(self, rate, mock_sleep):
    """With a non-positive rate, this wrapper should do nothing."""
    env = _get_base_env()
    wrapper = rate_limit_wrapper.RateLimitWrapper(env, rate=rate)
    _ = wrapper.reset()
    mock_sleep.assert_not_called()
    _ = wrapper.step({
        'action_type': np.array(action_type.ActionType.LIFT, dtype=np.uint8),
        'touch_position': np.array([0.123, 0.456])
    })
    mock_sleep.assert_not_called()
    # When the wrapper is disabled, base step should only be called once.
    env.step.assert_called_once()

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_enabled(self, mock_sleep):
    """When enabled, the wrapper should sleep for a period in [0, 1/rate]."""

    env = _get_base_env()
    env.step.return_value = dm_env.transition(reward=None, observation=None)
    wrapper = rate_limit_wrapper.RateLimitWrapper(env, rate=1/33.33)

    _ = wrapper.reset()
    mock_sleep.assert_not_called()  # It should never sleep during reset().

    # Step for 100 steps.
    for _ in range(100):
      _ = wrapper.step({
          'action_type':
              np.array(action_type.ActionType.LIFT, dtype=np.uint8),
          'touch_position':
              np.array([0.123, 0.456])
      })

    # Check that there are 100 calls and that they're all within [0, 1/rate].
    self.assertLen(mock_sleep.call_args_list, 100)
    for call in mock_sleep.call_args_list:
      args, unused_kwargs = call
      sleep_time = args[0]
      self.assertBetween(sleep_time, 0.0, 33.33)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_enabled_sleep_type_before(self, mock_sleep):
    """When sleep_type==BEFORE, sleep should come before step()."""

    env = _get_base_env()
    wrapper = rate_limit_wrapper.RateLimitWrapper(
        env,
        rate=1/33.33,
        sleep_type=rate_limit_wrapper.RateLimitWrapper.SleepType.BEFORE)

    _ = wrapper.reset()
    mock_sleep.assert_not_called()  # It should never sleep during reset().

    @_with_timestamp
    def _sleep_fn(sleep_time):
      _sleep_fn.timestamp = time.time()
      self.assertBetween(sleep_time, 0.0, 33.33)

    mock_sleep.side_effect = _sleep_fn

    def _step_fn(action):
      self.assertEqual(
          action['action_type'],
          np.array(action_type.ActionType.LIFT, dtype=np.uint8))
      _step_fn.timestamps.append(time.time())
      return dm_env.transition(reward=None, observation=None)

    _step_fn.timestamps = []

    env.step.side_effect = _step_fn

    _ = wrapper.step({
        'action_type': np.array(action_type.ActionType.LIFT, dtype=np.uint8),
        'touch_position': np.array([0.123, 0.456])
    })

    self.assertLen(_step_fn.timestamps, 1)
    # We expect sleep to have been executed BEFORE a single `step()`.
    self.assertGreaterEqual(_step_fn.timestamps[0], _sleep_fn.timestamp)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_enabled_sleep_type_after(self, mock_sleep):
    """When sleep_type==AFTER, sleep should come after step()."""

    env = _get_base_env()
    wrapper = rate_limit_wrapper.RateLimitWrapper(
        env,
        rate=1/33.33,
        sleep_type=rate_limit_wrapper.RateLimitWrapper.SleepType.AFTER)
    _ = wrapper.reset()
    mock_sleep.assert_not_called()  # It should never sleep during reset().

    @_with_timestamp
    def _sleep_fn(sleep_time):
      _sleep_fn.timestamp = time.time()
      self.assertBetween(sleep_time, 0.0, 33.33)

    mock_sleep.side_effect = _sleep_fn

    def _step_fn(action):
      self.assertEqual(
          action['action_type'],
          np.array(action_type.ActionType.LIFT, dtype=np.uint8))
      _step_fn.timestamps.append(time.time())
      return dm_env.transition(reward=None, observation=None)

    _step_fn.timestamps = []

    env.step.side_effect = _step_fn

    _ = wrapper.step({
        'action_type': np.array(action_type.ActionType.LIFT, dtype=np.uint8),
        'touch_position': np.array([0.123, 0.456])
    })

    # We expect sleep to have been executed AFTER a single `step()`.
    self.assertLen(_step_fn.timestamps, 1)
    self.assertLessEqual(_step_fn.timestamps[0], _sleep_fn.timestamp)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_enabled_sleep_type_after_with_repeat(self, mock_sleep):
    """When sleep_type==AFTER_WITH_REPEAT, sleep should be between 2 steps()."""

    env = _get_base_env()
    wrapper = rate_limit_wrapper.RateLimitWrapper(
        env,
        rate=1/33.33,
        sleep_type=rate_limit_wrapper.RateLimitWrapper.SleepType
        .AFTER_WITH_REPEAT)

    _ = wrapper.reset()
    mock_sleep.assert_not_called()  # It should never sleep during reset().

    @_with_timestamp
    def _sleep_fn(sleep_time):
      _sleep_fn.timestamp = time.time()
      self.assertBetween(sleep_time, 0.0, 33.33)

    mock_sleep.side_effect = _sleep_fn

    @_with_timestamp
    def _step_fn(action):
      # On even calls the action should be the actual agent action, but on odd
      # calls they should be REPEATs.
      if len(_step_fn.timestamps) % 2 == 0:
        self.assertEqual(
            action['action_type'],
            np.array(action_type.ActionType.LIFT, dtype=np.uint8))
      else:
        self.assertEqual(
            action['action_type'],
            np.array(action_type.ActionType.REPEAT, dtype=np.uint8))
      _step_fn.timestamps.append(time.time())
      return dm_env.transition(reward=1.0, observation=None)

    _step_fn.timestamps = []

    env.step.side_effect = _step_fn

    timestep = wrapper.step({
        'action_type': np.array(action_type.ActionType.LIFT, dtype=np.uint8),
        'touch_position': np.array([0.123, 0.456])
    })

    # When the wrapper is enabled, base step should be called twice.
    self.assertEqual(env.step.call_count, 2)

    # `step()` should be called twice: before `sleep()` and after it.
    self.assertLen(_step_fn.timestamps, 2)
    self.assertGreaterEqual(_sleep_fn.timestamp, _step_fn.timestamps[0])
    self.assertLessEqual(_sleep_fn.timestamp, _step_fn.timestamps[1])
    # Rewards should accumulate over the two step() calls
    self.assertEqual(timestep.reward, 2.0)

  @mock.patch.object(time, 'sleep', autospec=True)
  def test_enabled_sleep_type_after_with_repeat_last(self, mock_sleep):
    """If the first step is a LAST, second step should not be taken."""

    env = _get_base_env()
    wrapper = rate_limit_wrapper.RateLimitWrapper(
        env,
        rate=1/33.33,
        sleep_type=rate_limit_wrapper.RateLimitWrapper.SleepType
        .AFTER_WITH_REPEAT)

    _ = wrapper.reset()
    mock_sleep.assert_not_called()  # It should never sleep during reset().

    env.step.return_value = dm_env.termination(reward=None, observation=None)

    _ = wrapper.step({
        'action_type': np.array(action_type.ActionType.LIFT, dtype=np.uint8),
        'touch_position': np.array([0.123, 0.456])
    })

    # Second step call should be skipped.
    env.step.assert_called_once()
    mock_sleep.assert_not_called()


if __name__ == '__main__':
  absltest.main()
