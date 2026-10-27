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
from absl.testing import parameterized
from android_env.components import android_device as android_device_mod
from android_env.components import setup_step_interpreter
from android_env.components import telemetry

from android_env.mcp import android_mcp_tools
from android_env.mcp import errors
from android_env.proto import device_env_service_pb2
from android_env.proto import task_pb2
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
    expected_pixels = np.frombuffer(raw_pixels, dtype=np.uint8).reshape(
        (height, width, 3)
    )
    np.testing.assert_array_equal(np.array(img), expected_pixels)


def _create_sample_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  window = forest.windows.add()
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
  return forest


class GetUiElementsTest(absltest.TestCase):

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
    forest = _create_sample_forest()

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
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
    forest = _create_sample_forest()

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE
    sig.accessibility_forest.CopyFrom(forest)
    mock_device.get_state.return_value = state

    result = tools.get_ui_elements(output_format='json')
    expected_json = json_format.MessageToJson(forest)
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


class GetBatteryMetricsTest(absltest.TestCase):

  def test_get_battery_metrics_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.get_battery_metrics()

  @mock.patch.object(telemetry, 'fetch_battery_power_metrics', autospec=True)
  def test_get_battery_metrics_fallback_none(self, mock_fetch):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_device.get_state.return_value = device_env_service_pb2.DeviceState()
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    mock_fetch.return_value = None

    result_json = tools.get_battery_metrics()
    mock_fetch.assert_called_once_with(mock_device)
    expected = {'error': 'Battery telemetry unavailable'}
    self.assertEqual(json.loads(result_json), expected)
    self.assertEqual(result_json, json.dumps(expected, indent=2))

  @mock.patch.object(telemetry, 'fetch_battery_power_metrics', autospec=True)
  def test_get_battery_metrics_from_device_state_signal(self, mock_fetch):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER
    sig.battery_power.level_percent = 92
    sig.battery_power.power_mw = 1250.0
    sig.battery_power.voltage_mv = 4150
    sig.battery_power.current_now_ua = -301204
    sig.battery_power.temperature_celsius = 29.0
    sig.battery_power.status = 'DISCHARGING'
    sig.battery_power.plugged_source = 'UNPLUGGED'
    sig.battery_power.charge_counter_uah = 3800000
    sig.battery_power.thermal_status = 0
    sig.battery_power.energy_counter_nwh = 14000000
    mock_device.get_state.return_value = state
    mock_fetch.return_value = None

    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    result_json = tools.get_battery_metrics()

    data = json.loads(result_json)
    self.assertEqual(data['level_percent'], 92)
    self.assertEqual(data['power_mw'], 1250.0)
    self.assertEqual(data['status'], 'DISCHARGING')

  @mock.patch.object(telemetry, 'fetch_battery_power_metrics', autospec=True)
  def test_get_battery_metrics_success_with_mock(self, mock_fetch):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    mock_metrics = mock.create_autospec(
        telemetry.BatteryPowerMetrics, instance=True
    )
    mock_metrics.level_percent = 85
    mock_metrics.power_mw = 1890.5
    mock_metrics.voltage_mv = 4200
    mock_metrics.current_now_ua = -450000
    mock_metrics.temperature_celsius = 28.5
    mock_metrics.status = 'CHARGING'
    mock_metrics.plugged_source = 'USB'
    mock_metrics.charge_counter_uah = 3100000
    mock_metrics.thermal_status = 0
    mock_metrics.energy_counter_nwh = 11500000
    mock_fetch.return_value = mock_metrics

    result_json = tools.get_battery_metrics()
    mock_fetch.assert_called_once_with(mock_device)
    expected = {
        'level_percent': 85,
        'power_mw': 1890.5,
        'voltage_mv': 4200,
        'current_now_ua': -450000,
        'temperature_celsius': 28.5,
        'status': 'CHARGING',
        'plugged_source': 'USB',
        'charge_counter_uah': 3100000,
        'thermal_status': 0,
        'energy_counter_nwh': 11500000,
    }
    self.assertEqual(json.loads(result_json), expected)
    self.assertEqual(result_json, json.dumps(expected, indent=2))

  @mock.patch.object(telemetry, 'fetch_battery_power_metrics', autospec=True)
  def test_get_battery_metrics_success_with_dataclass(self, mock_fetch):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    mock_metrics = telemetry.BatteryPowerMetrics(
        level_percent=100,
        current_now_ua=5000,
        voltage_mv=4100,
        power_mw=20.5,
        temperature_celsius=25.0,
        status='FULL',
        plugged_source='AC',
        charge_counter_uah=4000000,
        thermal_status=1,
        energy_counter_nwh=15000000,
    )
    mock_fetch.return_value = mock_metrics

    result_json = tools.get_battery_metrics()
    mock_fetch.assert_called_once_with(mock_device)
    expected = {
        'level_percent': 100,
        'power_mw': 20.5,
        'voltage_mv': 4100,
        'current_now_ua': 5000,
        'temperature_celsius': 25.0,
        'status': 'FULL',
        'plugged_source': 'AC',
        'charge_counter_uah': 4000000,
        'thermal_status': 1,
        'energy_counter_nwh': 15000000,
    }
    self.assertEqual(json.loads(result_json), expected)
    self.assertEqual(result_json, json.dumps(expected, indent=2))


