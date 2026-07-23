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

"""Unit tests for Android FastMCP Tools library (CL 1 baseline)."""

import os
import pathlib
import subprocess
from unittest import mock
from absl.testing import absltest
from android_env import env_interface
from android_env import loader
from android_env.mcp import android_mcp_tools
import mcp.server.fastmcp


class AndroidMcpToolsTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.tools = android_mcp_tools.AndroidMcpTools()

  def test_tool_registration(self):
    fastmcp = mcp.server.fastmcp.FastMCP("TestAndroidEnv")
    self.tools.register_tools(fastmcp)
    tools = fastmcp._tool_manager.list_tools()
    tool_names = [t.name for t in tools]
    self.assertIn("list_devices", tool_names)
    self.assertIn("connect_device", tool_names)
    self.assertIn("disconnect_device", tool_names)

  @mock.patch.object(pathlib.Path, "exists", autospec=True, return_value=False)
  def test_get_adb_path_fallback(self, unused_mock_exists):
    fake_env = {"ANDROID_HOME": "/tmp/fake_sdk"}
    with mock.patch.dict(os.environ, fake_env, clear=True):
      path = android_mcp_tools.get_adb_path()
      self.assertEqual(path, "adb")

  @mock.patch.object(subprocess, "run", autospec=True)
  def test_list_devices(self, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=["adb", "devices"],
        returncode=0,
        stdout=(
            "List of devices"
            " attached\nemulator-5554\tdevice\n127.0.0.1:5555\tdevice\n"
        ),
    )
    devices = android_mcp_tools.list_devices()
    self.assertEqual(devices, ["emulator-5554", "127.0.0.1:5555"])

  @mock.patch.object(subprocess, "run", autospec=True)
  def test_list_devices_raises_adb_error(self, mock_run):
    mock_run.side_effect = OSError("adb binary not found")
    with self.assertRaises(android_mcp_tools.AdbError):
      android_mcp_tools.list_devices()

  @mock.patch.object(subprocess, "run", autospec=True)
  def test_list_devices_with_banner(self, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=["adb", "devices"],
        returncode=0,
        stdout=(
            "* daemon not running; starting now at tcp:5037\n"
            "* daemon started successfully\n"
            "List of devices attached\n"
            "emulator-5554\tdevice\n"
        ),
    )
    devices = android_mcp_tools.list_devices()
    self.assertEqual(devices, ["emulator-5554"])

  @mock.patch.object(
      android_mcp_tools,
      "list_devices",
      autospec=True,
      return_value=["emulator-5554"],
  )
  def test_connect_device_adb_direct(self, unused_mock_list):
    res = self.tools.connect_device(serial="emulator-5554", use_adb_direct=True)
    self.assertIn("ADB Direct Mode", res)
    self.assertEqual(self.tools.active_serial, "emulator-5554")
    self.assertTrue(self.tools.use_adb_direct)
    self.assertIsNone(self.tools.active_device_env)

  @mock.patch.object(loader, "load", autospec=True)
  def test_connect_device_loader(self, mock_load):
    mock_env_instance = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    mock_load.return_value = mock_env_instance

    res = self.tools.connect_device(
        serial="emulator-5554",
        use_adb_direct=False,
    )
    self.assertIn("Connected to AndroidEnv device 'emulator-5554'", res)
    self.assertFalse(self.tools.use_adb_direct)
    self.assertEqual(self.tools.active_serial, "emulator-5554")
    self.assertEqual(self.tools.active_device_env, mock_env_instance)
    mock_load.assert_called_once()

  @mock.patch.object(
      android_mcp_tools,
      "list_devices",
      autospec=True,
      return_value=["emulator-5554"],
  )
  def test_disconnect_device(self, unused_mock_list):
    self.tools.connect_device(serial="emulator-5554", use_adb_direct=True)
    res = self.tools.disconnect_device()
    self.assertEqual(res, "Disconnected from Android device.")
    self.assertIsNone(self.tools.active_serial)

  @mock.patch.object(
      android_mcp_tools,
      "list_devices",
      autospec=True,
      return_value=["emulator-5554"],
  )
  @mock.patch.object(loader, "load", autospec=True)
  def test_connect_device_closes_previous(self, mock_load, unused_mock_list):
    """Verifies reconnecting closes the prior environment."""
    mock_env = mock.create_autospec(
        env_interface.AndroidEnvInterface, instance=True
    )
    mock_load.return_value = mock_env

    self.tools.connect_device(serial="emulator-5554", use_adb_direct=False)
    self.assertEqual(self.tools.active_device_env, mock_env)

    # Reconnect in ADB direct mode — prior env must be closed.
    self.tools.connect_device(serial="emulator-5554", use_adb_direct=True)
    mock_env.close.assert_called_once()
    self.assertIsNone(self.tools.active_device_env)

  @mock.patch.object(
      android_mcp_tools,
      "list_devices",
      autospec=True,
      return_value=["emulator-5554"],
  )
  def test_connect_device_bogus_serial(self, unused_mock_list):
    """Verifies bogus serial raises DeviceConnectionError."""
    with self.assertRaises(android_mcp_tools.DeviceConnectionError):
      self.tools.connect_device(serial="bogus_serial", use_adb_direct=True)

  @mock.patch.object(
      android_mcp_tools,
      "list_devices",
      autospec=True,
      return_value=[],
  )
  def test_connect_device_empty_devices(self, unused_mock_list):
    """Verifies empty device list raises DeviceConnectionError."""
    with self.assertRaises(android_mcp_tools.DeviceConnectionError):
      self.tools.connect_device(serial="emulator-5554", use_adb_direct=True)

  @mock.patch.object(
      android_mcp_tools,
      "list_devices",
      autospec=True,
      side_effect=android_mcp_tools.AdbError("adb failed"),
  )
  def test_connect_device_adb_error_on_verify(self, unused_mock_list):
    """Verifies AdbError during verification raises DeviceConnectionError."""
    with self.assertRaises(android_mcp_tools.DeviceConnectionError):
      self.tools.connect_device(serial="emulator-5554", use_adb_direct=True)


if __name__ == "__main__":
  absltest.main()
