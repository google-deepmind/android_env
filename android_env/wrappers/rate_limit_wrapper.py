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

"""Limits interactions with the environment to a given rate."""

import enum
import time

from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import base_wrapper
import dm_env
import numpy as np


class RateLimitWrapper(base_wrapper.BaseWrapper):
  """Limits interactions with the environment to a given rate."""

  class SleepType(enum.IntEnum):
    """Determines how the wrapper interacts with the underlying environment."""

    # The wrapper sleeps before calling `step()` on the underlying environment.
    BEFORE = 0

    # The wrapper sleeps after calling `step()` on the underlying environment.
    AFTER = 1

    # The wrapper first calls `step()`, obtaining a TimeStep which is ignored,
    # then it sleeps, and then it calls `step(REPEAT)` to obtain a TimeStep
    # that's as fresh as possible.
    #
    # Note that for both BEFORE and AFTER_WITH_REPEAT, the _total_ amount of
    # time inside this wrapper may go beyond the rate specified in `rate`
    # because the sleep does not account for the time taken by step().
    AFTER_WITH_REPEAT = 2

  def __init__(self,
               env: env_interface.AndroidEnvInterface,
               rate: float,
               sleep_type: SleepType = SleepType.AFTER_WITH_REPEAT):
    """Initializes this wrapper.

    Args:
      env: The underlying environment to which this wrapper is applied.
      rate: The desired rate in Hz to interact with the environment. If <=0.0,
        this wrapper will be disabled.
      sleep_type: This determines how the wrapper will interact with the
        underlying AndroidEnv environment.
    """
    super().__init__(env)
    self._assert_base_env()
    self._last_step_time = None
    self._max_wait = 1.0 / rate if rate > 0.0 else 0.0
    self._sleep_type = sleep_type

  def _assert_base_env(self):
    """Checks that the wrapped env has the right action spec format."""
    parent_action_spec = self._env.action_spec()
    assert len(parent_action_spec) == 2
    assert not parent_action_spec['action_type'].shape
    assert parent_action_spec['touch_position'].shape == (2,)

  def reset(self):
    timestep = self._env.reset()
    self._last_step_time = time.time()
    return timestep

  def step(self, action: dict[str, np.ndarray]) -> dm_env.TimeStep:
    """Takes a step while maintaining a steady interaction rate."""

    # If max_wait is non-positive, the wrapper has no effect.
    if self._max_wait <= 0.0:
      return self._env.step(action)

    if self._sleep_type == RateLimitWrapper.SleepType.BEFORE:
      self._wait()

    timestep = self._env.step(action)
    if timestep.last():
      return timestep

    if self._sleep_type == RateLimitWrapper.SleepType.AFTER_WITH_REPEAT:
      for k in action.keys():
        if k.startswith('action_type'):
          action[k] = np.array(action_type.ActionType.REPEAT, dtype=np.uint8)
      self._wait()
      first_reward = timestep.reward or 0.0
      timestep = self._env.step(action)
      second_reward = timestep.reward or 0.0
      # Accumulate rewards over the two steps taken.
      timestep = timestep._replace(reward=first_reward + second_reward)

    elif self._sleep_type == RateLimitWrapper.SleepType.AFTER:
      self._wait()

    self._last_step_time = time.time()

    return timestep

  def _wait(self) -> None:
    if self._max_wait > 0.0 and self._last_step_time is not None:
      time_since_step = time.time() - self._last_step_time
      sec_to_wait = self._max_wait - time_since_step
      if sec_to_wait > 0.0:
        time.sleep(sec_to_wait)
