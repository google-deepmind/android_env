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

"""FastMCP tool implementations for direct AndroidDevice connection.

Exposes Android device inspection, interaction, telemetry, and task lifecycle
capabilities to LLM agents by receiving a connected `AndroidDevice` instance,
bypassing the RL interface (`dm_env`).
"""

import ast
import base64
from collections.abc import Mapping, Sequence
import io
import json
import re
import tempfile
from typing import Any

from absl import logging
from android_env.components import android_device as android_device_mod
from android_env.components import setup_step_interpreter
from android_env.components import telemetry

from android_env.mcp import errors
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2
from android_env.proto import task_pb2
from android_env.proto.a11y import android_accessibility_node_info_pb2
from google.protobuf import json_format
from google.protobuf import text_format
from mcp.server import fastmcp
import numpy as np
from PIL import Image

_DEFAULT_SIGNALS = frozenset({
    device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
    device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
    device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE,
    device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS,
    device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER,
})
_LOGCAT_PREFIX_RE = re.compile(
    r'^\s*(?:(?:\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+|\d+\.\d+)'
    r'\s+\d+\s+\d+\s+\S\s+[^:]*:\s*|[A-Z]/[^:]*:\s*)'
)

COMMON_TOOLS: tuple[str, ...] = (
    'get_screenshot',
    'get_ui_elements',
    'get_device_info',
)
WORKER_TOOLS: tuple[str, ...] = (
    'get_screenshot',
    'get_ui_elements',
    'get_device_info',
    'tap',
    'swipe',
    'press_key',
)
MANAGER_TOOLS: tuple[str, ...] = (
    'get_screenshot',
    'get_ui_elements',
    'get_device_info',
    'get_battery_metrics',
    'load_task',
    'reset_task',
    'get_task_info',
    'get_task_metrics',
)
VALID_ROLES: tuple[str, ...] = ('all', 'worker', 'manager')


def fetch_apks_for_task(
    task: task_pb2.Task, task_tmp_dir: str | None = None
) -> task_pb2.Task:
  """Fetches APKs specified in `task` and returns the updated `Task` proto.

  Args:
    task: `task_pb2.Task` proto definition.
    task_tmp_dir: Optional local directory to store fetched APKs. If `None`,
      uses the default system temporary directory.

  Returns:
    Updated `task_pb2.Task` proto with resolved local filesystem APK paths.
  """
  del task_tmp_dir
  return task


def _extract_screenshot(
    state: device_env_service_pb2.DeviceState,
) -> np.ndarray:
  """Extracts decoded RGB screenshot pixels from `DeviceState` signals.

  Args:
    state: A `DeviceState` protobuf containing device signals.

  Returns:
    A NumPy array of shape `(height, width, 3)` with `uint8` dtype containing
    decoded RGB pixel values.

  Raises:
    errors.DeviceConnectionError: If no decoded screenshot signal is found in
      the provided device state.
  """
  for signal in state.signals:
    if (
        signal.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
        and signal.HasField('screenshot')
        and signal.screenshot.HasField('decoded')
    ):
      decoded = signal.screenshot.decoded
      return np.frombuffer(decoded.raw_pixels, dtype=np.uint8).reshape(
          (decoded.height, decoded.width, 3)
      )
  raise errors.DeviceConnectionError(
      'No decoded screenshot signal found in device state.'
  )


def _render_node(
    nodes_by_id: Mapping[
        int, android_accessibility_node_info_pb2.AndroidAccessibilityNodeInfo
    ],
    node_id: int,
    indent: int,
    lines: list[str],
    visited: set[int] | None = None,
) -> None:
  """Recursively renders an accessibility node and its children into text lines.

  Args:
    nodes_by_id: Mapping from unique node ID to `AndroidAccessibilityNodeInfo`
      protobuf messages.
    node_id: The ID of the current accessibility node to render.
    indent: The current indentation level in the tree display.
    lines: Output list of strings where rendered line entries are appended.
    visited: Set of already visited node IDs used to prevent infinite recursion
      in cyclic graphs.
  """
  if visited is None:
    visited = set()
  if node_id in visited:
    return
  visited.add(node_id)

  node = nodes_by_id.get(node_id)
  if node is None:
    return

  prefix = '  ' * indent
  text = node.text or node.content_description or ''
  bounds = node.bounds_in_screen
  bounds_str = f'{{{bounds.left},{bounds.top},{bounds.right},{bounds.bottom}}}'

  flags = []
  if node.is_clickable:
    flags.append('clickable')
  if node.is_scrollable:
    flags.append('scrollable')
  if node.is_checked:
    flags.append('checked')
  if node.is_focused:
    flags.append('focused')
  if node.is_enabled:
    flags.append('enabled')
  if node.is_editable:
    flags.append('editable')

  flag_str = f' [{" ".join(flags)}]' if flags else ''
  lines.append(f'{prefix}[{node.class_name}] "{text}" {bounds_str}{flag_str}')

  for child_id in node.child_ids:
    _render_node(nodes_by_id, child_id, indent + 1, lines, visited)


