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

"""Loader function for creating an AndroidDevice instance."""

import os
import time
from typing import Any

from absl import logging
from android_env.components import adb_call_parser
from android_env.components import adb_controller
from android_env.components import android_device
from android_env.components import config_classes
from android_env.components import device_connection
from android_env.components import errors
from android_env.components import setup_step_interpreter
from android_env.components.simulators.emulator import emulator_launcher
from android_env.components.simulators.emulator import tcp_ports
from android_env.proto import adb_pb2
from android_env.proto import task_pb2
from google.protobuf import text_format
import portpicker


def load_android_device(
    config: config_classes.AndroidDeviceConfig,
) -> android_device.AndroidDevice:
  """Loads an AndroidDevice handle configured according to `config`."""
  on_close_callbacks = []
  on_error_callbacks = []

  if config.emulator_launcher is not None:
    if config.adb_controller is None:
      config.adb_controller = config_classes.AdbControllerConfig()

    launcher_config = config.emulator_launcher
    tcp_ports.pick_emulator_ports(launcher_config)

    if not config.adb_controller.device_name:
      config.adb_controller.device_name = 'emulator-%d' % (
          launcher_config.adb_port - 1
      )

    launcher = emulator_launcher.EmulatorLauncher(
        config=config.emulator_launcher,
        adb_controller_config=config.adb_controller,
    )
    serial = config.adb_controller.device_name
    adb = adb_controller.AdbController(config.adb_controller)
    adb.init_server()

    launcher.launch_emulator_process()
    try:
      _wait_for_boot(adb)
    except (errors.AdbControllerError, RuntimeError):
      logging.exception('Failed to boot emulator (or aborted).')
      launcher.close()
      raise

    on_close_callbacks.append(launcher.close)

    def dump_logcat_cb(exc_type: Any, exc_value: Any, traceback: Any) -> None:
      del exc_type, exc_value, traceback
      logging.error(
          'Error occurred, dumping logcat to /tmp/androidenv_logcat.txt'
      )
      try:
        logcat = adb.execute_command(['logcat', '-d', '-t', '50000'])
        with open('/tmp/androidenv_logcat.txt', 'wb') as f:
          f.write(logcat)
      except (errors.AdbControllerError, OSError):
        logging.exception('Failed to dump logcat.')

    on_error_callbacks.append(dump_logcat_cb)

    local_port = portpicker.pick_unused_port()
    config.adb_path = config.adb_controller.adb_path
    config.serial = serial
    config.device_connection.websocket_port = local_port
    config.auto_setup = True

  try:
    adb = adb_controller.AdbController(
        config_classes.AdbControllerConfig(
            adb_path=config.adb_path,
            device_name=config.serial,
        )
    )

    parser = adb_call_parser.AdbCallParser(adb)
    if config.auto_setup and config.device_connection.host in (
        'localhost',
        '127.0.0.1',
    ):
      _prep_device(config, parser)

    conn = _connect_to_device(config, adb)
    return android_device.AndroidDevice(
        connection=conn,
        adb_call_parser=parser,
        on_close_callbacks=on_close_callbacks,
        on_error_callbacks=on_error_callbacks,
    )
  except (errors.AdbControllerError, RuntimeError, OSError, ValueError):
    logging.exception('Failed to load android device.')
    for cb in on_close_callbacks:
      cb()
    raise


def _wait_for_boot(
    adb: adb_controller.AdbController, timeout_sec: float = 300.0
) -> None:
  """Waits for the emulator device to finish booting."""
  deadline = time.time() + timeout_sec
  while time.time() < deadline:
    try:
      output = adb.execute_command(['shell', 'getprop', 'sys.boot_completed'])
      if output.strip() == b'1':
        return
    except errors.AdbControllerError:
      pass
    time.sleep(1.0)
  raise RuntimeError('Timed out waiting for emulator boot.')


def _get_core_apk_from_runfiles() -> str:
  """Returns the path to the android_env_server APK in runfiles."""
  return ''


def _get_prep_steps_path() -> str:
  """Returns the path to the default `device_prep_steps.textproto`."""
  return os.path.join(
      os.path.dirname(os.path.abspath(__file__)), 'device_prep_steps.textproto'
  )


def _prep_device(
    config: config_classes.AndroidDeviceConfig,
    parser: adb_call_parser.AdbCallParser,
) -> None:
  """Executes default setup steps on the device."""
  textproto_path = _get_prep_steps_path()
  with open(textproto_path, 'r') as f:
    text_content = f.read()

  task = task_pb2.Task()
  text_format.Parse(text_content, task)
  steps = list(task.setup_steps)

  apk_path = _get_core_apk_from_runfiles()
  if apk_path:
    steps.insert(
        1,
        task_pb2.SetupStep(
            adb_request=adb_pb2.AdbRequest(
                install_apk=adb_pb2.AdbRequest.InstallApk(
                    filesystem=adb_pb2.AdbRequest.InstallApk.Filesystem(
                        path=apk_path
                    )
                )
            )
        ),
    )

  forward_ws_step = task_pb2.SetupStep(
      adb_request=adb_pb2.AdbRequest(
          generic=adb_pb2.AdbRequest.GenericRequest(
              args=[
                  'forward',
                  f'tcp:{config.device_connection.websocket_port}',
                  'tcp:8000',
              ]
          )
      )
  )
  steps.insert(-2, forward_ws_step)

  interpreter = setup_step_interpreter.SetupStepInterpreter(parser)
  interpreter.interpret(steps)


def _connect_to_device(
    config: config_classes.AndroidDeviceConfig,
    adb: adb_controller.AdbController,
    max_retries: int = 3,
) -> device_connection.DeviceConnection:
  """Establishes WebSocket connection to device with retries."""
  for attempt in range(max_retries):
    try:
      return device_connection.DeviceConnection(config.device_connection)
    except (errors.AdbControllerError, RuntimeError, OSError) as e:
      logging.warning(
          'Attempt %d/%d failed to connect: %s', attempt + 1, max_retries, e
      )
      if attempt == max_retries - 1:
        raise
      if config.auto_setup and config.device_connection.host in (
          'localhost',
          '127.0.0.1',
      ):
        try:
          adb.execute_command([
              'shell',
              'am',
              'startservice',
              '-a',
              'com.google.androidenv.core.START',
              'com.google.androidenv.core/.AndroidEnvService',
          ])
        except errors.AdbControllerError:
          pass
  raise RuntimeError('Failed to connect to on-device server.')
