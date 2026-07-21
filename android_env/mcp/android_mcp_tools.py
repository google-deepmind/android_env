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

"""FastMCP tool implementation and device state management for AndroidEnv.

Exposes Android device inspection and interaction capabilities to LLM agents.
"""

import os
import pathlib
import subprocess
from absl import logging
from android_env import env_interface
from android_env import loader
from android_env.components import config_classes
import mcp.server.fastmcp


class AndroidMcpError(Exception):
  """Base exception for Android MCP operations."""


class AdbError(AndroidMcpError):
  """Raised when ADB commands fail or execution errors occur."""


class DeviceConnectionError(AndroidMcpError):
  """Raised when connecting or disconnecting a device fails."""


def get_adb_path() -> str:
  """Finds adb binary in runfiles, environment, or system PATH.

  Returns:
    Absolute path to adb binary, or 'adb' fallback string.
  """

  android_home = os.environ.get("ANDROID_HOME")
  if android_home:
    path = pathlib.Path(android_home) / "platform-tools" / "adb"
    if path.exists():
      return str(path)

  return "adb"


def list_devices() -> list[str]:
  """Lists all connected Android devices/emulators via ADB.

  Returns:
    List of active device serial numbers (e.g. ['emulator-5554']).

  Raises:
    AdbError: If adb command execution fails.
  """
  adb_bin = get_adb_path()
  try:
    result = subprocess.run(
        [adb_bin, "devices"],
        capture_output=True,
        text=True,
        check=True,
    )
    output = result.stdout
  except (subprocess.CalledProcessError, OSError) as e:
    raise AdbError(f"Error running adb devices: {e}") from e

  lines = output.strip().splitlines()

  if "List of devices attached" in lines:
    header_idx = lines.index("List of devices attached")
    device_lines = lines[header_idx + 1 :]
  else:
    device_lines = lines

  devices = []
  for line in device_lines:
    if line.strip():
      parts = line.split()
      if len(parts) >= 2 and parts[1] == "device":
        devices.append(parts[0])
  return devices


class AndroidMcpTools:
  """FastMCP tools and device state manager for AndroidEnv.

  Note:
    This class manages state (_active_serial, _active_device_env,
    _use_adb_direct) for single-session/single-client operation (e.g. stdio
    transport with a single agent). It is not thread-safe for concurrent multi-
    client HTTP/Sse connections.
  """

  def __init__(self) -> None:
    self._active_device_env: env_interface.AndroidEnvInterface | None = None
    self._active_serial: str | None = None
    self._use_adb_direct: bool = True

  @property
  def active_serial(self) -> str | None:
    return self._active_serial

  @property
  def use_adb_direct(self) -> bool:
    return self._use_adb_direct

  @property
  def active_device_env(self) -> env_interface.AndroidEnvInterface | None:
    return self._active_device_env

  def connect_device(
      self,
      serial: str | None = None,
      use_adb_direct: bool = True,
  ) -> str:
    """Connects MCP server to an Android device.

    Args:
      serial: Target ADB device serial (e.g. 'emulator-5554'). If None,
        auto-picks first device.
      use_adb_direct: If True (default), routes actions through ADB shell
        directly, allowing MCP tools to run concurrently alongside Playground
        web UI without closing stream connections.

    Returns:
      Status string indicating connection result.

    Raises:
      DeviceConnectionError: If device auto-detection or connection fails.
    """
    # Gracefully close any existing connection before establishing a new one.
    self.disconnect_device()

    target_serial = serial
    fetched_devices: list[str] = []

    if not target_serial:
      try:
        fetched_devices = list_devices()
      except AdbError as e:
        raise DeviceConnectionError(f"Failed to list devices: {e}") from e

      if not fetched_devices:
        raise DeviceConnectionError(
            "Failed to auto-detect device: No devices found."
        )
      target_serial = fetched_devices[0]

    self._use_adb_direct = use_adb_direct

    if self._use_adb_direct:
      # Verify the serial actually exists before claiming success.
      try:
        devices = fetched_devices if fetched_devices else list_devices()
        if target_serial not in devices:
          raise DeviceConnectionError(
              f"Device '{target_serial}' not found. Available: {devices}"
          )
      except AdbError as e:
        raise DeviceConnectionError(
            f"Could not verify serial '{target_serial}': {e}"
        ) from e
      self._active_serial = target_serial
      self._active_device_env = None
      return (
          f"Connected to device '{target_serial}' via ADB Direct Mode."
          " Concurrent Playground streaming active."
      )

    try:
      config = config_classes.AndroidEnvConfig()
      if isinstance(config.simulator, config_classes.EmulatorConfig):
        config.simulator.adb_controller.device_name = target_serial
      self._active_device_env = loader.load(config)
      self._active_serial = target_serial
      return f"Connected to AndroidEnv device '{target_serial}'."
    except (RuntimeError, OSError, ValueError) as e:
      raise DeviceConnectionError(
          f"Failed to connect to AndroidEnv: {e}"
      ) from e

  def disconnect_device(self) -> str:
    """Disconnects from the active Android device and resets connection state."""
    if self._active_device_env is not None:
      try:
        self._active_device_env.close()
      except (RuntimeError, OSError) as e:
        logging.warning("Error closing active device environment: %s", e)
    self._active_device_env = None
    self._active_serial = None
    self._use_adb_direct = True
    return "Disconnected from Android device."

  def register_tools(self, fastmcp: mcp.server.fastmcp.FastMCP) -> None:
    """Registers bound instance tools with a FastMCP server."""
    fastmcp.add_tool(list_devices)
    fastmcp.add_tool(self.connect_device)
    fastmcp.add_tool(self.disconnect_device)
