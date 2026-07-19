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

"""Records full episode trajectories to disk."""

import os
import pathlib
from typing import Any

from absl import logging
from android_env import env_interface
from android_env.wrappers import base_wrapper
import dm_env
import numpy as np


class TrajectoryRecorderWrapper(base_wrapper.BaseWrapper):
  """Records (observation, action, reward, discount) trajectories to disk.

  This wrapper does not alter observations, actions or rewards in any way; it
  only observes them as they pass through and writes each completed episode to
  its own compressed `.npz` file under `record_dir`. It is intended for
  collecting human demonstrations (e.g. via `run_human_agent.py`) or agent
  rollouts to be used downstream for imitation learning or reward-model
  training, such as a data-collection step for RLHF. This wrapper itself does
  not implement any training or learning algorithm.

  Each `.npz` file contains one stacked array per observation field (keyed as
  `observation.<name>`), one per action field (keyed as `action.<name>`), and
  `step_type`, `reward`, `discount` arrays, all sharing the same leading
  (time) dimension. The initial observation from `reset()` has no preceding
  agent action, so it is paired with a zero-valued action.
  """

  def __init__(
      self,
      env: env_interface.AndroidEnvInterface,
      record_dir: str | os.PathLike[str],
      episode_prefix: str = 'episode',
  ) -> None:
    """Initializes this wrapper.

    Args:
      env: The environment to wrap.
      record_dir: Directory where episode trajectories will be written. It
        will be created if it does not already exist.
      episode_prefix: Filename prefix used for each recorded episode.
    """
    super().__init__(env)
    self._record_dir = pathlib.Path(record_dir)
    self._record_dir.mkdir(parents=True, exist_ok=True)
    self._episode_prefix = episode_prefix
    self._episode_count = 0
    self._steps: list[dict[str, Any]] = []
    self._pending_action: dict[str, np.ndarray] | None = None

  def _reset_state(self) -> None:
    self._flush_episode()
    self._pending_action = None

  def _process_action(self, action: dict[str, np.ndarray]) -> Any:
    self._pending_action = action
    return action

  def _process_timestep(self, timestep: dm_env.TimeStep) -> dm_env.TimeStep:
    self._steps.append({
        'step_type': np.int32(timestep.step_type),
        'reward': np.float32(timestep.reward or 0.0),
        'discount': np.float32(timestep.discount or 0.0),
        'observation': timestep.observation,
        'action': self._pending_action,
    })
    self._pending_action = None
    if timestep.last():
      self._flush_episode()
    return timestep

  def _zero_action(self) -> dict[str, np.ndarray]:
    return {
        name: np.zeros(spec.shape, dtype=spec.dtype)
        for name, spec in self._env.action_spec().items()
    }

  def _flush_episode(self) -> None:
    """Writes the currently buffered episode (if any) to disk."""
    if not self._steps:
      return

    zero_action = self._zero_action()
    arrays: dict[str, np.ndarray] = {
        'step_type': np.stack([s['step_type'] for s in self._steps]),
        'reward': np.stack([s['reward'] for s in self._steps]),
        'discount': np.stack([s['discount'] for s in self._steps]),
    }
    for key in self._steps[0]['observation']:
      arrays[f'observation.{key}'] = np.stack(
          [s['observation'][key] for s in self._steps])
    for key in zero_action:
      arrays[f'action.{key}'] = np.stack(
          [(s['action'] or zero_action)[key] for s in self._steps])

    filename = (
        self._record_dir
        / f'{self._episode_prefix}_{self._episode_count:06d}.npz'
    )
    np.savez_compressed(filename, **arrays)
    logging.info(
        'Wrote %d-step trajectory to %s.', len(self._steps), filename)

    self._episode_count += 1
    self._steps = []

  def close(self) -> None:
    self._flush_episode()
    super().close()
