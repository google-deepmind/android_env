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

"""Unit tests for FastMCP server entrypoint in android_mcp_server."""

from unittest import mock

from absl import app
from absl.testing import absltest
from absl.testing import flagsaver
from absl.testing import parameterized
from android_env.components import android_device as android_device_mod
from android_env.components import android_device_loader
from android_env.mcp import android_mcp_server
from android_env.mcp import android_mcp_tools
from mcp.server import fastmcp


class AndroidMcpServerTest(parameterized.TestCase):

  @parameterized.named_parameters(
      ('all_role', 'all', 11),
      ('worker_role', 'worker', 6),
      ('manager_role', 'manager', 8),
  )
  def test_register_tools_delegates_with_role(
      self, role: str, expected_count: int
  ):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    tools = android_mcp_tools.AndroidMcpTools(mock_device)
    server = mock.MagicMock(spec=fastmcp.FastMCP)

    android_mcp_server.register_tools(server, tools, role=role)

    self.assertEqual(server.tool.call_count, expected_count)

  def test_main_raises_on_extra_arguments(self):
    with self.assertRaisesRegex(
        app.UsageError, 'Too many command-line arguments'
    ):
      android_mcp_server.main(['android_mcp_server', 'extra_arg'])

  @mock.patch.object(
      android_device_loader, 'load_android_device', autospec=True
  )
  @mock.patch.object(fastmcp, 'FastMCP', autospec=True)
  def test_main_initializes_device_and_runs_server(
      self, mock_fastmcp_cls, mock_load_device
  ):
    mock_device = mock.create_autospec(
        android_device_mod.AndroidDevice, instance=True
    )
    mock_load_device.return_value = mock_device
    mock_server = mock_fastmcp_cls.return_value

    with flagsaver.flagsaver(
        serial='pixel-1234',
        host='127.0.0.1',
        websocket_port=9000,
        role='worker',
        task_path=None,
    ):
      android_mcp_server.main(['android_mcp_server'])

    mock_load_device.assert_called_once()
    loaded_config = mock_load_device.call_args[0][0]
    self.assertEqual(loaded_config.serial, 'pixel-1234')
    self.assertTrue(loaded_config.auto_setup)
    self.assertEqual(loaded_config.device_connection.host, '127.0.0.1')
    self.assertEqual(loaded_config.device_connection.websocket_port, 9000)
    self.assertEqual(mock_server.tool.call_count, 6)
    mock_server.run.assert_called_once_with(transport='stdio')


if __name__ == '__main__':
  absltest.main()
