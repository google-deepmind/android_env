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

"""Wraps the AndroidEnv environment to provide discrete actions."""

from collections.abc import Sequence

from android_env.components import action_type
from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import numpy as np


_NOISE_CLIP_VALUE = 0.4999


class DiscreteActionWrapper(base_wrapper.BaseWrapper):
  """AndroidEnv with discrete actions."""

  def __init__(
      self,
      env: dm_env.Environment,
      action_grid: Sequence[int] = (10, 10),
      redundant_actions: bool = True,
      noise: float = 0.1,
  ):
    super().__init__(env)
    self._parent_action_spec = self._env.action_spec()
    self._assert_base_env()
    self._action_grid = action_grid  # [height, width]
    self._grid_size = np.prod(self._action_grid)
    self._num_action_types = self._parent_action_spec['action_type'].num_values
    self._redundant_actions = redundant_actions
    self._noise = noise

  def _assert_base_env(self):
    """Checks that the wrapped env has the right action spec format."""

    assert len(self._parent_action_spec) == 2
    assert not self._parent_action_spec['action_type'].shape
    assert self._parent_action_spec['touch_position'].shape == (2,)

  @property
  def num_actions(self) -> int:
    """Number of discrete actions."""

    if self._redundant_actions:
      return self._grid_size * self._num_action_types
    else:
      return self._grid_size + self._num_action_types - 1

  def step(self, action: dict[str, int]) -> dm_env.TimeStep:
    """Take a step in the base environment."""

    return self._env.step(self._process_action(action))

  def _process_action(self, action: dict[str, int]) -> dict[str, np.ndarray]:
    """Transforms action so that it agrees with AndroidEnv's action spec."""

    return {
        'action_type':
            np.array(self._get_action_type(action['action_id']),
                     dtype=self._parent_action_spec['action_type'].dtype),
        'touch_position':
            np.array(self._get_touch_position(action['action_id']),
                     dtype=self._parent_action_spec['touch_position'].dtype)
    }

  def _get_action_type(self, action_id: int) -> action_type.ActionType:
    """Compute action type corresponding to the given action_id.

    When `self._redundant_actions` == True the `grid_size` is "broadcast" over
    all the possible actions so you end up with `grid_size` discrete actions
    of type 0, `grid_size` discrete actions of type 1, etc. for all action
    types.

    When `self._redundant_actions` == False the first `grid_size` actions are
    reserved for "touch" and the rest are just added (NOT multiplied) to the
    total number of discrete actions (exactly one of LIFT and REPEAT).

    Args:
      action_id: A discrete action.
    Returns:
      action_type: The action_type of the action.
    """

    if self._redundant_actions:
      assert action_id < self._num_action_types * self._grid_size
      return action_id // self._grid_size

    else:
      assert action_id <= self._grid_size + 1
      if action_id < self._grid_size:
        return action_type.ActionType.TOUCH
      elif action_id == self._grid_size:
        return action_type.ActionType.LIFT
      else:
        return action_type.ActionType.REPEAT

  def _get_touch_position(self, action_id: int) -> Sequence[float]:
    """Compute the position corresponding to the given action_id.

    Note: in the touch_position (x, y) of an action, x corresponds to the
    horizontal axis (width), and y corresponds to the vertical axis (height)
    of the screen. BUT, the screen has dimensions (height, width), i.e. the
    first coordinate corresponds to y, and the second coordinate corresponds
    to x. Pay attention to this mismatch in the calculations below.

    Args:
      action_id: A discrete action.
    Returns:
      touch_position: The [0,1]x[0,1] coordinate of the action.
    """

    position_idx = action_id % self._grid_size

    x_pos_grid = position_idx % self._action_grid[1]  # WIDTH
    y_pos_grid = position_idx // self._action_grid[1]  # HEIGHT

    noise_x = np.random.normal(loc=0.0, scale=self._noise)
    noise_y = np.random.normal(loc=0.0, scale=self._noise)

    # Noise is clipped so that the action will strictly stay in the cell.
    noise_x = max(min(noise_x, _NOISE_CLIP_VALUE), -_NOISE_CLIP_VALUE)
    noise_y = max(min(noise_y, _NOISE_CLIP_VALUE), -_NOISE_CLIP_VALUE)

    x_pos = (x_pos_grid + 0.5 + noise_x) / self._action_grid[1]  # WIDTH
    y_pos = (y_pos_grid + 0.5 + noise_y) / self._action_grid[0]  # HEIGHT

    # Project action space to action_spec ranges. For the default case of
    # minimum = [0, 0] and maximum = [1, 1], this will not do anything.
    x_min, y_min = self._parent_action_spec['touch_position'].minimum
    x_max, y_max = self._parent_action_spec['touch_position'].maximum

    x_pos = x_min + x_pos * (x_max - x_min)
    y_pos = y_min + y_pos * (y_max - y_min)

    return [x_pos, y_pos]

  def action_spec(self) -> dict[str, specs.Array]:
    """Action spec of the wrapped environment."""

    return {
        'action_id':
            specs.DiscreteArray(
                num_values=self.num_actions,
                name='action_id')
    }
