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

"""Standardized 2048 multi-model benchmark sweep for AndroidEnv.

Runs a standardized 10-step 2048 evaluation across frontier and fast models,
recording per-step model inference latency, cumulative tile-merge reward, action
diversity, and device power/battery telemetry.
"""

from collections.abc import Sequence
import io
import json
import os
import time
from typing import Any, cast

from absl import app
from absl import flags
from android_env import loader
from android_env.components import config_classes
from android_env.components import telemetry
from android_env.google.configs import prod_config
from android_env.playground import mcp_bridge
from android_env.playground import providers
from android_env.playground import state
from PIL import Image

_AVD_NAME = flags.DEFINE_string(
    'avd_name', 'pixel_6_api_34', 'Android Virtual Device name.'
)
_TASK = flags.DEFINE_string(
    'task', '2048', 'AndroidEnv task name to benchmark.'
)
_STEPS_PER_MODEL = flags.DEFINE_integer(
    'steps_per_model', 10, 'Number of steps to execute per model.'
)
_MODELS = flags.DEFINE_list(
    'models',
    [
        'gemini-3.1-flash-lite-preview',
        'gemini-3-flash-preview',
        'gemini-3.1-pro-preview',
        'gemini-2.5-flash',
        'gpt-4o-2024-08-06',
        'gpt-4o-mini-2024-07-18',
    ],
    'Models to evaluate on 2048.',
)
_OUTPUT_JSON = flags.DEFINE_string(
    'output_json',
    '/tmp/standardized_2048_sweep.json',
    'Output path for JSON benchmark results.',
)

_GOAL_2048 = (
    'Play 2048 and maximize your score by merging tiles! Keep your largest tile'
    ' anchored in a corner and choose the swipe direction (UP, DOWN, LEFT, or'
    ' RIGHT) that merges tiles cleanly. If a swipe direction did not move any'
    ' tiles, pick a different direction!'
)

_SYSTEM_PROMPT = """You are an autonomous Android Agent controlling a live Android device inside AndroidEnv Playground via Model Context Protocol (MCP) tools.
Use `swipe` to slide tiles across the 2048 board:
- UP: `swipe(start_x=0.5, start_y=0.7, end_x=0.5, end_y=0.3)`
- DOWN: `swipe(start_x=0.5, start_y=0.3, end_x=0.5, end_y=0.7)`
- LEFT: `swipe(start_x=0.75, start_y=0.5, end_x=0.25, end_y=0.5)`
- RIGHT: `swipe(start_x=0.25, start_y=0.5, end_x=0.75, end_y=0.5)`
Call exactly ONE `swipe` tool per turn.
"""


def _encode_png(rgb_pixels: Any) -> bytes:
  """Encodes an RGB numpy array into PNG bytes."""
  img = Image.fromarray(rgb_pixels, mode='RGB')
  buf = io.BytesIO()
  img.save(buf, format='PNG')
  return buf.getvalue()


def _step_action_in_env(env: Any, act: dict[str, Any]) -> Any:
  """Executes a single normalized touch or key action on the environment."""
  act_type = act.get('type')
  if act_type in ('down', 'move'):
    return env.step({
        'action_type': 0,
        'touch_position': [float(act['x']), float(act['y'])],
    })
  if act_type == 'up':
    return env.step({
        'action_type': 1,
        'touch_position': [float(act['x']), float(act['y'])],
    })
  return env.step({'action_type': 1, 'touch_position': [0.0, 0.0]})


def _drain_actions(
    env: Any, pstate: Any, bridge: mcp_bridge.PlaygroundMcpBridge
) -> float:
  """Drains queued MCP actions into `env.step` and updates frame/reward."""
  del bridge
  step_reward = 0.0
  ts = None
  while not pstate.action_queue.empty():
    act = pstate.action_queue.get_nowait()
    ts = _step_action_in_env(env, act)
    if ts.reward:
      step_reward += float(ts.reward)

  for _ in range(4):
    ts = env.step({'action_type': 1, 'touch_position': [0.0, 0.0]})
    if ts.reward:
      step_reward += float(ts.reward)
    time.sleep(0.05)

  if ts is not None:
    pstate.set_last_timestep(ts)
    pixels = ts.observation['pixels']
    with pstate.frame_lock:
      pstate.current_frame = _encode_png(pixels)
  return step_reward


