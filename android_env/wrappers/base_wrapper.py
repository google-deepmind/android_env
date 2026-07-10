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

"""Base class for AndroidEnv wrappers."""

from typing import Any

from absl import logging
from android_env import env_interface
from android_env.proto import adb_pb2
from android_env.proto import state_pb2
import dm_env
from dm_env import specs
import numpy as np


class BaseWrapper(env_interface.AndroidEnvInterface):
  """AndroidEnv wrapper.

  Supports wrapping standard `dm_env.Environment` instances in addition to
  `AndroidEnvInterface` instances.
  """

  def __init__(self, env: dm_env.Environment) -> None:
    # `self._env` can be a standard `dm_env.Environment` or an
    # `AndroidEnvInterface`. We use the `|` operator to support both, and use
    # `hasattr` checks before calling AndroidEnv-specific methods that are not
    # present in standard `dm_env.Environment`.
    self._env: env_interface.AndroidEnvInterface | dm_env.Environment = env
    logging.info('Wrapping with %s', self.__class__.__name__)

  def reset(self) -> dm_env.TimeStep:
    self._reset_state()
    timestep = self._process_timestep(self._env.reset())
    return timestep

  def step(self, action: Any) -> dm_env.TimeStep:
    action = self._process_action(action)
    return self._process_timestep(self._env.step(action))

  def _get_env_attr(self, name: str) -> Any:
    """Safely gets an attribute from the wrapped environment."""
    if hasattr(self._env, name):
      return getattr(self._env, name)
    raise AttributeError(
        f'Underlying environment {type(self._env).__name__} does not have'
        f' attribute {name}.'
    )

  def _delegate_to_env(self, method_name: str, *args, **kwargs) -> Any:
    """Delegates to the underlying env if the method exists, else uses super()."""
    method = getattr(self._env, method_name, None)
    if method is not None and callable(method):
      return method(*args, **kwargs)
    # Fallback to super() to call the default AndroidEnvInterface implementation
    return getattr(super(), method_name)(*args, **kwargs)

  def task_extras(self, latest_only: bool = True) -> dict[str, np.ndarray]:
    return self._delegate_to_env('task_extras', latest_only=latest_only)

  def _reset_state(self):
    pass

  def _process_action(self, action: Any) -> Any:
    return action

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    return timestep

  def observation_spec(self) -> dict[str, specs.Array]:
    return self._env.observation_spec()

  def action_spec(self) -> dict[str, specs.Array]:
    return self._env.action_spec()

  def reward_spec(self) -> specs.Array:
    return self._env.reward_spec()

  def discount_spec(self) -> specs.Array:
    return self._env.discount_spec()

  def _wrapper_stats(self) -> dict[str, Any]:
    """Add wrapper specific logging here."""
    return {}

  def stats(self) -> dict[str, Any]:
    if hasattr(self._env, 'stats'):
      info = self._env.stats()
    else:
      info = super().stats()
    info.update(self._wrapper_stats())
    return info

  def load_state(
      self, request: state_pb2.LoadStateRequest
  ) -> state_pb2.LoadStateResponse:
    """Loads a state."""
    return self._delegate_to_env('load_state', request)

  def save_state(
      self, request: state_pb2.SaveStateRequest
  ) -> state_pb2.SaveStateResponse:
    """Saves a state.

    Args:
      request: A `SaveStateRequest` containing any parameters necessary to
        specify how/what state to save.

    Returns:
      A `SaveStateResponse` containing the status, error message (if
      applicable), and any other relevant information.
    """
    return self._delegate_to_env('save_state', request)

  def execute_adb_call(
      self, adb_call: adb_pb2.AdbRequest
  ) -> adb_pb2.AdbResponse:
    return self._delegate_to_env('execute_adb_call', adb_call)

  @property
  def raw_action(self) -> Any:
    return self._get_env_attr('raw_action')

  @property
  def raw_observation(self) -> Any:
    return self._get_env_attr('raw_observation')

  @property
  def raw_env(self) -> dm_env.Environment:
    """Recursively unwrap until we reach the true 'raw' env."""
    wrapped = self._env
    if hasattr(wrapped, 'raw_env'):
      return wrapped.raw_env
    return wrapped

  def __getattr__(self, attr) -> Any:
    """Delegate attribute access to underlying environment."""
    if attr in ('raw_action', 'raw_observation'):
      return self._get_env_attr(attr)
    return getattr(self._env, attr)

  def close(self) -> None:
    self._env.close()
