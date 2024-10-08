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

"""Android environment implementation."""

from typing import Any

from absl import logging
from android_env import env_interface
from android_env.components import adb_call_parser
from android_env.components import coordinator as coordinator_lib
from android_env.components import task_manager as task_manager_lib
from android_env.components.simulators import base_simulator
from android_env.proto import adb_pb2
from android_env.proto import state_pb2
import dm_env
import numpy as np


class AndroidEnv(env_interface.AndroidEnvInterface):
  """An RL environment that interacts with Android apps."""

  def __init__(
      self,
      simulator: base_simulator.BaseSimulator,
      coordinator: coordinator_lib.Coordinator,
      task_manager: task_manager_lib.TaskManager,
  ):
    """Initializes the state of this AndroidEnv object."""

    self._simulator = simulator
    self._coordinator = coordinator
    self._task_manager = task_manager
    self._latest_action = {}
    self._latest_observation = {}
    self._latest_extras = {}
    self._reset_next_step = True
    self._is_closed = False

    logging.info('Action spec: %s', self.action_spec())
    logging.info('Observation spec: %s', self.observation_spec())

  def __del__(self) -> None:
    self.close()

  # Methods required by dm_env.Environment.

  def action_spec(self) -> dict[str, dm_env.specs.Array]:
    return self._coordinator.action_spec()

  def observation_spec(self) -> dict[str, dm_env.specs.Array]:
    return self._coordinator.observation_spec()

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

  def step(self, action: dict[str, np.ndarray]) -> dm_env.TimeStep:
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

  def close(self) -> None:
    """Cleans up running processes, threads and local files."""
    if not self._is_closed:
      logging.info('Cleaning up AndroidEnv...')
      if hasattr(self, '_coordinator'):
        self._coordinator.close()
      logging.info('Done cleaning up AndroidEnv.')
      self._is_closed = True

  # Extensions provided by AndroidEnv.

  def task_extras(self, latest_only: bool = True) -> dict[str, np.ndarray]:
    """Returns latest task extras."""

    task_extras = {}  # Build a copy to avoid reusing objects.
    for k, spec in self._latest_extras.items():
      extra_values = spec.astype(spec.dtype)
      task_extras[k] = extra_values[-1] if latest_only else extra_values
    return task_extras

  @property
  def raw_action(self):
    return self._latest_action.copy()

  @property
  def raw_observation(self):
    return self._latest_observation.copy()

  def stats(self) -> dict[str, Any]:
    coordinator_stats = self._coordinator.stats()
    task_manager_stats = self._task_manager.stats()
    return coordinator_stats | task_manager_stats

  def execute_adb_call(self, call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    return self._coordinator.execute_adb_call(call)

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

    self._task_manager.stop()
    response = self._simulator.load_state(request)
    self._task_manager.start(
        adb_call_parser_factory=lambda: adb_call_parser.AdbCallParser(
            self._simulator.create_adb_controller()
        ),
        log_stream=self._simulator.create_log_stream(),
    )
    return response

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

    return self._simulator.save_state(request)
