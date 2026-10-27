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

"""Multi-model Gemini and Ditto benchmark sweep runner for AndroidEnv Playground.

Connects to a running AndroidEnv Playground WebSocket server
(`ws://127.0.0.1:8765/ws`),
reloads the target task for a clean episode, triggers `agent_start` for each
model, and records step-by-step telemetry, latency, rewards, and thoughts.
"""

from collections.abc import Sequence
import json
import os
import time
from typing import Any

from absl import app
from absl import flags
import websocket

_WS_URL = flags.DEFINE_string(
    'ws_url',
    'ws://127.0.0.1:8765/ws',
    'WebSocket URL of the AndroidEnv Playground server.',
)
_TASK = flags.DEFINE_string(
    'task',
    'sgtpuzzles_flood_3x3_easy',
    'Task name to reload before each model trial.',
)
_GOAL = flags.DEFINE_string(
    'goal',
    'Play Flood It (3x3 Easy) and flood the entire board with a single color '
    'in as few moves as possible. When solved, call done.',
    'Goal instruction sent to the autonomous agent.',
)
_MODELS = flags.DEFINE_list(
    'models',
    [
        'gemini-3-flash-preview',
        'gemini-3.1-pro-preview',
        'gemini-3.1-flash-lite-preview',
        'gpt-4o-2024-08-06',
        'claude-3-5-sonnet-v2@20241022',
    ],
    'List of model identifiers to benchmark.',
)
_MAX_STEPS = flags.DEFINE_integer(
    'max_steps', 12, 'Maximum agent steps per episode.'
)
_OUTPUT_JSON = flags.DEFINE_string(
    'output_json',
    '/tmp/Sweep_results_gemini.json',
    'Output file path for JSON benchmark metrics.',
)


def wait_for_reload_complete(
    ws: websocket.WebSocket, timeout_s: float = 90.0
) -> bool:
  """Waits until the Playground server completes task reload."""
  deadline = time.time() + timeout_s
  saw_loading = False
  while time.time() < deadline:
    try:
      raw = ws.recv()
    except websocket.WebSocketTimeoutException:
      continue
    if isinstance(raw, bytes):
      continue
    msg = json.loads(raw)
    if msg.get('type') == 'reload_status':
      st = msg.get('status')
      if st == 'loading':
        saw_loading = True
      elif st == 'idle' and saw_loading:
        return True
      elif st == 'error':
        print(f'Reload error: {msg.get("error")}')
        return False
  return False


def run_single_model(
    ws_url: str,
    model: str,
    task_name: str,
    goal: str,
    max_steps: int,
) -> dict[str, Any]:
  """Runs a single model evaluation over WebSocket and returns metrics."""
  print('\n======================================================')
  print(f'Starting Benchmark for Model: {model} on Task: {task_name}')
  print('======================================================')
  ws = websocket.create_connection(ws_url, timeout=5.0)

  ws.send(json.dumps({'type': 'reload', 'task': task_name}))
  print('Waiting for environment reload to finish...')
  wait_for_reload_complete(ws, timeout_s=90.0)
  time.sleep(2.0)

  t_start = time.time()
  ws.send(
      json.dumps({
          'type': 'agent_start',
          'goal': goal,
          'model': model,
          'max_steps': max_steps,
      })
  )

  tool_calls: list[dict[str, Any]] = []
  thoughts: list[str] = []
  latencies: list[float] = []
  battery_samples: list[dict[str, Any]] = []
  cumulative_reward = 0.0
  status = 'timeout'
  error_msg = ''

  deadline = time.time() + 300.0
  while time.time() < deadline:
    try:
      raw = ws.recv()
    except websocket.WebSocketTimeoutException:
      continue
    if isinstance(raw, bytes):
      continue
    msg = json.loads(raw)
    mtype = msg.get('type')
    if mtype == 'stats':
      for pt in msg.get('data', []):
        if pt.get('reward', 0) != 0:
          cumulative_reward += float(pt['reward'])
      bp = msg.get('battery_power')
      if bp and bp.get('power_mw', 0) > 0:
        battery_samples.append(bp)
    elif mtype == 'agent_event':
      ev = msg.get('event')
      step = msg.get('step', 0)
      text = msg.get('text', '')
      lat = msg.get('latency_ms')
      if ev == 'thought':
        thoughts.append(text)
        print(f'  [Step {step} Thought] {text[:120]}')
      elif ev == 'tool_call':
        if lat:
          latencies.append(float(lat))
        tool_calls.append({
            'step': step,
            'tool': msg.get('tool'),
            'args': msg.get('args'),
            'latency_ms': lat,
        })
        print(f'  [Step {step} Tool] {text}')
      elif ev == 'completed':
        status = 'completed'
        print(f'  [Completed] {text}')
        break
      elif ev == 'error':
        status = 'error'
        error_msg = text
        print(f'  [Error] {text}')
        break
      elif ev == 'stopped':
        status = 'stopped'
        break

  total_time_s = time.time() - t_start
  ws.close()

  avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
  avg_power_mw = 0.0
  if battery_samples:
    total_power = sum(b.get('power_mw', 0.0) for b in battery_samples)
    avg_power_mw = total_power / len(battery_samples)

  return {
      'model': model,
      'task': task_name,
      'status': status,
      'error': error_msg,
      'steps_taken': len(tool_calls),
      'max_steps': max_steps,
      'cumulative_reward': cumulative_reward,
      'avg_latency_ms': round(avg_lat, 1),
      'min_latency_ms': round(min(latencies), 1) if latencies else 0.0,
      'max_latency_ms': round(max(latencies), 1) if latencies else 0.0,
      'total_wall_time_s': round(total_time_s, 2),
      'avg_device_power_mw': round(avg_power_mw, 1),
      'tool_calls': tool_calls,
      'thoughts': thoughts,
  }


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  results: list[dict[str, Any]] = []
  for model in _MODELS.value:
    try:
      res = run_single_model(
          ws_url=_WS_URL.value,
          model=model,
          task_name=_TASK.value,
          goal=_GOAL.value,
          max_steps=_MAX_STEPS.value,
      )
      results.append(res)
    except Exception as e:  # pylint: disable=broad-exception-caught
      print(f'Model {model} failed: {e}')
      results.append({'model': model, 'status': 'exception', 'error': str(e)})

    out_dir = os.path.dirname(_OUTPUT_JSON.value)
    if out_dir:
      os.makedirs(out_dir, exist_ok=True)
    with open(_OUTPUT_JSON.value, 'w', encoding='utf-8') as f:
      json.dump(results, f, indent=2)

  print('\n=== SWEEP SUMMARY ===')
  for r in results:
    print(
        f"{r.get('model'):32s} | status={r.get('status'):10s} | "
        f"steps={r.get('steps_taken', 0):2d} | "
        f"reward={r.get('cumulative_reward', 0.0):.1f} | "
        f"avg_lat={r.get('avg_latency_ms', 0.0):.1f}ms | "
        f"wall={r.get('total_wall_time_s', 0.0):.1f}s"
    )


if __name__ == '__main__':
  app.run(main)
