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
and interaction.

Usage:
  android-env-mcp --serial=emulator-5554
  android-env-mcp --avd_name=my_avd
  python -m android_env.mcp.android_mcp_server --serial=emulator-5554
"""

from collections.abc import Sequence
import os

from absl import app
from absl import flags
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.mcp import android_mcp_tools
from mcp.server import fastmcp

_SERIAL = flags.DEFINE_string(
    'serial', '', 'ADB serial number of target device.'
)
_AVD_NAME = flags.DEFINE_string(
    'avd_name', '', 'Local Android Virtual Device (AVD) name to launch.'
)
_ADB_PATH = flags.DEFINE_string(
    'adb_path', 'adb', 'Filesystem path to the adb binary.'
)
_WEBSOCKET_PORT = flags.DEFINE_integer(
    'websocket_port', 8000, 'On-device WebSocket port.'
)
_HOST = flags.DEFINE_string('host', 'localhost', 'On-device WebSocket host.')


def _build_config() -> config_classes.AndroidDeviceConfig:
  """Builds an AndroidDeviceConfig from command-line flags."""
  if _SERIAL.value and _AVD_NAME.value:
    raise app.UsageError('Specify at most one of --serial or --avd_name.')

  device_connection = config_classes.DeviceConnectionConfig(
      host=_HOST.value,
      websocket_port=_WEBSOCKET_PORT.value,
  )
  if not _AVD_NAME.value:
    return config_classes.AndroidDeviceConfig(
        serial=_SERIAL.value,
        adb_path=_ADB_PATH.value,
        auto_setup=True,
        device_connection=device_connection,
    )

  android_home = os.environ.get('ANDROID_HOME', '~/Android/Sdk')
  android_avd_home = os.environ.get('ANDROID_AVD_HOME', '~/.android/avd')
  adb_path = (
      _ADB_PATH.value
      if _ADB_PATH.value != 'adb'
      else os.path.join(android_home, 'platform-tools', 'adb')
  )
  return config_classes.AndroidDeviceConfig(
      adb_path=adb_path,
      auto_setup=True,
      device_connection=device_connection,
      emulator_launcher=config_classes.EmulatorLauncherConfig(
          avd_name=_AVD_NAME.value,
          android_avd_home=android_avd_home,
          android_sdk_root=android_home,
          emulator_path=os.path.join(android_home, 'emulator', 'emulator'),
      ),
  )


def main(argv: Sequence[str]) -> None:
  if len(argv) > 1:
    raise app.UsageError('Too many command-line arguments.')

  config = _build_config()
  with android_device_loader.load_android_device(config) as device:
    mcp_server = fastmcp.FastMCP(name='android_mcp_server')
    tools_handler = android_mcp_tools.AndroidMcpTools(device)
    tools_handler.register_tools(mcp_server)
    mcp_server.run(transport='stdio')


def run() -> None:
  """Console-script entry point for `android-env-mcp`."""
  app.run(main)


if __name__ == '__main__':
  run()