class TapTest(parameterized.TestCase):

  def test_tap_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.tap(0.5, 0.5)

  @parameterized.named_parameters(
      ('x_below_zero', -0.01, 0.5),
      ('x_above_one', 1.01, 0.5),
      ('y_below_zero', 0.5, -0.01),
      ('y_above_one', 0.5, 1.01),
  )
  def test_tap_out_of_bounds(self, x: float, y: float):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    with self.assertRaises(ValueError):
      tools.tap(x, y)

  @parameterized.named_parameters(
      ('interior_point', 0.25, 0.75),
      ('origin_boundary', 0.0, 0.0),
      ('max_boundary', 1.0, 1.0),
  )
  def test_tap_success(self, x: float, y: float):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    result = tools.tap(x, y)
    self.assertEqual(result, f'Tapped at ({x}, {y})')

    self.assertEqual(mock_device.send_action.call_count, 2)
    down_action = mock_device.send_action.call_args_list[0][0][0]
    up_action = mock_device.send_action.call_args_list[1][0][0]

    self.assertEqual(
        down_action.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
    )
    self.assertEqual(down_action.touch_position.x, x)
    self.assertEqual(down_action.touch_position.y, y)

    self.assertEqual(
        up_action.action_type, device_env_service_pb2.ACTION_TYPE_TOUCH_UP
    )
    self.assertEqual(up_action.touch_position.x, x)
    self.assertEqual(up_action.touch_position.y, y)


class SwipeTest(parameterized.TestCase):

  def test_swipe_not_connected(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    tools._device = None
    with self.assertRaises(errors.DeviceConnectionError):
      tools.swipe(0.1, 0.1, 0.9, 0.9)

  @parameterized.named_parameters(
      ('zero_steps', 0),
      ('negative_steps', -1),
  )
  def test_swipe_invalid_steps(self, steps: int):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    with self.assertRaises(ValueError):
      tools.swipe(0.1, 0.1, 0.9, 0.9, steps=steps)

  @parameterized.named_parameters(
      ('start_x_below', -0.1, 0.1, 0.9, 0.9),
      ('start_x_above', 1.1, 0.1, 0.9, 0.9),
      ('start_y_below', 0.1, -0.1, 0.9, 0.9),
      ('start_y_above', 0.1, 1.1, 0.9, 0.9),
      ('end_x_below', 0.1, 0.1, -0.1, 0.9),
      ('end_x_above', 0.1, 0.1, 1.1, 0.9),
      ('end_y_below', 0.1, 0.1, 0.9, -0.1),
      ('end_y_above', 0.1, 0.1, 0.9, 1.1),
  )
  def test_swipe_out_of_bounds(
      self, start_x: float, start_y: float, end_x: float, end_y: float
  ):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    with self.assertRaises(ValueError):
      tools.swipe(start_x, start_y, end_x, end_y)

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


class LoadTaskTest(absltest.TestCase):

  def test_load_task_success(self):
    tools = android_mcp_tools.AndroidMcpTools()
    task_textproto = (
        'id: "catch_ball"\n'
        'name: "Catch The Ball"\n'
        'description: "Tap the ball when it appears."\n'
    )
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'task.textproto', content=task_textproto
    ).full_path

    result = tools.load_task(task_path)
    self.assertIn('Loaded task Catch The Ball (catch_ball)', result)
    self.assertIsNotNone(tools._task)
    self.assertEqual(tools._task.id, 'catch_ball')
    self.assertEqual(tools._task.name, 'Catch The Ball')
    self.assertEqual(tools._task_path, task_path)

  def test_init_with_task_path(self):
    task_textproto = 'id: "init_task"\nname: "Init Task"\n'
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'init_task.textproto', content=task_textproto
    ).full_path

    tools = android_mcp_tools.AndroidMcpTools(task_path=task_path)
    self.assertIsNotNone(tools._task)
    self.assertEqual(tools._task.id, 'init_task')

  def test_load_task_file_not_found(self):
    tools = android_mcp_tools.AndroidMcpTools()
    with self.assertRaises(FileNotFoundError):
      tools.load_task('/non/existent/path/task.textproto')

  @mock.patch.object(android_mcp_tools, 'fetch_apks_for_task', autospec=True)
  def test_load_task_apk_resolution_and_install(self, mock_fetch):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    task_proto = task_pb2.Task(id='catch_ball', name='Catch The Ball')
    step = task_proto.setup_steps.add()
    step.adb_request.install_apk.filesystem.path = '/tmp/catch_ball-debug.apk'
    mock_fetch.return_value = task_proto

    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'task.textproto', content='id: "catch_ball"\nname: "Catch The Ball"\n'
    ).full_path

    result = tools.load_task(task_path)
    self.assertIn('Loaded task Catch The Ball', result)
    mock_fetch.assert_called_once()
    mock_device.execute_adb_call.assert_called()

  @mock.patch.object(android_mcp_tools, 'fetch_apks_for_task', autospec=True)
  def test_load_task_apk_fetch_error_fallback(self, mock_fetch):
    mock_fetch.side_effect = RuntimeError('Fetch error')
    tools = android_mcp_tools.AndroidMcpTools()

    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'task.textproto', content='id: "fallback_task"\nname: "Fallback Task"\n'
    ).full_path

    result = tools.load_task(task_path)
    self.assertIn('Loaded task Fallback Task', result)


