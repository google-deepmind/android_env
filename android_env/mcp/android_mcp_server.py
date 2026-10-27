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

"""FastMCP server binary for AndroidEnv device interaction.

Provides a stdio FastMCP server entrypoint for AndroidEnv device management
and interaction with role-scoped tool registration.

Usage:
  python -m android_env.mcp.android_mcp_server --serial=emulator-5554
"""

from collections.abc import Sequence

from absl import app
from absl import flags
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.mcp import android_mcp_tools
from mcp.server import fastmcp

WORKER_TOOLS = android_mcp_tools.WORKER_TOOLS
MANAGER_TOOLS = android_mcp_tools.MANAGER_TOOLS

_SERIAL = flags.DEFINE_string(
    'serial', None, 'ADB serial number of target device.'
)
_WEBSOCKET_PORT = flags.DEFINE_integer(
    'websocket_port', 8000, 'On-device WebSocket port.'
)
_HOST = flags.DEFINE_string('host', 'localhost', 'On-device WebSocket host.')
_ROLE = flags.DEFINE_enum(
    'role',
    'all',
    list(android_mcp_tools.VALID_ROLES),
    'Role of this MCP server instance determining which tools are registered.',
)
_TASK_PATH = flags.DEFINE_string(
    'task_path', None, 'Path to task textproto file.'
)


def register_tools(
    mcp_server: fastmcp.FastMCP,
    tools: android_mcp_tools.AndroidMcpTools,
    role: str = 'all',
) -> None:
  """Registers tools on `mcp_server` scoped to the specified `role`.

  Args:
    mcp_server: FastMCP server instance where tool handlers will be registered.
    tools: `AndroidMcpTools` instance providing the tool implementations.
    role: Role of this MCP server instance (`'all'`, `'worker'`, or
      `'manager'`). Defaults to `'all'`.
  """
  tools.register_tools(mcp_server, role=role)


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  config = config_classes.AndroidDeviceConfig(
      serial=_SERIAL.value,  # pyrefly: ignore[bad-argument-type]
      auto_setup=True,
      device_connection=config_classes.DeviceConnectionConfig(
          host=_HOST.value,
          websocket_port=_WEBSOCKET_PORT.value,
      ),
  )

  device = android_device_loader.load_android_device(config)
  mcp_server = fastmcp.FastMCP(name='android_mcp_server')
  tools_handler = android_mcp_tools.AndroidMcpTools(
      device, task_path=_TASK_PATH.value
  )
  register_tools(mcp_server, tools_handler, role=_ROLE.value)
  mcp_server.run(transport='stdio')


if __name__ == '__main__':
  app.run(main)
