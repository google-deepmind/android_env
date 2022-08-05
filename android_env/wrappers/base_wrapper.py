# coding=utf-8
# Copyright 2022 DeepMind Technologies Limited.
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

"""Base class for AndroidEnv wrappers."""

from typing import Any, Dict

from absl import logging
from android_env import env_interface
from android_env.proto import adb_pb2
from android_env.proto import task_pb2
import dm_env
from dm_env import specs
import numpy as np


class BaseWrapper(env_interface.AndroidEnvInterface):
  """AndroidEnv wrapper."""

  def __init__(self, env):
    self._env = env
    logging.info('Wrapping with %s', self.__class__.__name__)

  def reset(self) -> dm_env.TimeStep:
    self._reset_state()
    timestep = self._process_timestep(self._env.reset())
    return timestep

  def step(self, action: Any) -> dm_env.TimeStep:
    action = self._process_action(action)
    return self._process_timestep(self._env.step(action))

  def task_extras(self, latest_only: bool = True) -> Dict[str, np.ndarray]:
    return self._env.task_extras(latest_only=latest_only)

  def _reset_state(self):
    pass

  def _process_action(self, action: Any) -> Any:
    return action

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    return timestep

  def observation_spec(self) -> Dict[str, specs.Array]:
    return self._env.observation_spec()

  def action_spec(self) -> Dict[str, specs.Array]:
    return self._env.action_spec()

  def task_extras_spec(self) -> Dict[str, specs.Array]:
    return self._env.task_extras_spec()

  def _wrapper_stats(self) -> Dict[str, Any]:
    """Add wrapper specific logging here."""
    return {}

  def stats(self) -> Dict[str, Any]:
    info = self._env.stats()
    info.update(self._wrapper_stats())
    return info

  def execute_adb_call(self,
                       adb_call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    return self._env.execute_adb_call(adb_call)

  def update_task(self, task: task_pb2.Task) -> bool:
    return self._env.update_task(task)

  @property
  def raw_action(self):
    return self._env.raw_action

  @property
  def raw_observation(self):
    return self._env.raw_observation

  @property
  def raw_env(self):
    """Recursively unwrap until we reach the true 'raw' env."""
    wrapped = self._env
    if hasattr(wrapped, 'raw_env'):
      return wrapped.raw_env
    return wrapped

  def __getattr__(self, attr):
    """Delegate attribute access to underlying environment."""
    return getattr(self._env, attr)

  def close(self):
    self._env.close()