def _format_accessibility_tree(
    state: device_env_service_pb2.DeviceState,
    output_format: str = 'tree',
) -> str:
  """Extracts and formats the accessibility tree from `DeviceState` signals.

  Args:
    state: A `DeviceState` protobuf message containing device signals.
    output_format: Desired string format of the accessibility tree output;
      either `'tree'` for human-readable tree lines or `'json'` for serialized
      JSON. Defaults to `'tree'`.

  Returns:
    Formatted string representation of the accessibility tree.

  Raises:
    ValueError: If `output_format` is not `'tree'` or `'json'`.
    errors.DeviceConnectionError: If no accessibility tree signal is present in
      the device state.
  """
  if output_format not in ('tree', 'json'):
    raise ValueError(
        f"Invalid output_format {output_format!r}. Must be 'tree' or 'json'."
    )

  forest = None
  for signal in state.signals:
    if (
        signal.type == device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
        and signal.HasField('accessibility_forest')
    ):
      forest = signal.accessibility_forest
      break

  if forest is None:
    raise errors.DeviceConnectionError(
        'No accessibility tree signal found in device state.'
    )

  if output_format == 'json':
    return json_format.MessageToJson(forest)

  lines = []
  for window in forest.windows:
    lines.append(f'[Window] "{window.title}" id={window.id}')
    if window.HasField('tree'):
      nodes_by_id = {n.unique_id: n for n in window.tree.nodes}
      root_ids = [n.unique_id for n in window.tree.nodes if n.depth == 0]
      visited: set[int] = set()
      for root_id in root_ids:
        _render_node(
            nodes_by_id, root_id, indent=1, lines=lines, visited=visited
        )
  return '\n'.join(lines)


