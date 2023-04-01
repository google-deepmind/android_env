# coding=utf-8
# Copyright 2023 DeepMind Technologies Limited.
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

"""Abstract AndroidEnv interface.

AndroidEnv is a standard dm_env.Environment instance, but it also offers a few
extra methods that clients may use for extended functionality.
"""

import abc
from typing import Any, Dict

from android_env.proto import adb_pb2
from android_env.proto import state_pb2
from android_env.proto import task_pb2
import dm_env
import numpy as np


class AndroidEnvInterface(dm_env.Environment, metaclass=abc.ABCMeta):
  """Pure virtual interface for AndroidEnv implementations."""

  # Methods required by dm_env.Environment.

  @abc.abstractmethod
  def action_spec(self) -> Dict[str, dm_env.specs.Array]:
    """Returns the action specification."""

  @abc.abstractmethod
  def observation_spec(self) -> Dict[str, dm_env.specs.Array]:
    """Returns the observation specification."""

  @abc.abstractmethod
  def reset(self) -> dm_env.TimeStep:
    """Resets the current episode."""

  @abc.abstractmethod
  def step(self, action: Dict[str, np.ndarray]) -> dm_env.TimeStep:
    """Executes `action` and returns a `TimeStep`."""

  def load_state(
      self, request: state_pb2.LoadStateRequest
  ) -> state_pb2.LoadStateResponse:
    """Loads a state.

    Args:
      request: A `LoadStateRequest` containing any parameters necessary to
        specify how/what state to load.

    Returns:
      A `LoadStateResponse` containing the status, error message (if
      applicable), and any other relevant information.
    """
    raise NotImplementedError('This environment does not support loading state')

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
    raise NotImplementedError('This environment does not support saving state')

  @abc.abstractmethod
  def close(self) -> None:
    """Frees up resources."""

  # Extensions provided by AndroidEnv.

  def task_extras(self, latest_only: bool = True) -> Dict[str, np.ndarray]:
    """Returns extra info provided by tasks."""

    return {}

  @property
  def raw_action(self):
    """Returns the latest action."""

  @property
  def raw_observation(self):
    """Returns the latest observation."""

  def stats(self) -> Dict[str, Any]:
    """Returns information generated inside the implementation."""

    return {}

  def execute_adb_call(self, call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    """Executes `call` and returns its response."""

    return adb_pb2.AdbResponse()

  def update_task(self, task: task_pb2.Task) -> bool:
    """Replaces the current task with a new task.

    It is the caller's responsibility to call `reset()` after the task update.

    Args:
      task: A new task to replace the current one.

    Returns:
      A bool indicating the success of the task setup.
    """

    return True
