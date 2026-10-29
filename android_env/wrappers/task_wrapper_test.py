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

"""Tests for TaskWrapper environment wrapper."""

import threading
from unittest import mock

from absl.testing import absltest
from android_env import env_interface
from android_env.proto import adb_pb2
from android_env.proto import task_pb2
from android_env.rl import fake_log_stream
from android_env.wrappers import task_wrapper
import dm_env
import numpy as np


class TaskWrapperTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._thread_exceptions = []
    self._orig_excepthook = threading.excepthook

    def _excepthook(args):
      self._thread_exceptions.append(args)
      self._orig_excepthook(args)

    threading.excepthook = _excepthook
    self.base_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    self.base_env.task_extras.return_value = {}
    self.base_env.stats.return_value = {}
    self.fake_log_stream = fake_log_stream.FakeLogStream()
    self.task = task_pb2.Task(
        name='test_task',
        max_episode_steps=5,
    )

  def tearDown(self):
    threading.excepthook = self._orig_excepthook
    self.assertEmpty(self._thread_exceptions)
    self.assertEqual(threading.active_count(), 1)
    super().tearDown()

  def test_reset_and_step_with_default_log_stream(self):
    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={'pixels': np.zeros((10, 10, 3), dtype=np.uint8)},
    )
    self.base_env.step.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=0.0,
        discount=1.0,
        observation={'pixels': np.ones((10, 10, 3), dtype=np.uint8)},
    )

    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
    )

    ts_reset = wrapper.reset()
    self.assertEqual(ts_reset.step_type, dm_env.StepType.FIRST)
    self.assertNotIn('extras', ts_reset.observation)
    self.base_env.reset.assert_called_once()

    ts_step = wrapper.step({'action_type': 0})
    self.assertEqual(ts_step.step_type, dm_env.StepType.MID)
    self.assertNotIn('extras', ts_step.observation)
    self.base_env.step.assert_called_once()

    wrapper.close()

  def test_device_signal_logs_compute_rewards_and_task_extras(self):
    self.task.log_parsing_config.log_regexps.score = r'^Score: ([-+]?[0-9]+)$'
    self.task.log_parsing_config.log_regexps.reward.append(
        r'^Bonus: ([-+]?[0-9]+)$'
    )
    self.task.log_parsing_config.log_regexps.extra.append(
        r'^Extra (?P<name>\w+): (?P<extra>.*)$'
    )
    self.task.log_parsing_config.log_regexps.episode_end.append(r'^GAME_OVER$')

    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={'pixels': np.zeros((10, 10, 3), dtype=np.uint8)},
    )
    self.base_env.step.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=0.0,
        discount=1.0,
        observation={'pixels': np.ones((10, 10, 3), dtype=np.uint8)},
    )
    reset_logs = [
        '07-26 12:00:00.123  100  200 I Game: Score: 10',
        '07-26 12:00:00.124  100  200 I Game: Extra reset_extra: 1',
    ]
    step_logs = [
        '07-26 12:00:01.000  100  200 I Game: Score: 25',
        '         1553110400.424  100  200 I Game: Bonus: 5',
        'Extra level: 2',
        'Extra level: 3',
        'GAME_OVER',
    ]
    active_logs = [reset_logs]

    def _fake_task_extras(latest_only: bool = True):
      logs = active_logs[0]
      return {
          'logs': logs[-1] if latest_only else logs,
          'battery_power': {'level_percent': 90},
      }

    self.base_env.task_extras.side_effect = _fake_task_extras

    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
    )

    wrapper.reset()
    self.assertEqual(wrapper.task_extras(latest_only=True)['reset_extra'], 1)

    active_logs[0] = step_logs
    ts_step = wrapper.step({'action_type': 0})

    self.assertEqual(ts_step.step_type, dm_env.StepType.LAST)
    self.assertEqual(ts_step.reward, 30.0)

    latest_extras = wrapper.task_extras(latest_only=True)
    self.assertEqual(latest_extras['battery_power'], {'level_percent': 90})
    self.assertEqual(latest_extras['level'], 3)

    all_extras = wrapper.task_extras(latest_only=False)
    np.testing.assert_array_equal(all_extras['level'], np.array([2, 3]))

    wrapper.close()

  def test_step_before_reset_or_after_episode_end_triggers_reset(self):
    self.task.max_episode_steps = 1
    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={'pixels': np.zeros((10, 10, 3), dtype=np.uint8)},
    )
    self.base_env.step.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=0.0,
        discount=1.0,
        observation={'pixels': np.ones((10, 10, 3), dtype=np.uint8)},
    )

    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
        log_stream=self.fake_log_stream,
    )

    # First step() before explicit reset() automatically calls reset().
    ts_first = wrapper.step({'action_type': 0})
    self.assertEqual(ts_first.step_type, dm_env.StepType.FIRST)
    self.assertEqual(self.base_env.reset.call_count, 1)

    # First real step is within max_episode_steps=1 (MID).
    ts_mid = wrapper.step({'action_type': 0})
    self.assertEqual(ts_mid.step_type, dm_env.StepType.MID)

    # Second real step exceeds max_episode_steps=1 (LAST).
    ts_last = wrapper.step({'action_type': 0})
    self.assertEqual(ts_last.step_type, dm_env.StepType.LAST)

    # Subsequent step() automatically resets the environment.
    ts_auto_reset = wrapper.step({'action_type': 0})
    self.assertEqual(ts_auto_reset.step_type, dm_env.StepType.FIRST)
    self.assertEqual(self.base_env.reset.call_count, 2)

    wrapper.close()

  def test_rewards_and_task_extras_from_custom_log_stream(self):
    self.task.log_parsing_config.log_regexps.reward.append(
        r'^Bonus: ([-+]?[0-9]+)$'
    )
    self.task.log_parsing_config.log_regexps.extra.append(
        r'^Extra (?P<name>\w+): (?P<extra>.*)$'
    )
    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={'pixels': np.zeros((10, 10, 3), dtype=np.uint8)},
    )
    self.base_env.step.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=0.0,
        discount=1.0,
        observation={'pixels': np.ones((10, 10, 3), dtype=np.uint8)},
    )
    self.base_env.task_extras.return_value = {
        'battery_power': {'level_percent': 90},
        'logs': ['Bonus: 100'],
    }

    ready_to_emit = threading.Event()
    logs_processed = threading.Event()

    def _log_gen():
      ready_to_emit.wait(timeout=5.0)
      yield '         0.000     1     1 I Game: Bonus: 5'
      yield '         0.000     1     1 I Game: Extra level: 2'
      yield '         0.000     1     1 I Game: Extra level: 3'
      logs_processed.set()

    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
        log_stream=fake_log_stream.FakeLogStream(log_generator=_log_gen()),
    )

    wrapper.reset()
    ready_to_emit.set()
    self.assertTrue(logs_processed.wait(timeout=5.0))

    ts_step = wrapper.step({'action_type': 0})

    self.assertEqual(ts_step.reward, 5.0)
    latest_extras = wrapper.task_extras(latest_only=True)
    self.assertEqual(latest_extras['battery_power'], {'level_percent': 90})
    self.assertEqual(latest_extras['level'], 3)

    all_extras = wrapper.task_extras(latest_only=False)
    np.testing.assert_array_equal(all_extras['level'], np.array([2, 3]))

    wrapper.close()

  def test_adb_call_delegation_runs_setup_steps_only_once(self):
    self.task.setup_steps.add(
        adb_request=adb_pb2.AdbRequest(
            press_button=adb_pb2.AdbRequest.PressButton(
                button=adb_pb2.AdbRequest.PressButton.Button.HOME
            )
        )
    )
    self.base_env.execute_adb_call.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK
    )
    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={'pixels': np.zeros((10, 10, 3), dtype=np.uint8)},
    )

    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
        log_stream=self.fake_log_stream,
    )

    wrapper.reset()
    wrapper.reset()
    self.base_env.execute_adb_call.assert_called_once()
    wrapper.close()

  def test_stats(self):
    self.base_env.stats.return_value = {'env_stat': 42}
    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={'pixels': np.zeros((10, 10, 3), dtype=np.uint8)},
    )

    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
        log_stream=self.fake_log_stream,
    )

    self.assertEqual(wrapper.stats(), {'env_stat': 42})

    wrapper.reset()
    stats = wrapper.stats()
    self.assertIn('env_stat', stats)
    self.assertIn('episode_steps', stats)
    wrapper.close()
    self.assertEqual(wrapper.stats(), {'env_stat': 42})

  def test_active_package_exit_truncates_and_auto_resets(self):
    self.task.expected_app_screen.activity = 'com.example.game/.MainActivity'
    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={
            'pixels': np.zeros((10, 10, 3), dtype=np.uint8),
            'active_package': 'com.example.game',
        },
    )
    self.base_env.step.side_effect = [
        dm_env.TimeStep(
            step_type=dm_env.StepType.MID,
            reward=0.0,
            discount=1.0,
            observation={
                'pixels': np.ones((10, 10, 3), dtype=np.uint8),
                'active_package': 'com.example.game',
            },
        ),
        dm_env.TimeStep(
            step_type=dm_env.StepType.MID,
            reward=0.0,
            discount=1.0,
            observation={
                'pixels': np.ones((10, 10, 3), dtype=np.uint8),
                'active_package': 'com.android.launcher3',
            },
        ),
    ]

    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
        log_stream=self.fake_log_stream,
    )

    wrapper.reset()
    ts_in_app = wrapper.step({'action_type': 0})
    self.assertEqual(ts_in_app.step_type, dm_env.StepType.MID)
    self.assertEqual(wrapper.stats()['reset_count_user_exited'], 0)

    ts_exited = wrapper.step({'action_type': 0})
    self.assertEqual(ts_exited.step_type, dm_env.StepType.LAST)
    self.assertEqual(wrapper.stats()['reset_count_user_exited'], 1)
    self.base_env.execute_adb_call.assert_not_called()

    wrapper.close()

  def test_stop_task_stops_task_manager_without_closing_base_env(self):
    self.base_env.reset.return_value = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=None,
        discount=None,
        observation={'pixels': np.zeros((10, 10, 3), dtype=np.uint8)},
    )
    self.base_env.stats.return_value = {'env_stat': 7}
    wrapper = task_wrapper.TaskWrapper(
        env=self.base_env,
        task=self.task,
        log_stream=self.fake_log_stream,
    )
    wrapper.reset()
    self.assertIn('episode_steps', wrapper.stats())

    wrapper.stop_task()
    self.assertEqual(wrapper.stats(), {'env_stat': 7})
    self.base_env.close.assert_not_called()


if __name__ == '__main__':
  absltest.main()
