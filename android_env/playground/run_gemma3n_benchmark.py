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

"""End-to-end benchmark runner for local Gemma 3n / Gemma 4 LiteRT-LM models.

Evaluates `gemma-3n-e2b` (Gemma-3n-E2B-it-int4) and `gemma-4-e2b` across the 4
AndroidEnv benchmark tasks (`sgtpuzzles_flood_3x3_easy`,
`sgtpuzzles_flood_4x4_easy`, `sgtpuzzles_flood_5x5`, and `2048`), recording
step-by-step latency, energy telemetry, and task rewards.
"""

from collections.abc import Sequence
import csv
import io
import json
import subprocess
import threading
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

_DEVICE_MODE = flags.DEFINE_enum(
    'device_mode', 'emulator', ['emulator', 'real_device'], 'Device mode.'
)
_AVD_NAME = flags.DEFINE_string(
    'avd_name', 'pixel_6_api_34', 'AVD name for emulator.'
)
_DEVICE_SERIAL = flags.DEFINE_string(
    'device_serial', '', 'Android serial for real_device.'
)
_ADB_PATH = flags.DEFINE_string('adb_path', 'adb', 'Path to adb binary.')
_MODELS = flags.DEFINE_list(
    'models',
    ['gemma-3n-e2b'],
    'Local LiteRT-LM models to benchmark (e.g., gemma-3n-e2b, gemma-4-e2b).',
)
_TASKS = flags.DEFINE_list(
    'tasks',
    [
        'sgtpuzzles_flood_3x3_easy',
        'sgtpuzzles_flood_4x4_easy',
        'sgtpuzzles_flood_5x5',
        '2048',
    ],
    'Tasks to benchmark.',
)
_EXECUTION_TARGET = flags.DEFINE_enum(
    'execution_target',
    'host',
    ['host', 'device'],
    'Where to run the LiteRT-LM engine (host workstation or Android device).',
)
_ENABLE_VISION = flags.DEFINE_bool(
    'enable_vision',
    True,
    'Whether to pass screenshots to the LiteRT-LM multimodal vision encoder.',
)
_TRIALS = flags.DEFINE_integer('trials', 2, 'Trials per (model, task).')
_MAX_STEPS_FLOOD = flags.DEFINE_integer(
    'max_steps_flood', 12, 'Max steps for Flood It.'
)
_MAX_STEPS_2048 = flags.DEFINE_integer(
    'max_steps_2048', 10, 'Max steps for 2048.'
)
_OUTPUT_JSON = flags.DEFINE_string(
    'output_json',
    '/tmp/gemma3n_benchmark_results.json',
    'Path to save JSON results.',
)
_OUTPUT_CSV = flags.DEFINE_string(
    'output_csv',
    '/tmp/gemma3n_step_series.csv',
    'Path to save per-step CSV time series.',
)


