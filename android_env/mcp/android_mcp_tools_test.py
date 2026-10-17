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

"""Unit tests for FastMCP Android device interaction tools in android_mcp_tools."""

import base64
import io
import json
from unittest import mock

from absl.testing import absltest
from android_env.components import android_device as android_device_mod
from android_env.mcp import android_mcp_tools
from android_env.mcp import errors
from android_env.proto import device_env_service_pb2
from android_env.proto.a11y import android_accessibility_forest_pb2
from android_env.proto.a11y import android_accessibility_node_info_pb2
from google.protobuf import json_format
from mcp.server import fastmcp
import numpy as np
from PIL import Image


class AndroidMcpToolsTest(absltest.TestCase):

  def test_init_updates_subscriptions(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    self.assertIs(tools._device, mock_device)
    mock_device.update_subscriptions.assert_called_once_with(
        set(android_mcp_tools._DEFAULT_SIGNALS)
    )

  def test_init_with_none_device(self):
    tools = android_mcp_tools.AndroidMcpTools(device=None)
    self.assertIsNone(tools._device)


class GetScreenshotTest(absltest.TestCase):

  def test_get_screenshot_not_connected(self):
    tools = android_mcp_tools.AndroidMcpTools()
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_screenshot()

  def test_get_screenshot_missing_signal(self):
    tools = android_mcp_tools.AndroidMcpTools()
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools._device = mock_device
    mock_device.get_state.return_value = device_env_service_pb2.DeviceState()
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_screenshot()

  def test_get_screenshot_signal_without_decoded(self):
    tools = android_mcp_tools.AndroidMcpTools()
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools._device = mock_device
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    mock_device.get_state.return_value = state
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_screenshot()

  def test_get_screenshot_incomplete_signal(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    state = device_env_service_pb2.DeviceState()
    sig1 = state.signals.add()
    sig1.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
    sig2 = state.signals.add()
    sig2.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig3 = state.signals.add()
    sig3.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig3.screenshot.encoded_bytes = b'123'
    mock_device.get_state.return_value = state
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_screenshot()

  def test_get_screenshot_success(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    height, width = 100, 100
    raw_pixels = np.zeros((height, width, 3), dtype=np.uint8).tobytes()

    state = device_env_service_pb2.DeviceState()
    sig_other = state.signals.add()
    sig_other.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE

    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    sig.screenshot.decoded.height = height
    sig.screenshot.decoded.width = width
    sig.screenshot.decoded.raw_pixels = raw_pixels

    mock_device.get_state.return_value = state

    result = tools.get_screenshot()
    decoded_data = base64.b64decode(result.encode('ascii'))
    img = Image.open(io.BytesIO(decoded_data))
    self.assertEqual(img.size, (width, height))
    # Check exact pixels (since PNG is lossless)
    expected_pixels = np.frombuffer(raw_pixels, dtype=np.uint8).reshape(
        (height, width, 3)
    )
    np.testing.assert_array_equal(np.array(img), expected_pixels)


class GetUiElementsTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = self._forest.windows.add()
    window.id = 1
    window.title = 'MainActivity'

    node = window.tree.nodes.add()
    node.unique_id = 0
    node.class_name = 'android.widget.TextView'
    node.text = 'Hello World'
    node.depth = 0
    node.bounds_in_screen.left = 0
    node.bounds_in_screen.top = 0
    node.bounds_in_screen.right = 100
    node.bounds_in_screen.bottom = 50
    node.is_clickable = True

  def test_get_ui_elements_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_ui_elements()

  def test_get_ui_elements_missing_signal(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
    mock_device.get_state.return_value = state
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_ui_elements()

  def test_get_ui_elements_invalid_format(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    with self.assertRaises(ValueError):
      tools.get_ui_elements(output_format='invalid')

  def test_get_ui_elements_tree_format(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(self._forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertIn('[Window] "MainActivity" id=1', result)
    self.assertIn(
        '  [android.widget.TextView] "Hello World" {0,0,100,50} [clickable]',
        result,
    )

  def test_get_ui_elements_json_format(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(self._forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='json')
    expected_json = json_format.MessageToJson(self._forest)
    self.assertEqual(json.loads(result), json.loads(expected_json))

  def test_get_ui_elements_with_cycle(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = forest.windows.add()
    window.id = 1
    window.title = 'MainActivity'

    node = window.tree.nodes.add()
    node.unique_id = 0
    node.class_name = 'android.widget.TextView'
    node.text = 'Cyclic Node'
    node.depth = 0
    node.bounds_in_screen.left = 0
    node.bounds_in_screen.top = 0
    node.bounds_in_screen.right = 100
    node.bounds_in_screen.bottom = 50
    node.child_ids.append(0)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertIn('[Window] "MainActivity" id=1', result)
    self.assertIn(
        '  [android.widget.TextView] "Cyclic Node" {0,0,100,50}', result
    )

  def test_get_ui_elements_content_description_fallback(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = forest.windows.add()
    window.id = 1
    window.title = 'MainActivity'

    node = window.tree.nodes.add()
    node.unique_id = 0
    node.class_name = 'android.widget.ImageView'
    node.text = ''
    node.content_description = 'Content Description Text'
    node.depth = 0
    node.bounds_in_screen.left = 0
    node.bounds_in_screen.top = 0
    node.bounds_in_screen.right = 100
    node.bounds_in_screen.bottom = 50

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertIn(
        '  [android.widget.ImageView] "Content Description Text" {0,0,100,50}',
        result,
    )

  def test_get_ui_elements_no_text_or_content_description(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = forest.windows.add()
    window.id = 1
    window.title = 'MainActivity'

    node = window.tree.nodes.add()
    node.unique_id = 0
    node.class_name = 'android.view.View'
    node.text = ''
    node.content_description = ''
    node.depth = 0
    node.bounds_in_screen.left = 0
    node.bounds_in_screen.top = 0
    node.bounds_in_screen.right = 100
    node.bounds_in_screen.bottom = 50

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertIn('  [android.view.View] "" {0,0,100,50}', result)

  def test_get_ui_elements_with_all_flags(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = forest.windows.add()
    window.id = 1
    window.title = 'MainActivity'

    node = window.tree.nodes.add()
    node.unique_id = 0
    node.class_name = 'android.widget.EditText'
    node.text = 'Editable Text'
    node.depth = 0
    node.bounds_in_screen.left = 0
    node.bounds_in_screen.top = 0
    node.bounds_in_screen.right = 100
    node.bounds_in_screen.bottom = 50
    node.is_clickable = True
    node.is_scrollable = True
    node.is_checked = True
    node.is_focused = True
    node.is_enabled = True
    node.is_editable = True

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertIn(
        '  [android.widget.EditText] "Editable Text" {0,0,100,50}'
        ' [clickable scrollable checked focused enabled editable]',
        result,
    )

  def test_get_ui_elements_missing_child_node(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = forest.windows.add()
    window.id = 1
    window.title = 'MainActivity'

    node = window.tree.nodes.add()
    node.unique_id = 0
    node.class_name = 'android.widget.LinearLayout'
    node.text = 'Parent Node'
    node.depth = 0
    node.bounds_in_screen.left = 0
    node.bounds_in_screen.top = 0
    node.bounds_in_screen.right = 100
    node.bounds_in_screen.bottom = 50
    node.child_ids.append(999)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertIn('[Window] "MainActivity" id=1', result)
    self.assertIn(
        '  [android.widget.LinearLayout] "Parent Node" {0,0,100,50}', result
    )

  def test_get_ui_elements_cycle_detection(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = forest.windows.add()
    window.id = 1
    window.title = 'MainActivity'

    parent = window.tree.nodes.add()
    parent.unique_id = 0
    parent.class_name = 'android.widget.LinearLayout'
    parent.text = 'Parent Node'
    parent.depth = 0
    parent.bounds_in_screen.left = 0
    parent.bounds_in_screen.top = 0
    parent.bounds_in_screen.right = 100
    parent.bounds_in_screen.bottom = 100
    parent.child_ids.append(1)

    child = window.tree.nodes.add()
    child.unique_id = 1
    child.class_name = 'android.widget.TextView'
    child.text = 'Child Node'
    child.depth = 1
    child.bounds_in_screen.left = 0
    child.bounds_in_screen.top = 0
    child.bounds_in_screen.right = 100
    child.bounds_in_screen.bottom = 50
    child.child_ids.append(0)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertIn('[Window] "MainActivity" id=1', result)
    self.assertIn(
        '  [android.widget.LinearLayout] "Parent Node" {0,0,100,100}', result
    )
    self.assertIn(
        '    [android.widget.TextView] "Child Node" {0,0,100,50}', result
    )

  def test_get_ui_elements_window_without_tree(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    window = forest.windows.add()
    window.id = 2
    window.title = 'EmptyWindow'

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='tree')
    self.assertEqual(result, '[Window] "EmptyWindow" id=2')

  def test_render_node_visited_default(self):
    node = android_accessibility_node_info_pb2.AndroidAccessibilityNodeInfo()
    node.unique_id = 1
    node.class_name = 'android.view.View'
    node.text = 'Direct Render'
    node.depth = 0
    node.bounds_in_screen.left = 0
    node.bounds_in_screen.top = 0
    node.bounds_in_screen.right = 10
    node.bounds_in_screen.bottom = 10

    nodes_by_id = {1: node}
    lines = []
    android_mcp_tools._render_node(nodes_by_id, 1, indent=0, lines=lines)
    self.assertEqual(lines, ['[android.view.View] "Direct Render" {0,0,10,10}'])


class GetDeviceInfoTest(absltest.TestCase):

  def test_get_device_info_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_device_info()

  def test_get_device_info_success(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    state = device_env_service_pb2.DeviceState()
    state.orientation = 1

    sig_pkg = state.signals.add()
    sig_pkg.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE
    sig_pkg.active_package = 'com.example.app'

    sig_settings = state.signals.add()
    sig_settings.type = device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS
    sig_settings.device_settings.entries['system_theme'] = 'dark'

    mock_device.get_state.return_value = state

    result = tools.get_device_info()
    data = json.loads(result)
    self.assertEqual(data['orientation'], 1)
    self.assertEqual(data['active_package'], 'com.example.app')
    self.assertEqual(data['settings']['system_theme'], 'dark')

  def test_get_device_info_signals_without_payloads(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    state = device_env_service_pb2.DeviceState()
    state.orientation = 0

    sig_settings = state.signals.add()
    sig_settings.type = device_env_service_pb2.DEVICE_SIGNAL_DEVICE_SETTINGS

    sig_pkg = state.signals.add()
    sig_pkg.type = device_env_service_pb2.DEVICE_SIGNAL_ACTIVE_PACKAGE

    sig_other = state.signals.add()
    sig_other.type = device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT

    mock_device.get_state.return_value = state

    result = tools.get_device_info()
    data = json.loads(result)
    self.assertEqual(data, {'orientation': 0})


class TapTest(absltest.TestCase):

  def test_tap_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.tap(0.5, 0.5)

  def test_tap_out_of_bounds(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    with self.assertRaises(ValueError):
      tools.tap(-0.1, 0.5)
    with self.assertRaises(ValueError):
      tools.tap(0.5, 1.1)

  def test_tap_success(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    result = tools.tap(0.25, 0.75)
    self.assertEqual(result, 'Tapped at (0.25, 0.75)')

    self.assertEqual(mock_device.send_action.call_count, 2)
    down_action = mock_device.send_action.call_args_list[0][0][0]
    up_action = mock_device.send_action.call_args_list[1][0][0]

    self.assertEqual(
        down_action.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
    )
    self.assertEqual(down_action.touch_position.x, 0.25)
    self.assertEqual(down_action.touch_position.y, 0.75)

    self.assertEqual(
        up_action.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_UP
    )
    self.assertEqual(up_action.touch_position.x, 0.25)
    self.assertEqual(up_action.touch_position.y, 0.75)


class SwipeTest(absltest.TestCase):

  def test_swipe_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.swipe(0.1, 0.1, 0.9, 0.9)

  def test_swipe_invalid_steps(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    with self.assertRaises(ValueError):
      tools.swipe(0.1, 0.1, 0.9, 0.9, steps=0)

  def test_swipe_out_of_bounds(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    with self.assertRaises(ValueError):
      tools.swipe(-0.1, 0.1, 0.9, 0.9)

  def test_swipe_success(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    result = tools.swipe(0.0, 0.0, 1.0, 1.0, steps=2)
    self.assertEqual(result, 'Swiped from (0.0, 0.0) to (1.0, 1.0)')
    self.assertEqual(mock_device.send_action.call_count, 4)


class PressKeyTest(absltest.TestCase):

  def test_press_key_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.press_key(3)

  def test_press_key_success(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    result = tools.press_key(3)
    self.assertEqual(result, 'Pressed key 3')
    mock_device.send_action.assert_called_once()
    action = mock_device.send_action.call_args[0][0]
    self.assertEqual(
        action.action_type, device_env_service_pb2.ACTION_TYPE_KEY_EVENT
    )
    self.assertEqual(action.keycode, 3)


class RegisterToolsTest(absltest.TestCase):

  def test_register_tools_count(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    server = mock.MagicMock(spec=fastmcp.FastMCP)
    tools.register_tools(server)
    self.assertEqual(server.tool.call_count, 6)


if __name__ == '__main__':
  absltest.main()
