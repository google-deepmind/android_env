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

"""Host-side dual-agent benchmark runner harness for AndroidEnv FastMCP.

Manages connection configurations and orchestration for dual MCP server roles:
  - Worker Agent (`--role=worker`, Port 8000 default): Dedicated to environment
    interaction (`tap`, `swipe`, `press_key`, `get_screenshot`).
  - Task Manager Agent (`--role=manager`, Port 8001 default): Dedicated to task
    lifecycle control (`load_task`, `reset_task`) and telemetry observation
    (`get_task_metrics`, `get_battery_metrics`).
"""

from collections.abc import Sequence
import json
import os
from typing import Any

from absl import app
from absl import flags
from absl import logging
from android_env.mcp import android_mcp_tools
from android_env.mcp import errors

_WORKER_PORT = flags.DEFINE_integer(
    'worker_port', 8000, 'Port for Worker Agent MCP server.'
)
_MANAGER_PORT = flags.DEFINE_integer(
    'manager_port', 8001, 'Port for Task Manager Agent MCP server.'
)
_HOST = flags.DEFINE_string('host', 'localhost', 'Host for MCP servers.')
_TASK_PATH = flags.DEFINE_string(
    'task_path', None, 'Path to task textproto file.'
)
_MAX_STEPS = flags.DEFINE_integer(
    'max_steps', 100, 'Maximum steps for trial execution.'
)


def _parse_json_metrics(metrics_raw: str | dict[str, Any]) -> dict[str, Any]:
  """Safely parses JSON metric strings or returns dictionary representations.

  Args:
    metrics_raw: Raw JSON metrics string or dictionary.

  Returns:
    Parsed metrics dictionary.
  """
  if isinstance(metrics_raw, str):
    try:
      parsed = json.loads(metrics_raw)
      if isinstance(parsed, dict):
        return parsed
      return {'value': parsed}
    except json.JSONDecodeError:
      return {'raw': metrics_raw}
  elif isinstance(metrics_raw, dict):
    return metrics_raw
  return {}


class AndroidMcpRunner:
  """Host-side dual-agent benchmark harness for AndroidEnv FastMCP servers."""

  def __init__(
      self,
      worker_port: int = 8000,
      manager_port: int = 8001,
      host: str = 'localhost',
      worker_tools: android_mcp_tools.AndroidMcpTools | Any | None = None,
      manager_tools: android_mcp_tools.AndroidMcpTools | Any | None = None,
  ) -> None:
    """Initializes the instance.

    Args:
      worker_port: Port assigned to the Worker Agent MCP server.
      manager_port: Port assigned to the Task Manager Agent MCP server.
      host: Hostname for MCP server connections.
      worker_tools: Optional tools handler instance for the Worker Agent.
      manager_tools: Optional tools handler instance for the Task Manager Agent.
    """
    self._worker_port = worker_port
    self._manager_port = manager_port
    self._host = host
    self._worker_tools = worker_tools
    self._manager_tools = manager_tools

  @property
  def worker_port(self) -> int:
    return self._worker_port

  @property
  def manager_port(self) -> int:
    return self._manager_port

  @property
  def host(self) -> str:
    return self._host

  @property
  def worker_tools(self) -> Any | None:
    return self._worker_tools

  @property
  def manager_tools(self) -> Any | None:
    return self._manager_tools

  def run_trial(self, task_path: str, max_steps: int = 100) -> dict[str, Any]:
    """Runs an evaluation trial using the dual-agent configuration.

    Args:
      task_path: Path to task textproto file.
      max_steps: Maximum number of trial steps to execute.

    Returns:
      Dictionary containing trial metrics (`task_path`, `steps`, `total_steps`,
      `score`, `reward`, `total_reward`, `is_done`, `battery_metrics`,
      `initial_battery_metrics`, `final_battery_metrics`, `extras`,
      `task_metrics`).

    Raises:
      FileNotFoundError: If `task_path` does not exist.
    """
    if not os.path.exists(task_path):
      raise FileNotFoundError(f'Task file not found: {task_path}')

    manager = self._manager_tools
    if manager is None:
      manager = android_mcp_tools.AndroidMcpTools()

    worker = self._worker_tools
    if worker is None:
      worker = (
          self._manager_tools if self._manager_tools is not None else manager
      )

    manager.load_task(task_path)
    if worker is not manager:
      worker.load_task(task_path)

    manager.reset_task()
    if worker is not manager:
      worker.reset_task()

    initial_battery: dict[str, Any] = {}
    try:
      initial_battery_raw = manager.get_battery_metrics()
      initial_battery = _parse_json_metrics(initial_battery_raw)
    except (errors.DeviceConnectionError, ValueError, json.JSONDecodeError):
      initial_battery = {'error': 'Battery telemetry unavailable'}

    steps_executed = 0
    total_reward = 0.0
    final_score = 0.0
    is_done = False
    latest_task_metrics: dict[str, Any] = {}

    for _ in range(max_steps):
      steps_executed += 1
      try:
        worker.get_screenshot()
      except errors.DeviceConnectionError:
        pass

      try:
        task_metrics_raw = manager.get_task_metrics()
        latest_task_metrics = _parse_json_metrics(task_metrics_raw)
        step_reward = float(latest_task_metrics.get('reward', 0.0))
        final_score = float(latest_task_metrics.get('score', 0.0))
        is_done = bool(latest_task_metrics.get('is_done', False))
        total_reward += step_reward

        if is_done:
          logging.info('Trial task marked done at step %d', steps_executed)
          break
      except (ValueError, json.JSONDecodeError):
        pass

    final_battery: dict[str, Any] = {}
    try:
      final_battery_raw = manager.get_battery_metrics()
      final_battery = _parse_json_metrics(final_battery_raw)
    except (errors.DeviceConnectionError, ValueError, json.JSONDecodeError):
      final_battery = {'error': 'Battery telemetry unavailable'}

    return {
        'task_path': task_path,
        'steps': steps_executed,
        'total_steps': steps_executed,
        'score': final_score,
        'reward': total_reward,
        'total_reward': total_reward,
        'is_done': is_done,
        'initial_battery_metrics': initial_battery,
        'final_battery_metrics': final_battery,
        'battery_metrics': final_battery,
        'extras': latest_task_metrics.get('extras', {}),
        'task_metrics': latest_task_metrics,
    }


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  if not _TASK_PATH.value:
    raise app.UsageError('--task_path must be specified.')

  runner = AndroidMcpRunner(
      worker_port=_WORKER_PORT.value,
      manager_port=_MANAGER_PORT.value,
      host=_HOST.value,
  )
  results = runner.run_trial(
      task_path=_TASK_PATH.value, max_steps=_MAX_STEPS.value
  )
  logging.info('Trial execution results: %s', results)
  print(json.dumps(results, indent=2))


if __name__ == '__main__':
  app.run(main)
