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

"""Android environment implementation."""

from typing import Any, Dict
from absl import logging
from android_env.components import coordinator as coordinator_lib
import dm_env
import numpy as np


class AndroidEnv(dm_env.Environment):
  """An RL environment that interacts with Android apps."""

  def __init__(self, coordinator: coordinator_lib.Coordinator):
    """Initializes the state of this AndroidEnv object."""

    self._coordinator = coordinator
    self._latest_action = {}
    self._latest_observation = {}
    self._latest_extras = {}
    self._reset_next_step = True

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
    return self._latest_action

  @property
  def raw_observation(self):
    return self._latest_observation

  def android_logs(self) -> Dict[str, Any]:
    return self._coordinator.get_logs()

  def reset(self) -> dm_env.TimeStep:
    """Resets the environment for a new RL episode."""

    logging.info('Resetting AndroidEnv...')

    # Reset state of the environment.
    self._coordinator.reset_environment_state()

    # Execute selected action (None when resetting).
    obs, _, extras, _ = self._coordinator.execute_action(action=None)

    # Process relevant information.
    if obs is not None:
      self._latest_observation = obs.copy()
    self._latest_extras = extras.copy()
    self._latest_action = {}
    self._reset_next_step = False

    logging.info('Done resetting AndroidEnv.')
    logging.info('************* NEW EPISODE *************')

    return dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        observation=self._latest_observation,
        reward=0.0,
        discount=0.0)

  def step(self, action: Dict[str, np.ndarray]) -> dm_env.TimeStep:
    """Takes a step in the environment."""

    # Check if it's time to reset the episode.
    if self._reset_next_step:
      return self.reset()

    # Execute selected action.
    obs, reward, extras, episode_end = self._coordinator.execute_action(action)

    # Process relevant information.
    if obs is not None:
      self._latest_observation = obs.copy()
    self._latest_extras = extras.copy()
    self._latest_action = action.copy()
    self._reset_next_step = episode_end

    # Return timestep with reward and observation just computed.
    if episode_end:
      return dm_env.termination(
          observation=self._latest_observation, reward=reward)
    else:
      return dm_env.transition(
          observation=self._latest_observation, reward=reward, discount=0.0)

  def task_extras(self, latest_only: bool = True) -> Dict[str, np.ndarray]:
    """Returns latest task extras."""

    task_extras = {}
    for key, spec in self.task_extras_spec().items():
      if key in self._latest_extras:
        extra_values = self._latest_extras[key].astype(spec.dtype)
        for extra in extra_values:
          spec.validate(extra)
        task_extras[key] = extra_values[-1] if latest_only else extra_values
    return task_extras

  def close(self) -> None:
    """Cleans up running processes, threads and local files."""
    logging.info('Cleaning up AndroidEnv...')
    if hasattr(self, '_coordinator'):
      self._coordinator.close()
    logging.info('Done cleaning up AndroidEnv.')

  def __del__(self) -> None:
    self.close()
