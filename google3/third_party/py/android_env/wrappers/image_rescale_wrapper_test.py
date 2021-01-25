"""Tests for android_env.wrappers.image_rescale_wrapper."""

from typing import Any, Dict

from absl.testing import absltest
import android_env
from android_env.wrappers import image_rescale_wrapper
import dm_env
from dm_env import specs
import numpy as np


class FakeEnv(android_env.AndroidEnv):
  """A class that we can use to inject custom observations and specs."""

  def __init__(self, obs_spec):
    self._obs_spec = obs_spec
    self._next_obs = None

  def reset(self) -> dm_env.TimeStep:
    return self._next_timestep

  def step(self, action: Any) -> dm_env.TimeStep:
    return self._next_timestep

  def observation_spec(self) -> Dict[str, specs.Array]:
    return self._obs_spec

  def action_spec(self) -> Dict[str, specs.Array]:
    assert False, 'This should not be called by tests.'

  def set_next_timestep(self, timestep):
    self._next_timestep = timestep


def _simple_spec():
  return specs.Array(
      shape=np.array([300, 300, 3]), dtype=np.uint8, name='pixels')


def _simple_timestep():
  observation = np.ones(shape=[300, 300, 3])
  return dm_env.TimeStep(
      step_type=dm_env.StepType.MID,
      reward=3.14,
      discount=0.9,
      observation={'pixels': observation})


class ImageRescaleWrapperTest(absltest.TestCase):

  def test_100x50_grayscale(self):
    obs_spec = {'pixels': _simple_spec()}
    fake_env = FakeEnv(obs_spec)
    fake_env.set_next_timestep(_simple_timestep())

    wrapper = image_rescale_wrapper.ImageRescaleWrapper(
        fake_env, zoom_factors=(1.0 / 3, 1.0 / 6.0), grayscale=True)
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (100, 50, 1))
    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (100, 50, 1))
    step_timestep = wrapper.step(action='fake_action')
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (100, 50, 1))

  def test_150x60_full_channels(self):
    obs_spec = {'pixels': _simple_spec()}
    fake_env = FakeEnv(obs_spec)
    fake_env.set_next_timestep(_simple_timestep())

    wrapper = image_rescale_wrapper.ImageRescaleWrapper(
        fake_env, zoom_factors=(1.0 / 2.0, 1.0 / 5.0))
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (150, 60, 3))
    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (150, 60, 3))
    step_timestep = wrapper.step(action='fake_action')
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (150, 60, 3))

  def test_list_zoom_factor(self):
    obs_spec = {'pixels': _simple_spec()}
    fake_env = FakeEnv(obs_spec)
    fake_env.set_next_timestep(_simple_timestep())

    wrapper = image_rescale_wrapper.ImageRescaleWrapper(
        fake_env, zoom_factors=[0.5, 0.2])
    self.assertIsNotNone(wrapper)
    self.assertEqual(wrapper.observation_spec()['pixels'].shape, (150, 60, 3))
    reset_timestep = wrapper.reset()
    reset_image = reset_timestep.observation['pixels']
    self.assertEqual(reset_image.shape, (150, 60, 3))
    step_timestep = wrapper.step(action='fake_action')
    step_image = step_timestep.observation['pixels']
    self.assertEqual(step_image.shape, (150, 60, 3))

if __name__ == '__main__':
  absltest.main()