class AndroidMcpTools:
  """FastMCP tools handler and device state manager via `AndroidDevice`."""

  def __init__(
      self,
      device: android_device_mod.AndroidDevice | None = None,
      task_path: str | None = None,
  ) -> None:
    """Initializes the instance.

    Args:
      device: Optional `AndroidDevice` instance used for querying device state.
      task_path: Optional path to a task textproto file.
    """
    self._device = device
    if self._device is not None:
      self._device.update_subscriptions(set(_DEFAULT_SIGNALS))

    self._task: task_pb2.Task | None = None
    self._task_path: str | None = None
    self._score: float = 0.0
    self._reward: float = 0.0
    self._is_done: bool = False
    self._extras: dict[str, Any] = {}

    if task_path is not None:
      self.load_task(task_path)

  def get_screenshot(self) -> str:
    """Captures and returns a base64-encoded PNG screenshot of the device.

    Returns:
      Base64-encoded PNG image string.

    Raises:
      errors.DeviceConnectionError: If not connected to any device or if no
        decoded screenshot signal is present in the device state.
    """
    if self._device is None:
      raise errors.DeviceConnectionError('Not connected to any device.')

    state = self._device.get_state()
    pixels = _extract_screenshot(state)

    img = Image.fromarray(pixels, mode='RGB')
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    return base64.b64encode(buffer.getvalue()).decode('ascii')

  def get_ui_elements(self, output_format: str = 'tree') -> str:
    """Returns accessibility hierarchy string of the device screen.

    Args:
      output_format: Desired format of the returned hierarchy string; either
        `'tree'` for human-readable tree lines or `'json'` for serialized JSON.
        Defaults to `'tree'`.

    Returns:
      Formatted accessibility hierarchy string.

    Raises:
      errors.DeviceConnectionError: If not connected to any device or if no
        accessibility tree signal is present in the device state.
      ValueError: If `output_format` is invalid.
    """
    if self._device is None:
      raise errors.DeviceConnectionError('Not connected to any device.')

    state = self._device.get_state()
    return _format_accessibility_tree(state, output_format)

  def get_device_info(self) -> str:
    """Returns device settings and metadata.

    Returns:
      JSON string containing device orientation, settings entries, and active
      package metadata.

    Raises:
      errors.DeviceConnectionError: If not connected to any device.
    """
    if self._device is None:
      raise errors.DeviceConnectionError('Not connected to any device.')

    state = self._device.get_state()
    info: dict[str, Any] = {'orientation': state.orientation}

    for signal in state.signals:
      if (
          signal.type == device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS
          and signal.HasField('device_settings')
      ):
        info['settings'] = dict(signal.device_settings.entries)
      elif (
          signal.type == device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
          and signal.HasField('active_package')
      ):
        info['active_package'] = signal.active_package

    return json.dumps(info, indent=2)

  def get_battery_metrics(self) -> str:
    """Returns structured battery and power telemetry metrics from the device.

    Returns:
      JSON string containing battery level, power, voltage, current,
      temperature, status, plugged source, and remaining energy metrics, or an
      error message if telemetry is unavailable.

    Raises:
      errors.DeviceConnectionError: If not connected to any device.
    """
    if self._device is None:
      raise errors.DeviceConnectionError('Not connected to any device.')

    metrics = telemetry.fetch_battery_power_metrics(self._device)
    if metrics is None:
      try:
        state = self._device.get_state()
        for signal in state.signals:
          if (
              signal.type == device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER
              and signal.HasField('battery_power')
          ):
            metrics = telemetry.BatteryPowerMetrics.from_proto(
                signal.battery_power
            )
            break
      except (
          errors.AndroidEnvMcpError,
          RuntimeError,
          AttributeError,
          TypeError,
      ):
        metrics = None

    if metrics is None:
      return json.dumps({'error': 'Battery telemetry unavailable'}, indent=2)

    info = {
        'level_percent': metrics.level_percent,
        'power_mw': metrics.power_mw,
        'voltage_mv': metrics.voltage_mv,
        'current_now_ua': metrics.current_now_ua,
        'temperature_celsius': metrics.temperature_celsius,
        'status': metrics.status,
        'plugged_source': metrics.plugged_source,
        'charge_counter_uah': metrics.charge_counter_uah,
        'thermal_status': metrics.thermal_status,
        'energy_counter_nwh': metrics.energy_counter_nwh,
    }
    return json.dumps(info, indent=2)

  def tap(self, x: float, y: float) -> str:
    """Taps at the given normalized screen coordinates.

    Args:
      x: Horizontal position, normalized `[0.0, 1.0]` (left to right).
      y: Vertical position, normalized `[0.0, 1.0]` (top to bottom).

    Returns:
      Confirmation message.

    Raises:
      errors.DeviceConnectionError: If not connected.
      ValueError: If coordinates are out of bounds `[0.0, 1.0]`.
    """
    if self._device is None:
      raise errors.DeviceConnectionError('Not connected to any device.')

    if not (0.0 <= x <= 1.0 and 0.0 <= y <= 1.0):
      raise ValueError(
          f'Coordinates ({x}, {y}) out of bounds. Must be in range [0.0, 1.0].'
      )

    point = device_env_service_pb2.Point(x=x, y=y)
    self._device.send_action(
        device_env_service_pb2.Action(
            action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN,
            touch_position=point,
        )
    )
    self._device.send_action(
        device_env_service_pb2.Action(
            action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_UP,
            touch_position=point,
        )
    )
    return f'Tapped at ({x}, {y})'

  def swipe(
      self,
      start_x: float,
      start_y: float,
      end_x: float,
      end_y: float,
      steps: int = 10,
  ) -> str:
    """Swipes from start to end coordinates.

    Args:
      start_x: Starting horizontal position, normalized `[0.0, 1.0]` (left to
        right).
      start_y: Starting vertical position, normalized `[0.0, 1.0]` (top to
        bottom).
      end_x: Ending horizontal position, normalized `[0.0, 1.0]` (left to
        right).
      end_y: Ending vertical position, normalized `[0.0, 1.0]` (top to bottom).
      steps: Number of steps to take from start to end.

    Returns:
      Confirmation message.

    Raises:
      errors.DeviceConnectionError: If not connected.
      ValueError: If coordinates are out of bounds `[0.0, 1.0]` or `steps` is
        less than 1.
    """
    if self._device is None:
      raise errors.DeviceConnectionError('Not connected to any device.')

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

    self._device.send_action(
        device_env_service_pb2.Action(
            action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN,
            touch_position=device_env_service_pb2.Point(x=start_x, y=start_y),
        )
    )

    for i in range(1, steps + 1):
      t = i / steps
      x = start_x + (end_x - start_x) * t
      y = start_y + (end_y - start_y) * t
      self._device.send_action(
          device_env_service_pb2.Action(
              action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE,
              touch_position=device_env_service_pb2.Point(x=x, y=y),
          )
      )

    self._device.send_action(
        device_env_service_pb2.Action(
            action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_UP,
            touch_position=device_env_service_pb2.Point(x=end_x, y=end_y),
        )
    )

    return f'Swiped from ({start_x}, {start_y}) to ({end_x}, {end_y})'

  def press_key(self, keycode: int) -> str:
    """Presses the given Android keycode.

    Args:
      keycode: The Android keycode to press.

    Returns:
      Confirmation message.

    Raises:
      errors.DeviceConnectionError: If not connected.
    """
    if self._device is None:
      raise errors.DeviceConnectionError('Not connected to any device.')

    self._device.send_action(
        device_env_service_pb2.Action(
            action_type=device_env_service_pb2.ACTION_TYPE_KEY_EVENT,
            keycode=keycode,
        )
    )
    return f'Pressed key {keycode}'

  def register_tools(
      self, mcp_server: fastmcp.FastMCP, role: str = 'all'
  ) -> None:
    """Registers tool methods on the given FastMCP server based on `role`.

    Args:
      mcp_server: FastMCP server instance where tool handlers will be
        registered.
      role: Role of this MCP server instance determining which tools are
        registered (`'all'`, `'worker'`, or `'manager'`). Defaults to `'all'`.

    Raises:
      ValueError: If `role` is not `'all'`, `'worker'`, or `'manager'`.
    """
    if role not in VALID_ROLES:
      raise ValueError(
          f"Invalid role {role!r}. Must be 'all', 'worker', or 'manager'."
      )

    mcp_server.tool()(self.get_screenshot)
    mcp_server.tool()(self.get_ui_elements)
    mcp_server.tool()(self.get_device_info)

    if role in ('all', 'worker'):
      mcp_server.tool()(self.tap)
      mcp_server.tool()(self.swipe)
      mcp_server.tool()(self.press_key)

    if role in ('all', 'manager'):
      mcp_server.tool()(self.get_battery_metrics)
      mcp_server.tool()(self.load_task)
      mcp_server.tool()(self.reset_task)
      mcp_server.tool()(self.get_task_info)
      mcp_server.tool()(self.get_task_metrics)

  def load_task(self, task_path: str) -> str:
    """Parses task textproto, resolves task APKs, and initializes task state.

    Args:
      task_path: Path to task textproto file.

    Returns:
      Confirmation message.

    Raises:
      FileNotFoundError: If `task_path` does not exist.
      google.protobuf.text_format.ParseError: If `task_path` cannot be parsed.
    """
    with open(task_path, 'r', encoding='utf-8') as f:
      content = f.read()

    task = task_pb2.Task()
    text_format.Parse(content, task)

    try:
      task = fetch_apks_for_task(task)
    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.warning('Failed to fetch APKs for task %s: %s', task.id, e)

    self._task = task
    self._task_path = task_path

    if self._device is not None:
      self._device.update_subscriptions(
          set(_DEFAULT_SIGNALS)
          | {device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS}
      )
      for step in list(task.setup_steps) + list(task.reset_steps):
        if step.HasField('adb_request'):
          adb_req = step.adb_request
          if adb_req.WhichOneof('command') == 'install_apk':
            try:
              self._device.execute_adb_call(adb_req)
            except Exception as e:  # pylint: disable=broad-exception-caught
              logging.warning('Failed to execute ADB install_apk: %s', e)

    self.reset_task()
    return f'Loaded task {task.name} ({task.id}) from {task_path}'

  def reset_task(self) -> str:
    """Resets task state, executes setup/reset ADB steps, and sets orientation.

    Returns:
      Confirmation message.

    Raises:
      ValueError: If no task is loaded.
    """
    if self._task is None:
      raise ValueError('No task loaded.')

    self._score = 0.0
    self._reward = 0.0
    self._is_done = False
    self._extras = {}

    if self._device is not None:
      orientation_req = adb_pb2.AdbRequest(
          settings=adb_pb2.AdbRequest.SettingsRequest(
              name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
              put=adb_pb2.AdbRequest.SettingsRequest.Put(
                  key='user_rotation',
                  value='0',
              ),
          )
      )
      try:
        self._device.execute_adb_call(orientation_req)
      except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning('Failed to set portrait orientation via ADB: %s', e)

      adb_parser = getattr(self._device, '_adb_call_parser', None)
      if adb_parser is not None:
        interpreter = setup_step_interpreter.SetupStepInterpreter(adb_parser)
        if self._task.setup_steps:
          try:
            interpreter.interpret(self._task.setup_steps)
          except Exception as e:  # pylint: disable=broad-exception-caught
            logging.warning('Failed to execute task setup steps: %s', e)
        if self._task.reset_steps:
          try:
            interpreter.interpret(self._task.reset_steps)
          except Exception as e:  # pylint: disable=broad-exception-caught
            logging.warning('Failed to execute task reset steps: %s', e)
      else:
        for step in list(self._task.setup_steps) + list(self._task.reset_steps):
          if step.HasField('adb_request'):
            adb_req = step.adb_request
            if adb_req.WhichOneof('command') != 'install_apk':
              try:
                self._device.execute_adb_call(adb_req)
              except Exception as e:  # pylint: disable=broad-exception-caught
                logging.warning(
                    'Failed to execute ADB setup/reset request: %s', e
                )

    return 'Task state reset.'

  def get_task_info(self) -> str:
    """Returns task metadata as a JSON string.

    Returns:
      JSON string containing task ID, name, description, and episode limits.

    Raises:
      ValueError: If no task is loaded.
    """
    if self._task is None:
      raise ValueError('No task loaded.')

    info: dict[str, Any] = {
        'id': self._task.id,
        'name': self._task.name,
        'description': self._task.description,
        'max_episode_sec': self._task.max_episode_sec,
        'max_episode_steps': self._task.max_episode_steps,
    }
    return json.dumps(info, indent=2)

  def _update_metrics_from_logs(self, log_lines: Sequence[str]) -> None:
    """Updates task metrics by parsing log lines against `log_parsing_config`."""
    if self._task is None or not self._task.HasField('log_parsing_config'):
      return

    regexps = self._task.log_parsing_config.log_regexps
    for raw_line in log_lines:
      line = _LOGCAT_PREFIX_RE.sub('', raw_line)
      if regexps.score:
        match = re.search(regexps.score, line)
        if match:
          current_score = float(match.group(1))
          self._reward += current_score - self._score
          self._score = current_score

      for pattern in regexps.reward:
        if pattern:
          match = re.search(pattern, line)
          if match:
            self._reward += float(match.group(1))

      for reward_event in regexps.reward_event:
        if reward_event.event and re.search(reward_event.event, line):
          self._reward += float(reward_event.reward)

      for pattern in regexps.episode_end:
        if pattern and re.search(pattern, line):
          self._is_done = True

      for pattern in regexps.extra:
        if pattern:
          match = re.search(pattern, line)
          if match:
            extra_name = match.group('name')
            extra_raw = match.group('extra')
            if extra_raw:
              try:
                self._extras[extra_name] = ast.literal_eval(extra_raw)
              except (ValueError, TypeError, SyntaxError):
                self._extras[extra_name] = extra_raw
            else:
              self._extras[extra_name] = 1

      for pattern in regexps.json_extra:
        if pattern:
          match = re.search(pattern, line)
          if match:
            try:
              parsed_extra = json.loads(match.group('json_extra'))
              if isinstance(parsed_extra, dict):
                self._extras.update(parsed_extra)
            except ValueError:
              pass

  def get_task_metrics(self) -> str:
    """Returns task metrics (`score`, `reward`, `is_done`, `extras`) as JSON.

    Returns:
      JSON string containing `score`, `reward`, `is_done`, and `extras`.

    Raises:
      ValueError: If no task is loaded.
    """
    if self._task is None:
      raise ValueError('No task loaded.')

    if self._device is not None:
      try:
        state = self._device.get_state()
        for signal in state.signals:
          if (
              signal.type == device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS
              and signal.HasField('system_logs')
          ):
            self._update_metrics_from_logs(signal.system_logs.values)
      except (
          errors.AndroidEnvMcpError,
          RuntimeError,
          AttributeError,
          TypeError,
      ):
        pass

    metrics: dict[str, Any] = {
        'score': self._score,
        'reward': self._reward,
        'is_done': self._is_done,
        'extras': self._extras,
    }
    return json.dumps(metrics, indent=2)
