"""Wraps the AndroidEnv to expose an OpenAI Gym interface."""

from typing import Any, Dict, Tuple

from android_env.wrappers import base_wrapper
import dm_env
from dm_env import specs
import gym
from gym import spaces
import numpy as np


class GymInterfaceWrapper(base_wrapper.BaseWrapper, gym.Env):
  """AndroidEnv with discrete actions."""

  def __init__(self, env: dm_env.Environment):

    base_wrapper.BaseWrapper.__init__(self, env)
    self.spec = None
    self.action_space = self._spec_to_space(self._env.action_spec())
    self.observation_space = self._spec_to_space(self._env.observation_spec())
    self.metadata = {'render.modes': ['rgb_array']}

  def _spec_to_space(self, spec: specs.Array) -> spaces.Space:
    """Converts dm_env specs to OpenAI Gym spaces."""

    if isinstance(spec, list):
      return spaces.Tuple([self._spec_to_space(s) for s in spec])

    if isinstance(spec, dict):
      return spaces.Dict(
          {name: self._spec_to_space(s) for name, s in spec.items()})

    if isinstance(spec, specs.DiscreteArray):
      return spaces.Box(
          shape=(),
          dtype=spec.dtype,
          low=0,
          high=spec.num_values-1)

    if isinstance(spec, specs.BoundedArray):
      return spaces.Box(
          shape=spec.shape,
          dtype=spec.dtype,
          low=spec.minimum,
          high=spec.maximum)

    if isinstance(spec, specs.Array):
      return spaces.Box(
          shape=spec.shape,
          dtype=spec.dtype,
          low=-np.inf,
          high=np.inf)

    raise ValueError('Unknown type for specs: {}'.format(spec))

  def render(self, mode='rgb_array'):
    """Renders the environment."""
    if mode == 'rgb_array':
      if self._latest_observation is None:
        return
      return self._latest_observation['pixels']
    else:
      raise ValueError('Only supported render mode is rgb_array.')

  def reset(self) -> np.ndarray:
    timestep = self._env.reset()
    return timestep.observation

  def step(self, action: Dict[str, int]) -> Tuple[Any, ...]:
    """Take a step in the base environment."""
    timestep = self._env.step(self._process_action(action))
    observation = timestep.observation
    reward = timestep.reward
    done = timestep.step_type == dm_env.StepType.LAST
    info = {'discount': timestep.discount}
    return observation, reward, done, info