def run_model_on_2048(
    env: Any,
    pstate: Any,
    bridge: mcp_bridge.PlaygroundMcpBridge,
    model_name: str,
    steps_per_model: int,
) -> dict[str, Any]:
  """Evaluates a single model on 2048 for `steps_per_model` steps."""
  print(f'\n>>> Evaluating {model_name} on 2048 ({steps_per_model} steps)...')
  ts = env.reset()
  pstate.reset_cumulative_reward()
  pstate.clear_action_queue()
  pstate.set_last_timestep(ts)
  with pstate.frame_lock:
    pstate.current_frame = _encode_png(ts.observation['pixels'])

  for _ in range(5):
    ts = env.step({'action_type': 1, 'touch_position': [0.0, 0.0]})
    time.sleep(0.1)
  pstate.set_last_timestep(ts)
  with pstate.frame_lock:
    pstate.current_frame = _encode_png(ts.observation['pixels'])

  provider = providers.create_provider(model_name)
  tools_schema = bridge.list_tools()

  latencies: list[float] = []
  step_records: list[dict[str, Any]] = []
  total_reward = 0.0
  history_lines: list[str] = []
  t_start = time.time()

  try:
    for step in range(1, steps_per_model + 1):
      screenshot_bytes = bridge.get_screenshot_bytes()
      dev_info = bridge.get_device_info()
      recent = '\n'.join(history_lines[-5:]) if history_lines else 'None yet.'
      user_prompt = (
          f'GOAL: {_GOAL_2048}\n'
          f'STEP: {step} / {steps_per_model}\n'
          f'DEVICE INFO:\n{dev_info}\n\n'
          f'RECENT HISTORY:\n{recent}\n\n'
          'Choose your next swipe tool call.'
      )

      resp = provider.generate(
          system_prompt=_SYSTEM_PROMPT,
          user_prompt=user_prompt,
          screenshot_bytes=screenshot_bytes,
          tools_schema=tools_schema,
          thinking_level='LOW',
      )
      latencies.append(resp.latency_ms)
      thought_str = resp.thoughts[0] if resp.thoughts else ''

      if resp.tool_calls:
        tc = resp.tool_calls[0]
        bridge.execute_tool(tc.name, tc.args)
        r = _drain_actions(env, pstate, bridge)
        total_reward += r
        history_lines.append(
            f'Step {step}: {tc.name}({json.dumps(tc.args)}) -> '
            f'reward={r}, total_reward={total_reward}'
        )
        step_records.append({
            'step': step,
            'tool': tc.name,
            'args': tc.args,
            'latency_ms': round(resp.latency_ms, 1),
            'step_reward': r,
            'cumulative_reward': total_reward,
            'thought': thought_str[:160],
        })
        print(
            f'  Step {step:2d} | {tc.name} {json.dumps(tc.args)} | '
            f'lat={resp.latency_ms:.0f}ms | '
            f'reward=+{r:.0f} (total={total_reward:.0f})'
        )
      else:
        step_records.append({
            'step': step,
            'tool': 'none',
            'latency_ms': round(resp.latency_ms, 1),
            'step_reward': 0.0,
            'cumulative_reward': total_reward,
            'thought': thought_str[:160],
        })
        print(f'  Step {step:2d} | No tool call | lat={resp.latency_ms:.0f}ms')
  finally:
    provider.close()

  wall_s = time.time() - t_start
  bp = telemetry.fetch_battery_power_metrics(env)
  avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

  return {
      'model': model_name,
      'task': '2048',
      'steps_completed': len(step_records),
      'cumulative_reward': total_reward,
      'avg_latency_ms': round(avg_lat, 1),
      'min_latency_ms': round(min(latencies), 1) if latencies else 0.0,
      'max_latency_ms': round(max(latencies), 1) if latencies else 0.0,
      'total_wall_time_s': round(wall_s, 2),
      'battery_power_mw': round(bp.power_mw, 1) if bp else 0.0,
      'battery_level_percent': bp.level_percent if bp else 0,
      'steps': step_records,
  }


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  env_cfg = prod_config.get_config('emulator')
  env_cfg.task = config_classes.MpmTaskConfig(task_id=_TASK.value)
  if isinstance(env_cfg.simulator, config_classes.EmulatorConfig):
    env_cfg.simulator.emulator_launcher.avd_name = _AVD_NAME.value
    env_cfg.simulator.emulator_launcher.run_headless = True
    env_cfg.simulator.emulator_launcher.gpu_mode = 'swiftshader_indirect'
  env = cast(Any, loader.load(env_cfg))

  pstate = cast(Any, state.PlaygroundState())
  pstate.set_env(env)
  pstate.set_status('Running')
  bridge = mcp_bridge.PlaygroundMcpBridge(pstate)

  results: list[dict[str, Any]] = []
  try:
    for m in _MODELS.value:
      try:
        res = run_model_on_2048(env, pstate, bridge, m, _STEPS_PER_MODEL.value)
        results.append(res)
      except Exception as e:  # pylint: disable=broad-exception-caught
        print(f'ERROR on {m}: {e}')
        results.append({'model': m, 'error': str(e)})
      out_dir = os.path.dirname(_OUTPUT_JSON.value)
      if out_dir:
        os.makedirs(out_dir, exist_ok=True)
      with open(_OUTPUT_JSON.value, 'w', encoding='utf-8') as f:
        json.dump(results, f, indent=2)
  finally:
    env.close()

  print('\n=== 2048 SWEEP COMPLETE ===')
  for r in results:
    print(
        f"{r.get('model'):30s} | reward={r.get('cumulative_reward', 0):6.1f} | "
        f"avg_lat={r.get('avg_latency_ms', 0):7.1f}ms | "
        f"wall={r.get('total_wall_time_s', 0):5.1f}s | "
        f"power={r.get('battery_power_mw', 0):.1f}mW"
    )


if __name__ == '__main__':
  app.run(main)
