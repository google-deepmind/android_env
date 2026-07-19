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

"""Tests for android_env.wrappers.trajectory_recorder_wrapper."""

import pathlib
from unittest import mock

from absl.testing import absltest
from android_env import env_interface
from android_env.components import action_type
from android_env.wrappers import trajectory_recorder_wrapper
import dm_env
from dm_env import specs
import numpy as np


def _fake_env():
  env = mock.create_autospec(env_interface.AndroidEnvInterface)
  env.action_spec.return_value = {
      'action_type':
          specs.DiscreteArray(
              num_values=len(action_type.ActionType), name='action_type'),
      'touch_position':
          specs.BoundedArray(
              shape=(2,),
              dtype=np.float32,
              minimum=[0.0, 0.0],
              maximum=[1.0, 1.0],
              name='touch_position'),
  }
  return env


def _timestep(step_type, reward=None, discount=None, pixel_value=0):
  return dm_env.TimeStep(
      step_type=step_type,
      reward=reward,
      discount=discount,
      observation={
          'pixels': np.full((4, 4, 3), pixel_value, dtype=np.uint8),
      })


def _action(x):
  return {
      'action_type': np.array(action_type.ActionType.TOUCH, dtype=np.int32),
      'touch_position': np.array([x, x], dtype=np.float32),
  }


class TrajectoryRecorderWrapperTest(absltest.TestCase):

  def test_records_full_episode_to_a_single_file(self):
    record_dir = self.create_tempdir().full_path
    env = _fake_env()
    env.reset.return_value = _timestep(dm_env.StepType.FIRST)
    env.step.side_effect = [
        _timestep(dm_env.StepType.MID, reward=1.0, discount=1.0,
                  pixel_value=1),
        _timestep(dm_env.StepType.LAST, reward=2.0, discount=0.0,
                  pixel_value=2),
    ]

    wrapper = trajectory_recorder_wrapper.TrajectoryRecorderWrapper(
        env, record_dir=record_dir)
    wrapper.reset()
    wrapper.step(_action(0.25))
    wrapper.step(_action(0.75))

    files = sorted(pathlib.Path(record_dir).glob('*.npz'))
    self.assertLen(files, 1)
    self.assertEqual(files[0].name, 'episode_000000.npz')

    with np.load(files[0]) as data:
      self.assertEqual(data['step_type'].tolist(), [
          dm_env.StepType.FIRST, dm_env.StepType.MID, dm_env.StepType.LAST
      ])
      np.testing.assert_allclose(data['reward'], [0.0, 1.0, 2.0])
      np.testing.assert_allclose(data['discount'], [0.0, 1.0, 0.0])
      self.assertEqual(data['observation.pixels'].shape, (3, 4, 4, 3))
      np.testing.assert_array_equal(
          data['observation.pixels'][:, 0, 0, 0], [0, 1, 2])

      # The initial (reset) observation had no preceding action, so it should
      # be padded with a zero-valued action.
      self.assertEqual(data['action.touch_position'].shape, (3, 2))
      np.testing.assert_allclose(data['action.touch_position'][0], [0.0, 0.0])
      np.testing.assert_allclose(data['action.touch_position'][1], [0.25, 0.25])
      np.testing.assert_allclose(data['action.touch_position'][2], [0.75, 0.75])

  def test_separate_episodes_get_separate_files(self):
    record_dir = self.create_tempdir().full_path
    env = _fake_env()
    env.reset.side_effect = [
        _timestep(dm_env.StepType.FIRST),
        _timestep(dm_env.StepType.FIRST),
    ]
    env.step.return_value = _timestep(dm_env.StepType.LAST, reward=1.0)

    wrapper = trajectory_recorder_wrapper.TrajectoryRecorderWrapper(
        env, record_dir=record_dir)
    wrapper.reset()
    wrapper.step(_action(0.1))
    wrapper.reset()
    wrapper.step(_action(0.2))

    files = sorted(
        f.name for f in pathlib.Path(record_dir).glob('*.npz'))
    self.assertEqual(files, ['episode_000000.npz', 'episode_000001.npz'])

  def test_close_flushes_incomplete_episode(self):
    record_dir = self.create_tempdir().full_path
    env = _fake_env()
    env.reset.return_value = _timestep(dm_env.StepType.FIRST)
    env.step.return_value = _timestep(dm_env.StepType.MID, reward=1.0)

    wrapper = trajectory_recorder_wrapper.TrajectoryRecorderWrapper(
        env, record_dir=record_dir)
    wrapper.reset()
    wrapper.step(_action(0.5))

    self.assertEmpty(list(pathlib.Path(record_dir).glob('*.npz')))
    wrapper.close()
    self.assertLen(list(pathlib.Path(record_dir).glob('*.npz')), 1)
    env.close.assert_called_once()

  def test_no_file_written_when_no_steps_taken(self):
    record_dir = self.create_tempdir().full_path
    env = _fake_env()

    wrapper = trajectory_recorder_wrapper.TrajectoryRecorderWrapper(
        env, record_dir=record_dir)
    wrapper.close()

    self.assertEmpty(list(pathlib.Path(record_dir).glob('*.npz')))

  def test_creates_record_dir_if_missing(self):
    record_dir = pathlib.Path(self.create_tempdir().full_path) / 'nested'
    env = _fake_env()

    trajectory_recorder_wrapper.TrajectoryRecorderWrapper(
        env, record_dir=record_dir)

    self.assertTrue(record_dir.is_dir())


if __name__ == '__main__':
  absltest.main()
