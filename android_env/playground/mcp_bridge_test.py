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

"""Unit tests for PlaygroundMcpBridge."""

import json
from typing import Any, cast
from unittest import mock

from absl.testing import absltest
from android_env.playground import mcp_bridge
from android_env.playground import state
from android_env.proto.a11y import android_accessibility_forest_pb2
import dm_env
import numpy as np


class PlaygroundMcpBridgeTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.state = cast(Any, state.PlaygroundState())
    self.bridge = mcp_bridge.PlaygroundMcpBridge(self.state)

  def test_get_screenshot_raises_when_empty(self):
    with self.assertRaises(RuntimeError):
      self.bridge.get_screenshot()

  def test_get_screenshot_returns_base64(self):
    with self.state.frame_lock:
      self.state.current_frame = b'fake_png_bytes'
    encoded = self.bridge.get_screenshot()
    self.assertEqual(encoded, 'ZmFrZV9wbmdfYnl0ZXM=')

  def test_tap_enqueues_down_and_up(self):
    res = self.bridge.tap(0.25, 0.75)
    self.assertIn('Tapped at (0.250, 0.750)', res)
    first = self.state.action_queue.get_nowait()
    second = self.state.action_queue.get_nowait()
    self.assertEqual(first, {'type': 'down', 'x': 0.25, 'y': 0.75})
    self.assertEqual(second, {'type': 'up', 'x': 0.25, 'y': 0.75})

  def test_tap_out_of_bounds_raises(self):
    with self.assertRaises(ValueError):
      self.bridge.tap(1.5, 0.5)
    with self.assertRaises(ValueError):
      self.bridge.tap(-0.1, 0.5)

  def test_swipe_enqueues_down_moves_up(self):
    res = self.bridge.swipe(0.5, 0.8, 0.5, 0.2, steps=3)
    self.assertIn('Swiped from (0.500, 0.800) to (0.500, 0.200)', res)
    actions = []
    while not self.state.action_queue.empty():
      actions.append(self.state.action_queue.get_nowait())
    self.assertLen(actions, 5)
    self.assertEqual(actions[0]['type'], 'down')
    self.assertEqual(actions[1]['type'], 'move')
    self.assertEqual(actions[-1]['type'], 'up')
    self.assertAlmostEqual(actions[-1]['y'], 0.2)

  def test_swipe_invalid_args_raises(self):
    with self.assertRaises(ValueError):
      self.bridge.swipe(0.0, 0.0, 2.0, 1.0)
    with self.assertRaises(ValueError):
      self.bridge.swipe(0.1, 0.1, 0.9, 0.9, steps=0)

  def test_press_key_enqueues_button(self):
    res = self.bridge.press_key('BACK')
    self.assertEqual(res, 'Pressed key back')
    act = self.state.action_queue.get_nowait()
    self.assertEqual(act, {'type': 'button', 'button': 'back'})

  def test_get_device_info_with_timestep(self):
    self.state.set_status('Running')
    self.state.set_orientation(1)
    ts = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=2.5,
        discount=1.0,
        observation={'pixels': np.zeros((800, 480, 3), dtype=np.uint8)},
    )
    self.state.set_last_timestep(ts)
    info = json.loads(self.bridge.get_device_info())
    self.assertEqual(info['status'], 'Running')
    self.assertEqual(info['orientation'], 1)
    self.assertEqual(info['orientation_name'], 'LANDSCAPE_90')
    self.assertEqual(info['reward'], 2.5)
    self.assertEqual(info['cumulative_reward'], 2.5)
    self.assertEqual(info['screen_height'], 800)
    self.assertEqual(info['screen_width'], 480)

  def test_get_device_info_includes_battery_power(self):
    mock_env = mock.MagicMock()
    mock_bp = mock.MagicMock()
    mock_bp.level_percent = 92
    mock_bp.current_now_ua = 350000
    mock_bp.voltage_mv = 4150
    mock_bp.power_mw = 1452.5
    mock_bp.temperature_celsius = 29.8
    mock_bp.status = 'DISCHARGING'
    mock_bp.plugged_source = 'UNPLUGGED'
    mock_bp.charge_counter_uah = 3900000
    mock_bp.thermal_status = 0
    mock_bp.energy_counter_nwh = 15200000000
    mock_env.task_extras.return_value = {'battery_power': mock_bp}
    self.state.set_env(mock_env)

    info = json.loads(self.bridge.get_device_info())
    self.assertIn('battery_power', info)
    self.assertEqual(info['battery_power']['level_percent'], 92)
    self.assertEqual(info['battery_power']['power_mw'], 1452.5)
    self.assertEqual(info['battery_power']['status'], 'DISCHARGING')
    self.assertEqual(info['battery_power']['charge_counter_uah'], 3900000)

  def test_get_ui_elements_from_proto_tree_and_json(self):
    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    win = forest.windows.add()
    win.title = 'MainApp'
    win.id = 1
    node = win.tree.nodes.add()
    node.unique_id = 10
    node.depth = 0
    node.class_name = 'android.widget.Button'
    node.text = 'Submit'
    node.is_clickable = True
    node.is_enabled = True
    node.bounds_in_screen.left = 10
    node.bounds_in_screen.top = 20
    node.bounds_in_screen.right = 100
    node.bounds_in_screen.bottom = 80

    mock_env = mock.MagicMock()
    arr = np.empty((1,), dtype=object)
    arr[0] = forest
    mock_env.task_extras.return_value = {'accessibility_tree': arr}
    self.state.set_env(mock_env)

    res = self.bridge.get_ui_elements('tree')
    self.assertIn('[Window] "MainApp" id=1', res)
    self.assertIn(
        '[android.widget.Button] "Submit" {10,20,100,80} [clickable enabled]',
        res,
    )

    res_json = self.bridge.get_ui_elements('json')
    parsed = json.loads(res_json)
    self.assertIn('windows', parsed)

  def test_get_ui_elements_invalid_format_raises(self):
    with self.assertRaises(ValueError):
      self.bridge.get_ui_elements('xml')

  def test_list_tools_and_execute_tool_dispatch(self):
    tools = self.bridge.list_tools()
    self.assertGreaterEqual(len(tools), 6)

    res_tap = self.bridge.execute_tool('tap', {'x': 0.5, 'y': 0.5})
    self.assertEqual(res_tap['status'], 'ok')

    res_wait = self.bridge.execute_tool('wait', {'seconds': 0.01})
    self.assertEqual(res_wait['status'], 'ok')

    res_done = self.bridge.execute_tool('done', {'summary': 'Won 2048'})
    self.assertEqual(res_done['status'], 'done')
    self.assertEqual(res_done['output'], 'Won 2048')

    res_unknown = self.bridge.execute_tool('nonexistent', {})
    self.assertEqual(res_unknown['status'], 'error')

    with self.state.frame_lock:
      self.state.current_frame = b'png_bytes'
    self.assertEqual(
        self.bridge.execute_tool('get_screenshot', {})['status'], 'ok'
    )
    self.assertEqual(
        self.bridge.execute_tool('get_device_info', {})['status'], 'ok'
    )
    self.assertEqual(
        self.bridge.execute_tool('get_ui_elements', {})['status'], 'ok'
    )
    self.assertEqual(
        self.bridge.execute_tool('press_key', {'key': 'home'})['status'], 'ok'
    )
    self.assertEqual(
        self.bridge.execute_tool(
            'swipe',
            {'start_x': 0.2, 'start_y': 0.5, 'end_x': 0.8, 'end_y': 0.5},
        )['status'],
        'ok',
    )
    self.assertEqual(
        self.bridge.execute_tool('tap', {'x': 5.0, 'y': 0.5})['status'],
        'error',
    )

    call_ok = self.bridge.call_tool('wait', {'seconds': 0.01})
    self.assertTrue(call_ok['success'])
    call_err = self.bridge.call_tool('tap', {'x': -1.0, 'y': 0.5})
    self.assertFalse(call_err['success'])

    self.state.reset_cumulative_reward()
    self.assertEqual(self.state.get_cumulative_reward(), 0.0)
    self.state.clear_action_queue()
    self.assertTrue(self.state.action_queue.empty())

  def test_get_ui_elements_fallbacks_and_bytes(self):
    self.state.set_env(None)
    self.assertIn('No active environment', self.bridge.get_ui_elements())

    forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
    win = forest.windows.add()
    win.title = 'BytesApp'
    win.id = 2

    mock_env = mock.MagicMock()
    arr = np.empty((1,), dtype=object)
    arr[0] = forest.SerializeToString()
    mock_env.task_extras.return_value = {'accessibility_tree': arr}
    self.state.set_env(mock_env)
    self.assertIn('BytesApp', self.bridge.get_ui_elements('tree'))

    mock_env.task_extras.return_value = {}
    ts = dm_env.TimeStep(
        step_type=dm_env.StepType.MID,
        reward=0.0,
        discount=1.0,
        observation={'accessibility_tree': forest},
    )
    self.state.set_last_timestep(ts)
    self.assertIn('BytesApp', self.bridge.get_ui_elements('tree'))

    self.state.set_last_timestep(None)
    self.assertIn(
        'Accessibility tree not available', self.bridge.get_ui_elements('tree')
    )


if __name__ == '__main__':
  absltest.main()