class ResetTaskTest(absltest.TestCase):

  def test_reset_task_no_task_loaded(self):
    tools = android_mcp_tools.AndroidMcpTools()
    with self.assertRaises(ValueError):
      tools.reset_task()

  def test_reset_task_success(self):
    tools = android_mcp_tools.AndroidMcpTools()
    task_textproto = 'id: "test_task"\nname: "Test Task"\n'
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'test_task.textproto', content=task_textproto
    ).full_path
    tools.load_task(task_path)

    tools._score = 10.0
    tools._reward = 5.0
    tools._is_done = True
    tools._extras = {'key': 'value'}

    result = tools.reset_task()
    self.assertEqual(result, 'Task state reset.')
    self.assertEqual(tools._score, 0.0)
    self.assertEqual(tools._reward, 0.0)
    self.assertFalse(tools._is_done)
    self.assertEqual(tools._extras, {})

  def test_reset_task_executes_orientation_and_setup_steps(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_device._adb_call_parser = None
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    task_textproto = (
        'id: "reset_demo"\n'
        'name: "Reset Demo"\n'
        'reset_steps: [\n'
        '  {\n'
        '    adb_request: {\n'
        '      start_activity: {\n'
        '        full_activity: "com.example.app/.MainActivity"\n'
        '        extra_args: ["--ez", "RL_TASK_ENABLED", "true", "--es",'
        ' "RL_TASK_GAME_CONFIG", "{}" ]\n'
        '      }\n'
        '    }\n'
        '  }\n'
        ']\n'
    )
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'task.textproto', content=task_textproto
    ).full_path
    tools.load_task(task_path)

    mock_device.execute_adb_call.reset_mock()
    result = tools.reset_task()
    self.assertEqual(result, 'Task state reset.')
    self.assertGreaterEqual(mock_device.execute_adb_call.call_count, 1)

  @mock.patch.object(
      setup_step_interpreter, 'SetupStepInterpreter', autospec=True
  )
  def test_reset_task_with_setup_step_interpreter(self, mock_interpreter_cls):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_parser = mock.MagicMock()
    mock_device._adb_call_parser = mock_parser
    mock_interpreter_inst = mock.MagicMock()
    mock_interpreter_cls.return_value = mock_interpreter_inst

    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    task_textproto = (
        'id: "interp_task"\n'
        'name: "Interp Task"\n'
        'setup_steps: [{ sleep: { time_sec: 1.0 } }]\n'
        'reset_steps: [{ sleep: { time_sec: 0.5 } }]\n'
    )
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'task.textproto', content=task_textproto
    ).full_path

    tools.load_task(task_path)
    mock_interpreter_cls.assert_called_with(mock_parser)
    self.assertEqual(mock_interpreter_inst.interpret.call_count, 2)

  def test_reset_task_adb_error_fallback(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_device._adb_call_parser = None
    mock_device.execute_adb_call.side_effect = RuntimeError(
        'ADB connection dropped'
    )

    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    task_textproto = 'id: "err_task"\nname: "Err Task"\n'
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'task.textproto', content=task_textproto
    ).full_path

    result = tools.load_task(task_path)
    self.assertIn('Loaded task Err Task', result)