class HardwareBatterySampler:
  """Polls real hardware battery sysfs counters via `adb shell` at 1 Hz."""

  def __init__(self, adb_path: str, serial: str | None) -> None:
    self._adb_path = adb_path
    self._serial = serial
    self._samples: list[dict[str, Any]] = []
    self._stop = threading.Event()
    self._thread: threading.Thread | None = None

  def _adb_cmd(self, *args: str) -> list[str]:
    cmd = [self._adb_path]
    if self._serial:
      cmd.extend(['-s', self._serial])
    cmd.extend(args)
    return cmd

  def sample_once(self) -> dict[str, Any] | None:
    """Reads `/sys/class/power_supply/battery` counters once."""
    script = (
        'cat /sys/class/power_supply/battery/current_now '
        '/sys/class/power_supply/battery/voltage_now '
        '/sys/class/power_supply/battery/charge_counter '
        '/sys/class/power_supply/battery/capacity '
        '/sys/class/power_supply/battery/temp '
        '/sys/class/power_supply/battery/status 2>/dev/null'
    )
    try:
      out = subprocess.check_output(
          self._adb_cmd('shell', script), text=True, timeout=3.0
      ).splitlines()
      if len(out) >= 6:
        curr_ua = int(out[0].strip())
        volt_uv = int(out[1].strip())
        charge_uah = int(out[2].strip())
        cap_pct = int(out[3].strip())
        temp_dc = int(out[4].strip())
        status_str = out[5].strip()
        volt_mv = volt_uv / 1000.0
        power_mw = abs(curr_ua) * volt_mv / 1_000_000.0
        return {
            'ts': time.time(),
            'current_now_ua': curr_ua,
            'voltage_mv': round(volt_mv, 1),
            'power_mw': round(power_mw, 2),
            'charge_counter_uah': charge_uah,
            'level_percent': cap_pct,
            'temperature_celsius': round(temp_dc / 10.0, 1),
            'status': status_str,
        }
    except (subprocess.SubprocessError, OSError, ValueError):
      pass
    return None

  def start(self) -> None:
    self._samples.clear()
    self._stop.clear()
    first = self.sample_once()
    if first:
      self._samples.append(first)
    self._thread = threading.Thread(target=self._loop, daemon=True)
    self._thread.start()

  def _loop(self) -> None:
    while not self._stop.is_set():
      s = self.sample_once()
      if s:
        self._samples.append(s)
      self._stop.wait(1.0)

  def stop_and_summarize(self) -> dict[str, Any]:
    """Stops polling and summarizes integrated energy and temperature."""
    self._stop.set()
    if self._thread:
      self._thread.join(timeout=2.0)
    last = self.sample_once()
    if last:
      self._samples.append(last)
    if not self._samples:
      return {'samples_count': 0}
    powers = [s['power_mw'] for s in self._samples]
    temps = [s['temperature_celsius'] for s in self._samples]
    energy_mj = 0.0
    for i in range(1, len(self._samples)):
      dt = self._samples[i]['ts'] - self._samples[i - 1]['ts']
      avg_p = 0.5 * (
          self._samples[i]['power_mw'] + self._samples[i - 1]['power_mw']
      )
      energy_mj += avg_p * dt
    return {
        'samples_count': len(self._samples),
        'avg_power_mw': round(sum(powers) / len(powers), 2),
        'peak_power_mw': round(max(powers), 2),
        'integrated_energy_mj': round(energy_mj, 2),
        'start_temp_c': temps[0],
        'end_temp_c': temps[-1],
    }


def _encode_png(
    rgb_pixels: Any, resize_to: tuple[int, int] = (256, 256)
) -> bytes:
  img = Image.fromarray(rgb_pixels, mode='RGB')
  if resize_to:
    img = img.resize(resize_to, Image.Resampling.BILINEAR)
  buf = io.BytesIO()
  img.save(buf, format='PNG')
  return buf.getvalue()


def _step_action_in_env(env: Any, act: dict[str, Any]) -> Any:
  """Executes a single touch action dictionary in `env`."""
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


def _drain_actions(env: Any, pstate: Any) -> tuple[float, bool]:
  """Drains `pstate.action_queue` into `env` and updates the frame buffer."""
  step_reward = 0.0
  episode_ended = False
  ts = None
  while not pstate.action_queue.empty():
    act = pstate.action_queue.get_nowait()
    ts = _step_action_in_env(env, act)
    if ts.reward:
      step_reward += float(ts.reward)
    if ts.last():
      episode_ended = True

  for _ in range(5):
    ts = env.step({'action_type': 1, 'touch_position': [0.0, 0.0]})
    if ts.reward:
      step_reward += float(ts.reward)
    if ts.last():
      episode_ended = True
    time.sleep(0.06)

  if ts is not None:
    pstate.set_last_timestep(ts)
    pixels = ts.observation['pixels']
    with pstate.frame_lock:
      pstate.current_frame = _encode_png(pixels)
  return step_reward, episode_ended


def _extract_board_summary(rgb_pixels: Any, task_name: str) -> str:
  """Extracts a compact RGB color summary of the puzzle grid cells."""
  if task_name == '2048':
    return 'Task: 2048 4x4 sliding tile board.'
  grid_n = 3
  if '4x4' in task_name:
    grid_n = 4
  elif '5x5' in task_name:
    grid_n = 5

  h, w = rgb_pixels.shape[:2]
  palette = {
      'RED': (220, 40, 40),
      'GREEN': (40, 180, 40),
      'BLUE': (40, 80, 220),
      'YELLOW': (230, 210, 40),
      'ORANGE': (235, 135, 35),
      'PURPLE': (165, 50, 195),
  }

  def _nearest_color(r: int, g: int, b: int) -> str:
    best_name = 'RED'
    best_d = 1e9
    for cname, (cr, cg, cb) in palette.items():
      d = (r - cr) ** 2 + (g - cg) ** 2 + (b - cb) ** 2
      if d < best_d:
        best_d = d
        best_name = cname
    return best_name

  rows_str: list[str] = []
  for r_idx in range(grid_n):
    yn = 0.25 + (r_idx + 0.5) * (0.52 / grid_n)
    py = min(max(int(yn * h), 0), h - 1)
    row_cells: list[str] = []
    for c_idx in range(grid_n):
      xn = 0.10 + (c_idx + 0.5) * (0.80 / grid_n)
      px = min(max(int(xn * w), 0), w - 1)
      rgb = rgb_pixels[py, px]
      cname = _nearest_color(int(rgb[0]), int(rgb[1]), int(rgb[2]))
      row_cells.append(f'({r_idx},{c_idx})@{xn:.2f},{yn:.2f}={cname}')
    rows_str.append(' | '.join(row_cells))
  return f'Flood-It {grid_n}x{grid_n} Grid:\n' + '\n'.join(rows_str)


