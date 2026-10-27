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

"""Playground MCP Bridge.

Bridges MCP tools (`get_screenshot`, `get_ui_elements`, `get_device_info`,
`tap`, `swipe`, `press_key`) onto `PlaygroundState` so that an LLM agent or
external MCP client can inspect the screen and enqueue actions directly into the
Playground's `action_queue`.
"""

import base64
import json
import queue
import threading
import time
from typing import Any

from android_env.components import telemetry
from android_env.mcp import android_mcp_tools
from android_env.playground import state
from android_env.proto.a11y import android_accessibility_forest_pb2
from google.protobuf import json_format

_ORIENTATION_NAMES: dict[int, str] = {
    0: 'PORTRAIT_0',
    1: 'LANDSCAPE_90',
    2: 'PORTRAIT_180',
    3: 'LANDSCAPE_270',
}


def _install_playground_state_extensions() -> None:
  """Attaches MCP/agent state accessors to PlaygroundState if not present."""
  cls: Any = state.PlaygroundState
  if hasattr(cls, 'get_env'):
    return

  def _get_lock(self: Any) -> threading.Lock:
    lock = getattr(self, '_ext_lock', None)
    if lock is None:
      lock = threading.Lock()
      setattr(self, '_ext_lock', lock)
    return lock

  def set_env(self: Any, env: Any) -> None:
    with _get_lock(self):
      setattr(self, '_ext_env', env)

  def get_env(self: Any) -> Any:
    with _get_lock(self):
      return getattr(self, '_ext_env', None)

  def set_orientation(self: Any, orientation: int) -> None:
    with _get_lock(self):
      setattr(self, '_ext_orientation', int(orientation))

  def get_orientation(self: Any) -> int:
    with _get_lock(self):
      return int(getattr(self, '_ext_orientation', 0))

  def set_last_timestep(self: Any, timestep: Any) -> None:
    with _get_lock(self):
      setattr(self, '_ext_last_timestep', timestep)
      setattr(
          self,
          '_ext_timestep_seq',
          int(getattr(self, '_ext_timestep_seq', 0)) + 1,
      )
      if timestep is not None and getattr(timestep, 'reward', None) is not None:
        try:
          r = float(timestep.reward)
        except (TypeError, ValueError):
          r = 0.0
        setattr(
            self,
            '_ext_cumulative_reward',
            float(getattr(self, '_ext_cumulative_reward', 0.0)) + r,
        )

  def get_last_timestep(self: Any) -> Any:
    with _get_lock(self):
      return getattr(self, '_ext_last_timestep', None)

  def get_last_timestep_with_seq(self: Any) -> tuple[Any, int]:
    with _get_lock(self):
      return (
          getattr(self, '_ext_last_timestep', None),
          int(getattr(self, '_ext_timestep_seq', 0)),
      )

  def set_reload_status(self: Any, status: str, error: str = '') -> None:
    with _get_lock(self):
      setattr(self, '_ext_reload_status', status)
      setattr(self, '_ext_reload_error', error)

  def get_reload_status(self: Any) -> dict[str, str]:
    with _get_lock(self):
      return {
          'status': str(getattr(self, '_ext_reload_status', 'idle')),
          'error': str(getattr(self, '_ext_reload_error', '')),
      }

  def get_cumulative_reward(self: Any) -> float:
    with _get_lock(self):
      return float(getattr(self, '_ext_cumulative_reward', 0.0))

  def reset_cumulative_reward(self: Any) -> None:
    with _get_lock(self):
      setattr(self, '_ext_cumulative_reward', 0.0)

  def clear_action_queue(self: Any) -> None:
    while True:
      try:
        self.action_queue.get_nowait()
      except queue.Empty:
        break

  cls.set_env = set_env
  cls.get_env = get_env
  cls.set_orientation = set_orientation
  cls.get_orientation = get_orientation
  cls.set_last_timestep = set_last_timestep
  cls.get_last_timestep = get_last_timestep
  cls.get_last_timestep_with_seq = get_last_timestep_with_seq
  cls.set_reload_status = set_reload_status
  cls.get_reload_status = get_reload_status
  cls.get_cumulative_reward = get_cumulative_reward
  cls.reset_cumulative_reward = reset_cumulative_reward
  cls.clear_action_queue = clear_action_queue


_install_playground_state_extensions()


def _format_forest(
    forest: android_accessibility_forest_pb2.AndroidAccessibilityForest,
    output_format: str = 'tree',
) -> str:
  """Formats an `AndroidAccessibilityForest` proto as a tree or JSON string."""
  if output_format == 'json':
    return json_format.MessageToJson(forest)

  lines: list[str] = []
  for window in forest.windows:
    lines.append(f'[Window] "{window.title}" id={window.id}')
    if window.HasField('tree'):
      nodes_by_id = {n.unique_id: n for n in window.tree.nodes}
      root_ids = [n.unique_id for n in window.tree.nodes if n.depth == 0]
      visited: set[int] = set()
      for root_id in root_ids:
        android_mcp_tools._render_node(  # pylint: disable=protected-access
            nodes_by_id, root_id, indent=1, lines=lines, visited=visited
        )
  return '\n'.join(lines)


