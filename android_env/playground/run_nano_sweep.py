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

"""Multi-task and on-device Nano / frontier benchmark sweep for AndroidEnv.

Evaluates on-device (`on-device-vision`, `nano`) and cloud frontier models
across multiple tasks (`2048`, `sgtpuzzles_flood_3x3_easy`,
`sgtpuzzles_flood_4x4_easy`, `sgtpuzzles_flood_5x5`) on either an Android
emulator or a physical Android device with real PMIC battery shunt telemetry.
"""

from collections.abc import Sequence
import io
import json
import os
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
    'device_mode',
    'emulator',
    ['emulator', 'real_device'],
    'Whether to run on an Android Virtual Device or a physical USB device.',
)
_AVD_NAME = flags.DEFINE_string(
    'avd_name', 'pixel_6_api_34', 'AVD name when device_mode=emulator.'
)
_DEVICE_SERIAL = flags.DEFINE_string(
    'device_serial', '', 'Device serial when device_mode=real_device.'
)
_ADB_PATH = flags.DEFINE_string('adb_path', 'adb', 'Path to the adb binary.')
_MODELS = flags.DEFINE_list(
    'models',
    [
        'on-device-vision',
        'gemini-3.1-flash-lite-preview',
        'gemini-3-flash-preview',
        'gemini-3.1-pro-preview',
        'gpt-4o-2024-08-06',
        'claude-3-5-sonnet-v2@20241022',
    ],
    'Comma-separated list of models to evaluate.',
)
_TASKS = flags.DEFINE_list(
    'tasks',
    [
        'sgtpuzzles_flood_3x3_easy',
        'sgtpuzzles_flood_4x4_easy',
        'sgtpuzzles_flood_5x5',
        '2048',
    ],
    'Comma-separated list of tasks to evaluate.',
)
_TRIALS = flags.DEFINE_integer(
    'trials', 1, 'Number of trials per (model, task).'
)
_MAX_STEPS_FLOOD = flags.DEFINE_integer(
    'max_steps_flood', 12, 'Max steps for Flood It tasks.'
)
_MAX_STEPS_2048 = flags.DEFINE_integer(
    'max_steps_2048', 10, 'Max steps for 2048.'
)
_OUTPUT_JSON = flags.DEFINE_string(
    'output_json',
    '/tmp/nano_and_frontier_multi_task_sweep.json',
    'Output JSON file path.',
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
    """Stops the polling thread and computes integrated energy in mJ."""
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

    delta_uah = (
        self._samples[0]['charge_counter_uah']
        - self._samples[-1]['charge_counter_uah']
    )
    return {
        'samples_count': len(self._samples),
        'avg_power_mw': round(sum(powers) / len(powers), 2),
        'peak_power_mw': round(max(powers), 2),
        'min_power_mw': round(min(powers), 2),
        'integrated_energy_mj': round(energy_mj, 2),
        'charge_delta_uah': delta_uah,
        'start_temp_c': temps[0],
        'end_temp_c': temps[-1],
        'start_level_pct': self._samples[0]['level_percent'],
        'end_level_pct': self._samples[-1]['level_percent'],
    }


def _encode_png(rgb_pixels: Any) -> bytes:
  img = Image.fromarray(rgb_pixels, mode='RGB')
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


def _task_prompts(task_name: str) -> tuple[str, str]:
  """Returns `(system_prompt, goal_prompt)` for the given task."""
  if task_name == '2048':
    sys_p = (
        'You are an autonomous Android Agent controlling 2048 via MCP tools.\n'
        'Use `swipe` to slide tiles:\n'
        '- UP: swipe(start_x=0.5, start_y=0.7, end_x=0.5, end_y=0.3)\n'
        '- DOWN: swipe(start_x=0.5, start_y=0.3, end_x=0.5, end_y=0.7)\n'
        '- LEFT: swipe(start_x=0.75, start_y=0.5, end_x=0.25, end_y=0.5)\n'
        '- RIGHT: swipe(start_x=0.25, start_y=0.5, end_x=0.75, end_y=0.5)\n'
        'Call ONE swipe tool per turn.'
    )
    goal_p = (
        'Play 2048 and maximize your score! Keep your largest tile anchored '
        'in a corner and alternate directions. If a swipe direction did not '
        'change the board, immediately pick a different direction!'
    )
    return sys_p, goal_p

  grid_desc = '3x3'
  coords_hint = (
      '- Row 0 centers: y=0.32 | Col 0: x=0.22, Col 1: x=0.50, Col 2: x=0.78\n'
      '- Row 1 centers: y=0.50 | Col 0: x=0.22, Col 1: x=0.50, Col 2: x=0.78\n'
      '- Row 2 centers: y=0.68 | Col 0: x=0.22, Col 1: x=0.50, Col 2: x=0.78'
  )
  if '4x4' in task_name:
    grid_desc = '4x4'
    coords_hint = (
        '- Rows y in {0.29, 0.43, 0.57, 0.71}\n'
        '- Cols x in {0.19, 0.40, 0.60, 0.81}'
    )
  elif '5x5' in task_name:
    grid_desc = '5x5'
    coords_hint = (
        '- Rows y in {0.27, 0.38, 0.50, 0.62, 0.73}\n'
        '- Cols x in {0.16, 0.33, 0.50, 0.67, 0.84}'
    )

  sys_p = (
      f'You are an autonomous Android Agent playing Flood It ({grid_desc}) '
      'via MCP tools. Inspect the colored grid in the screenshot and call '
      '`tap(x, y)` on a square whose color you want to flood-fill into the '
      'top-left connected component. Call ONE `tap(x, y)` per turn.'
  )
  goal_p = (
      f'Play Flood It ({grid_desc})! Flood-fill the entire {grid_desc} grid '
      'with a SINGLE color starting from the top-left corner (0, 0) in as '
      'few moves as possible.\n'
      f'Grid cell centers:\n{coords_hint}\n'
      'Tap a square of the color that absorbs the most adjacent tiles!'
  )
  return sys_p, goal_p


def run_single_trial(
    env: Any,
    pstate: Any,
    bridge: mcp_bridge.PlaygroundMcpBridge,
    hw_sampler: HardwareBatterySampler | None,
    model_name: str,
    task_name: str,
    trial_idx: int,
    max_steps: int,
) -> dict[str, Any]:
  """Executes one episode of `(model_name, task_name)`."""
  print(
      f'\n>>> [{_DEVICE_MODE.value}] Task={task_name} | Model={model_name} | '
      f'Trial={trial_idx}'
  )
  ts = env.reset()
  pstate.reset_cumulative_reward()
  pstate.clear_action_queue()
  pstate.set_last_timestep(ts)
  with pstate.frame_lock:
    pstate.current_frame = _encode_png(ts.observation['pixels'])

  for _ in range(5):
    ts = env.step({'action_type': 1, 'touch_position': [0.0, 0.0]})
    time.sleep(0.08)
  pstate.set_last_timestep(ts)
  with pstate.frame_lock:
    pstate.current_frame = _encode_png(ts.observation['pixels'])

  kwargs: dict[str, Any] = {}
  if model_name.startswith(('nano', 'on-device')):
    kwargs['env'] = env
    if _DEVICE_SERIAL.value:
      kwargs['device_serial'] = _DEVICE_SERIAL.value
    kwargs['adb_path'] = _ADB_PATH.value

  provider = providers.create_provider(model_name, **kwargs)
  tools_schema = bridge.list_tools()
  sys_prompt, goal_prompt = _task_prompts(task_name)

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
      screenshot_bytes = bridge.get_screenshot_bytes()
      dev_info = bridge.get_device_info()
      recent = '\n'.join(history_lines[-5:]) if history_lines else 'None yet.'
      user_prompt = (
          f'GOAL: {goal_prompt}\n'
          f'STEP: {step} / {max_steps}\n'
          f'DEVICE INFO:\n{dev_info}\n\n'
          f'RECENT HISTORY:\n{recent}\n\n'
          'Select your next MCP tool call.'
      )

      resp = provider.generate(
          system_prompt=sys_prompt,
          user_prompt=user_prompt,
          screenshot_bytes=screenshot_bytes,
          tools_schema=tools_schema,
          thinking_level='LOW',
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
            f'reward=+{r:.1f} (total={total_reward:.1f})'
        )
        if task_name != '2048' and (total_reward >= 1.0 or ended):
          solved = total_reward >= 1.0
          print(f'  *** Episode Finished on Step {step}! solved={solved} ***')
          break
      else:
        step_records.append({
            'step': step,
            'tool': 'none',
            'latency_ms': round(resp.latency_ms, 1),
            'step_reward': 0.0,
            'cumulative_reward': total_reward,
        })
  finally:
    provider.close()

  wall_s = time.time() - t_start
  hw_battery = hw_sampler.stop_and_summarize() if hw_sampler else {}
  bp = telemetry.fetch_battery_power_metrics(env)
  avg_lat = sum(latencies) / len(latencies) if latencies else 0.0

  return {
      'device_mode': _DEVICE_MODE.value,
      'device_serial': _DEVICE_SERIAL.value or _AVD_NAME.value,
      'task': task_name,
      'model': model_name,
      'trial': trial_idx,
      'solved': solved if task_name != '2048' else (total_reward > 0),
      'steps_completed': len(step_records),
      'cumulative_reward': total_reward,
      'avg_latency_ms': round(avg_lat, 1),
      'min_latency_ms': round(min(latencies), 1) if latencies else 0.0,
      'max_latency_ms': round(max(latencies), 1) if latencies else 0.0,
      'total_wall_time_s': round(wall_s, 2),
      'apk_battery_power_mw': round(bp.power_mw, 1) if bp else 0.0,
      'hardware_battery_telemetry': hw_battery,
      'steps': step_records,
  }


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  results: list[dict[str, Any]] = []
  if os.path.exists(_OUTPUT_JSON.value):
    try:
      with open(_OUTPUT_JSON.value, 'r', encoding='utf-8') as f:
        results = json.load(f)
    except (OSError, json.JSONDecodeError):
      results = []

  hw_sampler = None
  if _DEVICE_MODE.value == 'real_device':
    hw_sampler = HardwareBatterySampler(
        _ADB_PATH.value, _DEVICE_SERIAL.value or None
    )

  for task_name in _TASKS.value:
    print(
        f'\n================ LOADING TASK: {task_name} '
        f'({_DEVICE_MODE.value}) ================'
    )
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
      for m in _MODELS.value:
        for t_idx in range(1, _TRIALS.value + 1):
          try:
            res = run_single_trial(
                env,
                pstate,
                bridge,
                hw_sampler,
                m,
                task_name,
                t_idx,
                max_steps,
            )
            results.append(res)
          except Exception as e:  # pylint: disable=broad-exception-caught
            print(f'ERROR on {m} ({task_name}, trial {t_idx}): {e}')
            results.append({
                'device_mode': _DEVICE_MODE.value,
                'task': task_name,
                'model': m,
                'trial': t_idx,
                'error': str(e),
            })
          out_dir = os.path.dirname(_OUTPUT_JSON.value)
          if out_dir:
            os.makedirs(out_dir, exist_ok=True)
          with open(_OUTPUT_JSON.value, 'w', encoding='utf-8') as f:
            json.dump(results, f, indent=2)
    finally:
      env.close()


if __name__ == '__main__':
  app.run(main)