class GetTaskInfoTest(absltest.TestCase):

  def test_get_task_info_no_task_loaded(self):
    tools = android_mcp_tools.AndroidMcpTools()
    with self.assertRaises(ValueError):
      tools.get_task_info()

  def test_get_task_info_success(self):
    tools = android_mcp_tools.AndroidMcpTools()
    task_textproto = (
        'id: "test_task"\n'
        'name: "Test Task"\n'
        'description: "Test task description."\n'
        'max_episode_sec: 120.0\n'
        'max_episode_steps: 50\n'
    )
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'test_task.textproto', content=task_textproto
    ).full_path
    tools.load_task(task_path)

    result_json = tools.get_task_info()
    data = json.loads(result_json)
    self.assertEqual(data['id'], 'test_task')
    self.assertEqual(data['name'], 'Test Task')
    self.assertEqual(data['description'], 'Test task description.')
    self.assertEqual(data['max_episode_sec'], 120.0)
    self.assertEqual(data['max_episode_steps'], 50)


class GetTaskMetricsTest(absltest.TestCase):

  def test_get_task_metrics_no_task_loaded(self):
    tools = android_mcp_tools.AndroidMcpTools()
    with self.assertRaises(ValueError):
      tools.get_task_metrics()

  def test_get_task_metrics_success(self):
    tools = android_mcp_tools.AndroidMcpTools()
    task_textproto = 'id: "test_task"\nname: "Test Task"\n'
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'test_task.textproto', content=task_textproto
    ).full_path
    tools.load_task(task_path)

    result_json = tools.get_task_metrics()
    data = json.loads(result_json)
    self.assertEqual(data['score'], 0.0)
    self.assertEqual(data['reward'], 0.0)
    self.assertFalse(data['is_done'])
    self.assertEqual(data['extras'], {})

  def test_get_task_metrics_parses_system_logs(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_device.get_state.return_value = device_env_service_pb2.DeviceState()
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    task_textproto = (
        'id: "log_task"\n'
        'name: "Log Task"\n'
        'log_parsing_config: {\n'
        '  log_regexps: {\n'
        '    score: "^score: ([-+]?[0-9]*\\\\.?[0-9]+)$"\n'
        '    reward: ["^reward: ([-+]?[0-9]*\\\\.?[0-9]+)$"]\n'
        '    reward_event: [{ event: "^BONUS_HIT$" reward: 2.5 }]\n'
        '    episode_end: ["^EPISODE_END$"]\n'
        '    extra: ["^extra: (?P<name>[^ ]+)[ ]*(?P<extra>.*)$"]\n'
        '    json_extra: ["^json_extra: (?P<json_extra>.*)$"]\n'
        '  }\n'
        '}\n'
    )
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'log_task.textproto', content=task_textproto
    ).full_path
    tools.load_task(task_path)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS
    sig.system_logs.values.extend([
        'I/AndroidRLTask: score: 3.0',
        'I/AndroidRLTask: reward: 1.5',
        'I/AndroidRLTask: BONUS_HIT',
        'I/AndroidRLTask: extra: level 4',
        'I/AndroidRLTask: extra: flag',
        'I/AndroidRLTask: json_extra: {"coins": 10}',
        'I/AndroidRLTask: EPISODE_END',
    ])
    mock_device.get_state.return_value = state

    result_json = tools.get_task_metrics()
    data = json.loads(result_json)
    self.assertEqual(data['score'], 3.0)
    self.assertEqual(data['reward'], 7.0)
    self.assertTrue(data['is_done'])
    self.assertEqual(data['extras'], {'level': 4, 'flag': 1, 'coins': 10})

  def test_get_task_metrics_handles_malformed_logs_and_get_state_errors(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_device.get_state.return_value = device_env_service_pb2.DeviceState()
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    task_textproto = (
        'id: "log_task"\n'
        'name: "Log Task"\n'
        'log_parsing_config: {\n'
        '  log_regexps: {\n'
        '    extra: ["^extra: (?P<name>[^ ]+)[ ]*(?P<extra>.*)$"]\n'
        '    json_extra: ["^json_extra: (?P<json_extra>.*)$"]\n'
        '  }\n'
        '}\n'
    )
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'log_task.textproto', content=task_textproto
    ).full_path
    tools.load_task(task_path)

    state = device_env_service_pb2.DeviceState()
    sig = state.signals.add()
    sig.type = device_env_service_pb2.DEVICE_SIGNAL_SYSTEM_LOGS
    sig.system_logs.values.extend([
        'I/AndroidRLTask: extra: greeting hello world',
        'I/AndroidRLTask: json_extra: {invalid_json',
    ])
    mock_device.get_state.return_value = state

    data = json.loads(tools.get_task_metrics())
    self.assertEqual(data['extras'], {'greeting': 'hello world'})

    mock_device.get_state.side_effect = RuntimeError('Disconnected')
    data_after_error = json.loads(tools.get_task_metrics())
    self.assertEqual(data_after_error['extras'], {'greeting': 'hello world'})

  def test_error_resilience_in_battery_and_task_adb_calls(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_device.get_state.side_effect = RuntimeError('State error')
    mock_device.execute_adb_call.side_effect = RuntimeError('ADB error')
    tools = android_mcp_tools.AndroidMcpTools(mock_device)

    with mock.patch.object(
        telemetry, 'fetch_battery_power_metrics', return_value=None
    ):
      battery_data = json.loads(tools.get_battery_metrics())
      self.assertEqual(battery_data, {'error': 'Battery telemetry unavailable'})

    task_textproto = (
        'id: "err_task"\nname: "Error Task"\nsetup_steps: [\n  { adb_request: {'
        ' install_apk: { filesystem: { path: "/a.apk" } } } },\n  {'
        ' adb_request: { press_button: { button: HOME } } }\n]\nreset_steps:'
        ' [\n  { adb_request: { press_button: { button: BACK } } }\n]\n'
    )
    temp_dir = self.create_tempdir()
    task_path = temp_dir.create_file(
        'err_task.textproto', content=task_textproto
    ).full_path
    tools.load_task(task_path)

    mock_device._adb_call_parser = mock.MagicMock()
    with mock.patch.object(
        setup_step_interpreter, 'SetupStepInterpreter'
    ) as mock_interp_cls:
      mock_interp_cls.return_value.interpret.side_effect = RuntimeError(
          'Interpreter failure'
      )
      self.assertEqual(tools.reset_task(), 'Task state reset.')


class RegisterToolsTest(absltest.TestCase):

  def test_register_tools_count(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    server = mock.MagicMock(spec=fastmcp.FastMCP)
    tools.register_tools(server)
    self.assertEqual(server.tool.call_count, 11)

  def test_register_tools_all_role(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    server = mock.MagicMock(spec=fastmcp.FastMCP)
    tools.register_tools(server, role='all')
    self.assertEqual(server.tool.call_count, 11)
    registered_names = [
        call[0][0].__name__ for call in server.tool.return_value.call_args_list
    ]
    self.assertEqual(
        registered_names,
        [
            'get_screenshot',
            'get_ui_elements',
            'get_device_info',
            'tap',
            'swipe',
            'press_key',
            'get_battery_metrics',
            'load_task',
            'reset_task',
            'get_task_info',
            'get_task_metrics',
        ],
    )

  def test_register_tools_worker_role(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    server = mock.MagicMock(spec=fastmcp.FastMCP)
    tools.register_tools(server, role='worker')
    self.assertEqual(server.tool.call_count, 6)
    registered_names = [
        call[0][0].__name__ for call in server.tool.return_value.call_args_list
    ]
    self.assertEqual(
        registered_names,
        [
            'get_screenshot',
            'get_ui_elements',
            'get_device_info',
            'tap',
            'swipe',
            'press_key',
        ],
    )
    self.assertNotIn('get_battery_metrics', registered_names)
    self.assertNotIn('load_task', registered_names)
    self.assertNotIn('reset_task', registered_names)
    self.assertNotIn('get_task_info', registered_names)
    self.assertNotIn('get_task_metrics', registered_names)

  def test_register_tools_manager_role(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    server = mock.MagicMock(spec=fastmcp.FastMCP)
    tools.register_tools(server, role='manager')
    self.assertEqual(server.tool.call_count, 8)
    registered_names = [
        call[0][0].__name__ for call in server.tool.return_value.call_args_list
    ]
    self.assertEqual(
        registered_names,
        [
            'get_screenshot',
            'get_ui_elements',
            'get_device_info',
            'get_battery_metrics',
            'load_task',
            'reset_task',
            'get_task_info',
            'get_task_metrics',
        ],
    )
    self.assertNotIn('tap', registered_names)
    self.assertNotIn('swipe', registered_names)
    self.assertNotIn('press_key', registered_names)

  def test_register_tools_invalid_role(self):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    server = mock.MagicMock(spec=fastmcp.FastMCP)
    with self.assertRaises(ValueError):
      tools.register_tools(server, role='invalid')


if __name__ == '__main__':
  absltest.main()
