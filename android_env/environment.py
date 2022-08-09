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

"""Android environment implementation."""

from typing import Any, Dict

from absl import logging
from android_env import env_interface
from android_env.components import coordinator as coordinator_lib
from android_env.proto import adb_pb2
from android_env.proto import task_pb2
import dm_env
import numpy as np


class AndroidEnv(env_interface.AndroidEnvInterface):
  """An RL environment that interacts with Android apps."""

  def __init__(self, coordinator: coordinator_lib.Coordinator):
    """Initializes the state of this AndroidEnv object."""

    self._coordinator = coordinator
    self._latest_action = {}
    self._latest_observation = {}
    self._latest_extras = {}
    self._reset_next_step = True
    self._is_closed = False

    logging.info('Action spec: %s', self.action_spec())
    logging.info('Observation spec: %s', self.observation_spec())
    logging.info('Task extras spec: %s', self.task_extras_spec())

  def action_spec(self) -> Dict[str, dm_env.specs.Array]:
    return self._coordinator.action_spec()

  def observation_spec(self) -> Dict[str, dm_env.specs.Array]:
    return self._coordinator.observation_spec()

  def task_extras_spec(self) -> Dict[str, dm_env.specs.Array]:
    return self._coordinator.task_extras_spec()

  @property
  def raw_action(self):
    return self._latest_action.copy()

  @property
  def raw_observation(self):
    return self._latest_observation.copy()

  def stats(self) -> Dict[str, Any]:
    return self._coordinator.stats()

  def reset(self) -> dm_env.TimeStep:
    """Resets the environment for a new RL episode."""

    logging.info('Resetting AndroidEnv...')

    # Execute a reset. Timestep will be of type FIRST.
    timestep = self._coordinator.rl_reset()

    # Process relevant information.
    if timestep.observation is not None:
      self._latest_extras = timestep.observation.pop('extras')
      self._latest_observation = timestep.observation.copy()
    else:
      # If the observation is None, we return the latest observation again.
      timestep = timestep._replace(observation=self._latest_observation.copy())

    self._latest_action = {}
    self._reset_next_step = False

    logging.info('Done resetting AndroidEnv.')
    logging.info('************* NEW EPISODE *************')

    return timestep

  def step(self, action: Dict[str, np.ndarray]) -> dm_env.TimeStep:
    """Takes a step in the environment."""

    # Check if it's time to reset the episode.
    if self._reset_next_step:
      return self.reset()

    # Execute selected action.
    timestep = self._coordinator.rl_step(action)

    # Process relevant information.
    if timestep.observation is not None:
      self._latest_extras = timestep.observation.pop('extras')
      self._latest_observation = timestep.observation.copy()
    else:
      # If the observation is None, we return the latest observation again.
      timestep = timestep._replace(observation=self._latest_observation.copy())

    self._latest_action = action.copy()

    if timestep.last():
      self._reset_next_step = True
      logging.info('************* END OF EPISODE *************')

    return timestep

  def task_extras(self, latest_only: bool = True) -> Dict[str, np.ndarray]:
    """Returns latest task extras."""

    task_extras = {}
    for key, spec in self.task_extras_spec().items():
      if key in self._latest_extras:
        extra_values = self._latest_extras[key].astype(spec.dtype)
        task_extras[key] = extra_values[-1] if latest_only else extra_values
    return task_extras

  def execute_adb_call(self, call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    return self._coordinator.execute_adb_call(call)

  def update_task(self, task: task_pb2.Task) -> bool:
    """Replaces the current task with a new task.

    Args:
      task: A new task to replace the current one.

    Returns:
      A bool indicating the success of the task setup.
    """
    return self._coordinator.update_task(task)

  def close(self) -> None:
    """Cleans up running processes, threads and local files."""
    if not self._is_closed:
      logging.info('Cleaning up AndroidEnv...')
      if hasattr(self, '_coordinator'):
        self._coordinator.close()
      logging.info('Done cleaning up AndroidEnv.')
      self._is_closed = True

  def __del__(self) -> None:
    self.close()