class PlaygroundMcpBridge:
  """Exposes MCP tools backed by PlaygroundState."""

  def __init__(self, playground_state: state.PlaygroundState) -> None:
    """Initializes the bridge with a shared PlaygroundState instance.

    Args:
      playground_state: Shared state of the AndroidEnv Playground.
    """
    self._state: Any = playground_state

  def get_screenshot_bytes(self) -> bytes | None:
    """Returns raw PNG screenshot bytes from PlaygroundState, or None."""
    with self._state.frame_lock:
      return self._state.current_frame

  def get_screenshot(self) -> str:
    """Returns base64-encoded PNG screenshot of the current Playground frame.

    Returns:
      Base64-encoded PNG screenshot string.

    Raises:
      RuntimeError: If no screenshot is available yet.
    """
    frame = self.get_screenshot_bytes()
    if frame is None:
      raise RuntimeError('No screenshot available in PlaygroundState yet.')
    return base64.b64encode(frame).decode('ascii')

  def get_ui_elements(self, output_format: str = 'tree') -> str:
    """Returns accessibility hierarchy of the current screen if available.

    Args:
      output_format: Either `'tree'` for human-readable hierarchy or `'json'`
        for serialized JSON.

    Returns:
      Formatted accessibility hierarchy string or diagnostic message.

    Raises:
      ValueError: If `output_format` is not `'tree'` or `'json'`.
    """
    if output_format not in ('tree', 'json'):
      raise ValueError(
          f"Invalid output_format {output_format!r}. Must be 'tree' or 'json'."
      )

    env = self._state.get_env()
    if env is None:
      return 'No active environment connected.'

    try:
      if hasattr(env, 'task_extras'):
        extras = env.task_extras(latest_only=True)
        if extras and 'accessibility_tree' in extras:
          tree_data = extras['accessibility_tree']
          if hasattr(tree_data, 'shape') and tree_data.size > 0:
            item = tree_data.item(0)
            if isinstance(
                item,
                android_accessibility_forest_pb2.AndroidAccessibilityForest,
            ):
              return _format_forest(item, output_format)
            if isinstance(item, bytes):
              forest = android_accessibility_forest_pb2.AndroidAccessibilityForest.FromString(
                  item
              )
              return _format_forest(forest, output_format)
            return str(item)
    except (AttributeError, TypeError, ValueError, RuntimeError):
      pass

    ts = self._state.get_last_timestep()
    if ts is not None and isinstance(ts.observation, dict):
      if 'accessibility_tree' in ts.observation:
        obs_tree = ts.observation['accessibility_tree']
        if isinstance(
            obs_tree,
            android_accessibility_forest_pb2.AndroidAccessibilityForest,
        ):
          return _format_forest(obs_tree, output_format)

    return (
        'Accessibility tree not available in current observation '
        '(use visual screenshot coordinates).'
    )

  def get_device_info(self) -> str:
    """Returns device orientation, status, and latest reward/step metadata."""
    orientation_code = self._state.get_orientation()
    info: dict[str, Any] = {
        'status': self._state.get_status(),
        'orientation': orientation_code,
        'orientation_name': _ORIENTATION_NAMES.get(
            orientation_code, f'UNKNOWN_{orientation_code}'
        ),
        'cumulative_reward': self._state.get_cumulative_reward(),
    }
    ts = self._state.get_last_timestep()
    if ts is not None:
      info['step_type'] = int(ts.step_type)
      info['reward'] = float(ts.reward) if ts.reward is not None else 0.0
      if isinstance(ts.observation, dict) and 'pixels' in ts.observation:
        pixels = ts.observation['pixels']
        if hasattr(pixels, 'shape'):
          info['screen_height'] = int(pixels.shape[0])
          info['screen_width'] = int(pixels.shape[1])

    env = self._state.get_env()
    if env is not None:
      battery_metrics = telemetry.fetch_battery_power_metrics(env)
      if battery_metrics is not None:
        info['battery_power'] = {
            'level_percent': battery_metrics.level_percent,
            'current_now_ua': battery_metrics.current_now_ua,
            'voltage_mv': battery_metrics.voltage_mv,
            'power_mw': round(battery_metrics.power_mw, 2),
            'temperature_celsius': round(
                battery_metrics.temperature_celsius, 1
            ),
            'status': battery_metrics.status,
            'plugged_source': battery_metrics.plugged_source,
            'charge_counter_uah': battery_metrics.charge_counter_uah,
            'thermal_status': battery_metrics.thermal_status,
            'energy_counter_nwh': battery_metrics.energy_counter_nwh,
        }

    return json.dumps(info, indent=2)

  def tap(self, x: float, y: float) -> str:
    """Taps at the given normalized screen coordinates [0.0, 1.0].

    Args:
      x: Normalized horizontal coordinate in [0.0, 1.0].
      y: Normalized vertical coordinate in [0.0, 1.0].

    Returns:
      Confirmation string.

    Raises:
      ValueError: If `(x, y)` is outside `[0.0, 1.0]`.
    """
    x = float(x)
    y = float(y)
    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
      raise ValueError(
          f'Coordinates ({x}, {y}) out of bounds. Must be in range [0.0, 1.0].'
      )

    self._state.action_queue.put({'type': 'down', 'x': x, 'y': y})
    time.sleep(0.08)
    self._state.action_queue.put({'type': 'up', 'x': x, 'y': y})
    self._state.add_log(f'[MCP] tap({x:.3f}, {y:.3f})')
    return f'Tapped at ({x:.3f}, {y:.3f})'

  def swipe(
      self,
      start_x: float,
      start_y: float,
      end_x: float,
      end_y: float,
      steps: int = 8,
  ) -> str:
    """Swipes from `(start_x, start_y)` to `(end_x, end_y)` in normalized coords.

    Args:
      start_x: Starting horizontal coordinate in [0.0, 1.0].
      start_y: Starting vertical coordinate in [0.0, 1.0].
      end_x: Ending horizontal coordinate in [0.0, 1.0].
      end_y: Ending vertical coordinate in [0.0, 1.0].
      steps: Number of interpolation steps (>= 1).

    Returns:
      Confirmation string.

    Raises:
      ValueError: If coordinates are out of bounds or `steps < 1`.
    """
    start_x = float(start_x)
    start_y = float(start_y)
    end_x = float(end_x)
    end_y = float(end_y)
    steps = int(steps)

    if not (
        0.0 <= start_x <= 1.0
        and 0.0 <= start_y <= 1.0
        and 0.0 <= end_x <= 1.0
        and 0.0 <= end_y <= 1.0
    ):
      raise ValueError(
          'Coordinates must be in range [0.0, 1.0]. Got'
          f' start=({start_x}, {start_y}), end=({end_x}, {end_y}).'
      )
    if steps < 1:
      raise ValueError(f'steps must be at least 1, got {steps}.')

    self._state.action_queue.put({'type': 'down', 'x': start_x, 'y': start_y})
    time.sleep(0.03)
    for i in range(1, steps + 1):
      t = i / steps
      x = start_x + (end_x - start_x) * t
      y = start_y + (end_y - start_y) * t
      self._state.action_queue.put({'type': 'move', 'x': x, 'y': y})
      time.sleep(0.025)
    self._state.action_queue.put({'type': 'up', 'x': end_x, 'y': end_y})
    self._state.add_log(
        f'[MCP] swipe(({start_x:.3f}, {start_y:.3f}) ->'
        f' ({end_x:.3f}, {end_y:.3f}), steps={steps})'
    )
    return (
        f'Swiped from ({start_x:.3f}, {start_y:.3f}) to'
        f' ({end_x:.3f}, {end_y:.3f})'
    )

  def press_key(self, key: str) -> str:
    """Presses an Android system button (`home`, `back`, `overview`) or keycode.

    Args:
      key: Key name (`'home'`, `'back'`, `'overview'`) or keycode string.

    Returns:
      Confirmation string.
    """
    key_str = str(key).lower().strip()
    self._state.action_queue.put({'type': 'button', 'button': key_str})
    self._state.add_log(f'[MCP] press_key({key_str})')
    return f'Pressed key {key_str}'

  def wait(self, seconds: float = 1.0) -> str:
    """Waits for the specified duration (capped at 5.0s)."""
    duration = max(0.0, min(float(seconds), 5.0))
    time.sleep(duration)
    self._state.add_log(f'[MCP] wait({duration:.1f}s)')
    return f'Waited {duration:.1f}s'

  def list_tools(self, role: str = 'all') -> list[dict[str, Any]]:
    """Returns JSON schema declarations for all available MCP tools."""
    del role
    return [
        {
            'name': 'tap',
            'description': (
                'Tap on the Android screen at normalized coordinates (x, y) '
                'where 0.0 <= x <= 1.0 (left to right) and 0.0 <= y <= 1.0 '
                '(top to bottom).'
            ),
            'parameters': {
                'type': 'OBJECT',
                'properties': {
                    'x': {
                        'type': 'NUMBER',
                        'description': 'Normalized horizontal coordinate [0-1]',
                    },
                    'y': {
                        'type': 'NUMBER',
                        'description': 'Normalized vertical coordinate [0-1]',
                    },
                },
                'required': ['x', 'y'],
            },
        },
        {
            'name': 'swipe',
            'description': (
                'Swipe on the Android screen from (start_x, start_y) to '
                '(end_x, end_y) in normalized coordinates [0.0, 1.0]. '
                'For 2048 or directional games: '
                'Swipe UP: (0.5, 0.7) -> (0.5, 0.3); '
                'Swipe DOWN: (0.5, 0.3) -> (0.5, 0.7); '
                'Swipe LEFT: (0.7, 0.5) -> (0.3, 0.5); '
                'Swipe RIGHT: (0.3, 0.5) -> (0.7, 0.5).'
            ),
            'parameters': {
                'type': 'OBJECT',
                'properties': {
                    'start_x': {
                        'type': 'NUMBER',
                        'description': 'Starting X coordinate [0-1]',
                    },
                    'start_y': {
                        'type': 'NUMBER',
                        'description': 'Starting Y coordinate [0-1]',
                    },
                    'end_x': {
                        'type': 'NUMBER',
                        'description': 'Ending X coordinate [0-1]',
                    },
                    'end_y': {
                        'type': 'NUMBER',
                        'description': 'Ending Y coordinate [0-1]',
                    },
                    'steps': {
                        'type': 'INTEGER',
                        'description': (
                            'Number of interpolation steps (default 8)'
                        ),
                    },
                },
                'required': ['start_x', 'start_y', 'end_x', 'end_y'],
            },
        },
        {
            'name': 'press_key',
            'description': (
                'Press an Android navigation button: "back", "home", or '
                '"overview".'
            ),
            'parameters': {
                'type': 'OBJECT',
                'properties': {
                    'key': {
                        'type': 'STRING',
                        'description': 'One of "back", "home", "overview".',
                    },
                },
                'required': ['key'],
            },
        },
        {
            'name': 'get_ui_elements',
            'description': (
                'Inspect the accessibility UI tree of the current Android '
                'screen.'
            ),
            'parameters': {
                'type': 'OBJECT',
                'properties': {
                    'output_format': {
                        'type': 'STRING',
                        'description': 'Either "tree" or "json".',
                    },
                },
            },
        },
        {
            'name': 'get_device_info',
            'description': (
                'Get current Android device status, orientation, screen '
                'dimensions, and reward.'
            ),
            'parameters': {
                'type': 'OBJECT',
                'properties': {},
            },
        },
        {
            'name': 'wait',
            'description': 'Wait for UI animations to settle.',
            'parameters': {
                'type': 'OBJECT',
                'properties': {
                    'seconds': {
                        'type': 'NUMBER',
                        'description': 'Seconds to wait (0.1 to 5.0).',
                    },
                },
            },
        },
        {
            'name': 'done',
            'description': (
                'Call this tool when the user goal or task has been '
                'completed, or if you have finished playing.'
            ),
            'parameters': {
                'type': 'OBJECT',
                'properties': {
                    'summary': {
                        'type': 'STRING',
                        'description': (
                            'Final summary of what was accomplished.'
                        ),
                    },
                },
                'required': ['summary'],
            },
        },
    ]

  def execute_tool(self, name: str, args: dict[str, Any]) -> dict[str, Any]:
    """Executes a named MCP tool and returns a structured result dict."""
    try:
      if name == 'tap':
        res = self.tap(args['x'], args['y'])
      elif name == 'swipe':
        res = self.swipe(
            args['start_x'],
            args['start_y'],
            args['end_x'],
            args['end_y'],
            args.get('steps', 8),
        )
      elif name == 'press_key':
        res = self.press_key(args['key'])
      elif name == 'get_ui_elements':
        res = self.get_ui_elements(args.get('output_format', 'tree'))
      elif name == 'get_device_info':
        res = self.get_device_info()
      elif name == 'get_screenshot':
        res = self.get_screenshot()
      elif name == 'wait':
        res = self.wait(args.get('seconds', 1.0))
      elif name == 'done':
        summary = args.get('summary', 'Task completed.')
        self._state.add_log(f'[MCP] done: {summary}')
        return {'status': 'done', 'output': summary}
      else:
        return {'status': 'error', 'output': f'Unknown tool: {name}'}
      return {'status': 'ok', 'output': res}
    except Exception as e:  # pylint: disable=broad-exception-caught
      return {'status': 'error', 'output': str(e)}

  def call_tool(
      self, tool_name: str, args: dict[str, Any] | None = None
  ) -> dict[str, Any]:
    """Executes a tool and returns a WebSocket-compatible result dict."""
    res = self.execute_tool(tool_name, args or {})
    if res['status'] == 'error':
      return {
          'tool': tool_name,
          'success': False,
          'error': res['output'],
      }
    return {
        'tool': tool_name,
        'success': True,
        'result': res['output'],
    }
