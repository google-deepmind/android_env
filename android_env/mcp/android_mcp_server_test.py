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

"""Unit tests for the FastMCP server entry point in android_mcp_server."""

from unittest import mock

from absl import app
from absl.testing import absltest
from absl.testing import flagsaver
from android_env.components import android_device
from android_env.components import config_classes
from android_env.mcp import android_mcp_server


class AndroidMcpServerTest(absltest.TestCase):

  def test_main_raises_usage_error_on_extra_args(self):
    with self.assertRaises(app.UsageError):
      android_mcp_server.main(['android_mcp_server', 'extra_arg'])

  @mock.patch.object(
      android_mcp_server.android_mcp_tools, 'AndroidMcpTools', autospec=True
  )
  @mock.patch.object(android_mcp_server.fastmcp, 'FastMCP', autospec=True)
  @mock.patch.object(
      android_mcp_server.android_device_loader,
      'load_android_device',
      autospec=True,
  )
  def test_main_loads_device_and_runs_stdio_server(
      self, mock_load_device, mock_fastmcp_cls, mock_tools_cls
  ):
    mock_device = mock.create_autospec(
        android_device.AndroidDevice, instance=True
    )
    mock_load_device.return_value = mock_device

    with flagsaver.flagsaver(
        (android_mcp_server._SERIAL, 'emulator-5554'),
        (android_mcp_server._HOST, '127.0.0.1'),
        (android_mcp_server._WEBSOCKET_PORT, 8001),
    ):
      android_mcp_server.main(['android_mcp_server'])

    mock_load_device.assert_called_once_with(
        config_classes.AndroidDeviceConfig(
            serial='emulator-5554',
            auto_setup=True,
            device_connection=config_classes.DeviceConnectionConfig(
                host='127.0.0.1',
                websocket_port=8001,
            ),
        )
    )
    mock_fastmcp_cls.assert_called_once_with(name='android_mcp_server')
    mock_tools_cls.assert_called_once_with(mock_device)
    mock_tools_cls.return_value.register_tools.assert_called_once_with(
        mock_fastmcp_cls.return_value
    )
    mock_fastmcp_cls.return_value.run.assert_called_once_with(transport='stdio')

  @mock.patch.object(android_mcp_server.app, 'run', autospec=True)
  def test_run_invokes_app_run(self, mock_app_run):
    android_mcp_server.run()
    mock_app_run.assert_called_once_with(android_mcp_server.main)


if __name__ == '__main__':
  absltest.main()
