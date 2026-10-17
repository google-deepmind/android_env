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

Exposes Android device inspection and interaction capabilities to LLM agents
by receiving a connected AndroidDevice instance, bypassing the RL interface
(dm_env).
"""

import base64
from collections.abc import Mapping
import io
import json
from typing import Any

from android_env.components import android_device as android_device_mod
from android_env.mcp import errors
from android_env.proto import device_env_service_pb2
from android_env.proto.a11y import android_accessibility_node_info_pb2
from google.protobuf import json_format
from mcp.server import fastmcp
import numpy as np
from PIL import Image

_DEFAULT_SIGNALS = frozenset({
    device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
    device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
    device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE,
    device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS,
})


def _extract_screenshot(
    state: device_env_service_pb2.DeviceState,
) -> np.ndarray:
  """Extracts decoded RGB screenshot pixels from DeviceState signals.

  Args:
    state: A `DeviceState` protobuf containing device signals.

  Returns:
    A NumPy array of shape `(height, width, 3)` with uint8 dtype containing
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
  """Extracts and formats the accessibility tree from DeviceState signals.

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
      visited = set()
      for root_id in root_ids:
        _render_node(
            nodes_by_id, root_id, indent=1, lines=lines, visited=visited
        )
  return '\n'.join(lines)


class AndroidMcpTools:
  """FastMCP tools foundation class and device state manager via AndroidDevice."""

  def __init__(
      self, device: android_device_mod.AndroidDevice | None = None
  ) -> None:
    """Initializes AndroidMcpTools with an optional AndroidDevice.

    Args:
      device: Optional `AndroidDevice` instance used for querying device state.
    """
    self._device = device
    if self._device is not None:
      self._device.update_subscriptions(set(_DEFAULT_SIGNALS))

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

  def tap(self, x: float, y: float) -> str:
    """Taps at the given normalized screen coordinates.

    Args:
      x: Horizontal position, normalized [0.0, 1.0] (left to right).
      y: Vertical position, normalized [0.0, 1.0] (top to bottom).

    Returns:
      Confirmation message.

    Raises:
      errors.DeviceConnectionError: If not connected.
      ValueError: If coordinates are out of bounds [0.0, 1.0].
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
      start_x: Starting horizontal position, normalized [0.0, 1.0] (left to
        right).
      start_y: Starting vertical position, normalized [0.0, 1.0] (top to
        bottom).
      end_x: Ending horizontal position, normalized [0.0, 1.0] (left to right).
      end_y: Ending vertical position, normalized [0.0, 1.0] (top to bottom).
      steps: Number of steps to take from start to end.

    Returns:
      Confirmation message.

    Raises:
      errors.DeviceConnectionError: If not connected.
      ValueError: If coordinates are out of bounds [0.0, 1.0] or steps is less
        than 1.
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

  def register_tools(self, mcp_server: fastmcp.FastMCP) -> None:
    """Registers all tool methods on the given FastMCP server.

    Args:
      mcp_server: FastMCP server instance where tool handlers will be
        registered.
    """
    mcp_server.tool()(self.get_screenshot)
    mcp_server.tool()(self.get_ui_elements)
    mcp_server.tool()(self.get_device_info)
    mcp_server.tool()(self.tap)
    mcp_server.tool()(self.swipe)
    mcp_server.tool()(self.press_key)
