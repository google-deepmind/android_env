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

"""Unit tests for host-side dual-agent benchmark harness in android_mcp_runner."""

import json
from typing import Any
from unittest import mock

from absl import app
from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized
from android_env.mcp import android_mcp_runner
from android_env.mcp import android_mcp_tools
from android_env.mcp import errors


class AndroidMcpRunnerTest(parameterized.TestCase):

  def test_init_default_ports_and_host(self):
    runner = android_mcp_runner.AndroidMcpRunner()
    self.assertEqual(runner.worker_port, 8000)
    self.assertEqual(runner.manager_port, 8001)
    self.assertEqual(runner.host, 'localhost')
    self.assertIsNone(runner.worker_tools)
    self.assertIsNone(runner.manager_tools)

  def test_init_custom_ports_and_tools(self):
    mock_worker = mock.create_autospec(
        android_mcp_tools.AndroidMcpTools, instance=True
    )
    mock_manager = mock.create_autospec(
        android_mcp_tools.AndroidMcpTools, instance=True
    )
    runner = android_mcp_runner.AndroidMcpRunner(
        worker_port=8080,
        manager_port=8081,
        host='127.0.0.1',
        worker_tools=mock_worker,
        manager_tools=mock_manager,
    )
    self.assertEqual(runner.worker_port, 8080)
    self.assertEqual(runner.manager_port, 8081)
    self.assertEqual(runner.host, '127.0.0.1')
    self.assertIs(runner.worker_tools, mock_worker)
    self.assertIs(runner.manager_tools, mock_manager)

  def test_run_trial_invalid_task_path(self):
    runner = android_mcp_runner.AndroidMcpRunner()
    with self.assertRaises(FileNotFoundError):
      runner.run_trial('/nonexistent/task/path/file.textproto')

  def test_run_trial_success(self):
    temp_task = self.create_tempfile(
        'task.textproto', content='id: "test_task"\nname: "Test Task"\n'
    )
    mock_worker = mock.create_autospec(
        android_mcp_tools.AndroidMcpTools, instance=True
    )
    mock_manager = mock.create_autospec(
        android_mcp_tools.AndroidMcpTools, instance=True
    )

    mock_manager.get_task_metrics.side_effect = [
        json.dumps(
            {'score': 0.0, 'reward': 0.1, 'is_done': False, 'extras': {}}
        ),
        json.dumps(
            {'score': 0.5, 'reward': 0.2, 'is_done': False, 'extras': {}}
        ),
        json.dumps({
            'score': 1.0,
            'reward': 0.7,
            'is_done': True,
            'extras': {'result': 'win'},
        }),
    ]
    mock_manager.get_battery_metrics.side_effect = [
        json.dumps({'level_percent': 100.0, 'power_mw': 400.0}),
        json.dumps({'level_percent': 95.0, 'power_mw': 450.0}),
    ]

    runner = android_mcp_runner.AndroidMcpRunner(
        worker_tools=mock_worker,
        manager_tools=mock_manager,
    )

    results = runner.run_trial(temp_task.full_path, max_steps=10)

    mock_manager.load_task.assert_called_once_with(temp_task.full_path)
    mock_manager.reset_task.assert_called_once()
    mock_worker.load_task.assert_called_once_with(temp_task.full_path)
    mock_worker.reset_task.assert_called_once()

    self.assertEqual(results['task_path'], temp_task.full_path)
    self.assertEqual(results['steps'], 3)
    self.assertEqual(results['total_steps'], 3)
    self.assertAlmostEqual(results['score'], 1.0)
    self.assertAlmostEqual(results['reward'], 1.0)
    self.assertAlmostEqual(results['total_reward'], 1.0)
    self.assertTrue(results['is_done'])
    self.assertEqual(
        results['initial_battery_metrics'],
        {'level_percent': 100.0, 'power_mw': 400.0},
    )
    self.assertEqual(
        results['final_battery_metrics'],
        {'level_percent': 95.0, 'power_mw': 450.0},
    )
    self.assertEqual(results['extras'], {'result': 'win'})

  def test_run_trial_battery_telemetry_unavailable(self):
    temp_task = self.create_tempfile(
        'task.textproto', content='id: "test_task"\nname: "Test Task"\n'
    )
    mock_manager = mock.create_autospec(
        android_mcp_tools.AndroidMcpTools, instance=True
    )
    mock_manager.get_task_metrics.return_value = json.dumps(
        {'score': 0.0, 'reward': 0.0, 'is_done': True, 'extras': {}}
    )
    mock_manager.get_battery_metrics.side_effect = errors.DeviceConnectionError(
        'Not connected'
    )

    runner = android_mcp_runner.AndroidMcpRunner(
        manager_tools=mock_manager,
    )

    results = runner.run_trial(temp_task.full_path, max_steps=1)

    self.assertEqual(
        results['battery_metrics'], {'error': 'Battery telemetry unavailable'}
    )
    self.assertEqual(
        results['initial_battery_metrics'],
        {'error': 'Battery telemetry unavailable'},
    )
    self.assertEqual(
        results['final_battery_metrics'],
        {'error': 'Battery telemetry unavailable'},
    )

  def test_run_trial_handles_task_metrics_value_error(self):
    temp_task = self.create_tempfile(
        'task.textproto', content='id: "test_task"\nname: "Test Task"\n'
    )
    mock_manager = mock.create_autospec(
        android_mcp_tools.AndroidMcpTools, instance=True
    )
    mock_manager.get_task_metrics.side_effect = ValueError('Metrics parse err')
    mock_manager.get_battery_metrics.return_value = json.dumps(
        {'level_percent': 80}
    )

    runner = android_mcp_runner.AndroidMcpRunner(manager_tools=mock_manager)
    results = runner.run_trial(temp_task.full_path, max_steps=2)

    self.assertEqual(results['steps'], 2)
    self.assertEqual(results['score'], 0.0)
    self.assertFalse(results['is_done'])

  @parameterized.named_parameters(
      ('json_object', '{"a": 1}', {'a': 1}),
      ('dict_input', {'b': 2}, {'b': 2}),
      ('invalid_json', 'invalid json', {'raw': 'invalid json'}),
      ('json_scalar', '123', {'value': 123}),
      ('unsupported_type', 42, {}),
  )
  def test_parse_json_metrics_variants(
      self, raw_input: Any, expected: dict[str, Any]
  ):
    self.assertEqual(
        android_mcp_runner._parse_json_metrics(raw_input), expected
    )

  def test_main_execution(self):
    temp_task = self.create_tempfile(
        'task.textproto', content='id: "test_task"\nname: "Test Task"\n'
    )
    with flagsaver.flagsaver(
        task_path=temp_task.full_path,
        max_steps=1,
        worker_port=8000,
        manager_port=8001,
    ):
      android_mcp_runner.main(['android_mcp_runner'])

  def test_main_raises_on_extra_arguments(self):
    with self.assertRaisesRegex(
        app.UsageError, 'Too many command-line arguments'
    ):
      android_mcp_runner.main(['android_mcp_runner', 'unexpected'])

  def test_main_raises_when_task_path_missing(self):
    with flagsaver.flagsaver(task_path=None):
      with self.assertRaisesRegex(
          app.UsageError, '--task_path must be specified'
      ):
        android_mcp_runner.main(['android_mcp_runner'])


if __name__ == '__main__':
  absltest.main()