def _task_prompts(task_name: str) -> tuple[str, str]:
  """Returns `(system_prompt, goal_prompt)` for the given benchmark task."""
  if task_name == '2048':
    sys_p = (
        'You control 2048 on Android. Output ONLY a JSON object:\n'
        '{"tool": "swipe", "args": {"start_x": 0.5, "start_y": 0.7, '
        '"end_x": 0.5, "end_y": 0.3}, "thought": "reason"}\n'
        'Directions: UP=(0.5,0.7->0.5,0.3), DOWN=(0.5,0.3->0.5,0.7), '
        'LEFT=(0.75,0.5->0.25,0.5), RIGHT=(0.25,0.5->0.75,0.5).'
    )
    goal_p = 'Play 2048! Alternate swipe directions to merge tiles.'
    return sys_p, goal_p

  sys_p = (
      'You play Flood-It on Android. Flood-fill the grid from top-left (0,0) '
      'into a single color. Output ONLY a JSON object:\n'
      '{"tool": "tap", "args": {"x": 0.50, "y": 0.50}, '
      '"thought": "Tap color X to absorb adjacent tiles"}'
  )
  goal_p = (
      'Tap the (x, y) center of a square whose color is adjacent to the '
      "top-left (0,0) connected region but different from (0,0)'s current "
      'color!'
  )
  return sys_p, goal_p


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  results: list[dict[str, Any]] = []
  csv_rows: list[dict[str, Any]] = []

  hw_sampler = None
  if _DEVICE_MODE.value == 'real_device':
    hw_sampler = HardwareBatterySampler(
        _ADB_PATH.value, _DEVICE_SERIAL.value or None
    )

  for task_name in _TASKS.value:
    if _DEVICE_MODE.value == 'real_device':
      env_cfg = prod_config.get_config('real_device')
      env_cfg.task = config_classes.MpmTaskConfig(task_id=task_name)
      adb_ctrl_cfg = config_classes.AdbControllerConfig(
          adb_path=_ADB_PATH.value,
          device_name=_DEVICE_SERIAL.value,
      )
      env_cfg.simulator = config_classes.RealDeviceConfig(
          device_name=_DEVICE_SERIAL.value,
          adb_controller_config=adb_ctrl_cfg,
      )
    else:
      env_cfg = prod_config.get_config('emulator')
      env_cfg.task = config_classes.MpmTaskConfig(task_id=task_name)
      if isinstance(env_cfg.simulator, config_classes.EmulatorConfig):
        env_cfg.simulator.emulator_launcher.avd_name = _AVD_NAME.value
        env_cfg.simulator.emulator_launcher.run_headless = True
        env_cfg.simulator.emulator_launcher.gpu_mode = 'swiftshader_indirect'

    env = cast(Any, loader.load(env_cfg))
    pstate = cast(Any, state.PlaygroundState())
    pstate.set_env(env)
    pstate.set_status('Running')
    bridge = mcp_bridge.PlaygroundMcpBridge(pstate)
    max_steps = (
        _MAX_STEPS_2048.value if task_name == '2048' else _MAX_STEPS_FLOOD.value
    )

    try:
      for model_name in _MODELS.value:
        for trial_idx in range(1, _TRIALS.value + 1):
          print(
              f'\n>>> [{_DEVICE_MODE.value}] Task={task_name} | '
              f'Model={model_name} ({_EXECUTION_TARGET.value}) | '
              f'Trial={trial_idx}'
          )
          ts = env.reset()
          pstate.reset_cumulative_reward()
          pstate.clear_action_queue()
          pstate.set_last_timestep(ts)
          for _ in range(5):
            ts = env.step({'action_type': 1, 'touch_position': [0.0, 0.0]})
            time.sleep(0.08)
          pstate.set_last_timestep(ts)
          with pstate.frame_lock:
            pstate.current_frame = _encode_png(ts.observation['pixels'])

          provider = providers.create_provider(
              model_name,
              execution_target=_EXECUTION_TARGET.value,
              device_serial=_DEVICE_SERIAL.value or None,
              adb_path=_ADB_PATH.value,
              enable_vision=_ENABLE_VISION.value,
              max_output_tokens=96,
          )
          sys_prompt, goal_prompt = _task_prompts(task_name)
          tools_schema = bridge.list_tools()

          latencies: list[float] = []
          step_records: list[dict[str, Any]] = []
          total_reward = 0.0
          solved = False
          history_lines: list[str] = []

          if hw_sampler:
            hw_sampler.start()
          t_start = time.time()

          try:
            for step in range(1, max_steps + 1):
              cur_ts = pstate.get_last_timestep()
              board_summary = _extract_board_summary(
                  cur_ts.observation['pixels'], task_name
              )
              screenshot_bytes = (
                  bridge.get_screenshot_bytes()
                  if _ENABLE_VISION.value
                  else None
              )
              recent = (
                  '\n'.join(history_lines[-4:]) if history_lines else 'None.'
              )
              user_prompt = (
                  f'GOAL: {goal_prompt}\n'
                  f'STEP: {step}/{max_steps}\n'
                  f'{board_summary}\n'
                  f'HISTORY:\n{recent}\n'
                  'Output JSON action now:'
              )

              resp = provider.generate(
                  system_prompt=sys_prompt,
                  user_prompt=user_prompt,
                  screenshot_bytes=screenshot_bytes,
                  tools_schema=tools_schema,
              )
              latencies.append(resp.latency_ms)
              thought_str = resp.thoughts[0] if resp.thoughts else ''

              if resp.tool_calls:
                tc = resp.tool_calls[0]
                if tc.name == 'done':
                  break
                bridge.execute_tool(tc.name, tc.args)
                r, ended = _drain_actions(env, pstate)
                total_reward += r
                history_lines.append(
                    f'Step {step}: {tc.name}({json.dumps(tc.args)}) -> '
                    f'reward={r}'
                )
              else:
                tc = providers.ToolCall(name='none', args={})
                r, ended = 0.0, False

              bp = telemetry.fetch_battery_power_metrics(env)
              pwr = round(bp.power_mw, 1) if bp else 0.0
              temp_c = round(bp.temperature_celsius, 1) if bp else 25.0

              step_rec = {
                  'step': step,
                  'tool': tc.name,
                  'args': tc.args,
                  'latency_ms': round(resp.latency_ms, 1),
                  'step_reward': r,
                  'cumulative_reward': total_reward,
                  'power_mw': pwr,
                  'temp_c': temp_c,
                  'thought': thought_str[:140],
              }
              step_records.append(step_rec)
              csv_rows.append({
                  'device_mode': _DEVICE_MODE.value,
                  'task': task_name,
                  'model': f'{model_name}-{_EXECUTION_TARGET.value}',
                  'trial': trial_idx,
                  **step_rec,
              })
              print(
                  f'  Step {step:2d} | {tc.name} {json.dumps(tc.args)} | '
                  f'lat={resp.latency_ms:.0f}ms | '
                  f'reward=+{r:.1f} (total={total_reward:.1f})'
              )
              if task_name != '2048' and (total_reward >= 1.0 or ended):
                solved = total_reward >= 1.0
                print(f'  *** Episode Solved on Step {step}! ***')
                break
          finally:
            provider.close()

          wall_s = time.time() - t_start
          hw_bat = hw_sampler.stop_and_summarize() if hw_sampler else {}
          avg_lat = sum(latencies) / len(latencies) if latencies else 0.0
          results.append({
              'device_mode': _DEVICE_MODE.value,
              'execution_target': _EXECUTION_TARGET.value,
              'enable_vision': _ENABLE_VISION.value,
              'task': task_name,
              'model': model_name,
              'trial': trial_idx,
              'solved': solved if task_name != '2048' else (total_reward > 0),
              'steps_completed': len(step_records),
              'cumulative_reward': total_reward,
              'avg_latency_ms': round(avg_lat, 1),
              'total_wall_time_s': round(wall_s, 2),
              'hardware_battery_telemetry': hw_bat,
              'steps': step_records,
          })

          with open(_OUTPUT_JSON.value, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
          if csv_rows:
            with open(
                _OUTPUT_CSV.value, 'w', newline='', encoding='utf-8'
            ) as cf:
              writer = csv.DictWriter(cf, fieldnames=list(csv_rows[0].keys()))
              writer.writeheader()
              writer.writerows(csv_rows)
    finally:
      env.close()


if __name__ == '__main__':
  app.run(main)
