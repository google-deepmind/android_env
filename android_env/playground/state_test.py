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

"""Tests for playground state."""

import socket
from absl.testing import absltest
from android_env.playground import state as state_lib


class StateTest(absltest.TestCase):

  def test_playground_state_init(self):
    state = state_lib.PlaygroundState()
    self.assertIsNone(state.current_frame)
    self.assertTrue(state.running)
    self.assertIsNone(state.get_active_ws())
    self.assertFalse(state.waiting_for_ack)

  def test_set_active_ws(self):
    state = state_lib.PlaygroundState()
    # Use a dummy socket object or mock
    # A real socket is not connected, but we just want to verify it stores it
    mock_socket = socket.socket()
    state.set_active_ws(mock_socket)
    self.assertEqual(state.get_active_ws(), mock_socket)
    mock_socket.close()

  def test_reload_flags(self):
    state = state_lib.PlaygroundState()
    self.assertIsNone(state.get_reload())

    state.set_reload('my_task')
    self.assertEqual(state.get_reload(), 'my_task')

    state.clear_reload()
    self.assertIsNone(state.get_reload())

  def test_logs(self):
    state = state_lib.PlaygroundState()
    self.assertEqual(state.get_logs(), [])

    log1 = {'message': 'msg1', 'level': 'INFO', 'timestamp': 100.0}
    state.add_log(log1)
    self.assertEqual(state.get_logs(), [log1])

    log2 = {'message': 'msg2', 'level': 'ERROR', 'timestamp': 101.0}
    state.add_log(log2)
    self.assertEqual(state.get_logs(), [log1, log2])

    state.clear_logs()
    self.assertEqual(state.get_logs(), [])

  def test_logs_max_capacity(self):
    state = state_lib.PlaygroundState()
    state.max_logs = 3
    for i in range(5):
      state.add_log({'message': f'msg{i}'})
    logs = state.get_logs()
    self.assertLen(logs, 3)
    self.assertEqual(logs[0]['message'], 'msg2')
    self.assertEqual(logs[2]['message'], 'msg4')

  def test_battery_power_stats(self):
    state = state_lib.PlaygroundState()
    self.assertIsNone(state.get_battery_power_stats())

    battery_stats = {
        'level_percent': 85,
        'power_mw': 1500.0,
    }
    state.set_battery_power_stats(battery_stats)
    self.assertEqual(state.get_battery_power_stats(), battery_stats)

    stats = state.flush_stats()
    self.assertEqual(stats['battery_power'], battery_stats)

    class FakeScalar:

      def __init__(self, v):
        self._v = v

      def item(self):
        return self._v

    class FakeBatteryMetrics:
      level_percent = FakeScalar(90)
      status = 'CHARGING'
      power_mw = 2000.0

    state.set_battery_power_stats(FakeBatteryMetrics())
    self.assertEqual(
        state.get_battery_power_stats(),
        {'level_percent': 90, 'status': 'CHARGING', 'power_mw': 2000.0},
    )

    dict_metrics = {
        'level_percent': 85,
        'status': 'DISCHARGING',
        'power_mw': 1500.0,
    }
    state.set_battery_power_stats(dict_metrics)
    self.assertEqual(
        state.get_battery_power_stats(),
        {'level_percent': 85, 'status': 'DISCHARGING', 'power_mw': 1500.0},
    )

  def test_status(self):
    state = state_lib.PlaygroundState()
    self.assertIsNone(state.get_status())
    state.set_status('Ready! Orientation: 0')
    self.assertEqual(state.get_status(), 'Ready! Orientation: 0')

  def test_add_and_flush_stats(self):
    state = state_lib.PlaygroundState()
    self.assertEqual(state.flush_stats(), {})

    state.add_stat('ack_latency', 10.0)
    state.add_stat('ack_latency', 20.0)
    state.add_stat('env_step_ms', 5.0)
    state.add_stat('unknown_stat', 99.0)

    flushed = state.flush_stats()
    self.assertEqual(flushed, {'ack_latency': 15.0, 'env_step_ms': 5.0})
    self.assertEqual(state.flush_stats(), {})

  def test_reset_flags(self):
    state = state_lib.PlaygroundState()
    self.assertFalse(state.get_reset())
    state.set_reset()
    self.assertTrue(state.get_reset())
    state.clear_reset()
    self.assertFalse(state.get_reset())

  def test_episode_stats(self):
    state = state_lib.PlaygroundState()
    self.assertIsNone(state.get_episode_stats())

    ep_stats = {'step': 4, 'reward': 1.5, 'cumulative_reward': 6.0}
    state.set_episode_stats(ep_stats)
    self.assertEqual(state.get_episode_stats(), ep_stats)

    flushed = state.flush_stats()
    self.assertEqual(flushed['episode'], ep_stats)


if __name__ == '__main__':
  absltest.main()
