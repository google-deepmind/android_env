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

"""Playground for AndroidEnv, allowing human interaction via a web browser."""

import logging as std_logging
import os
import threading

from absl import app
from absl import flags
from absl import logging
from android_env.components import config_classes
from android_env.playground import device_runner
from android_env.playground import log_handler
from android_env.playground import server
from android_env.playground import state as state_lib
from android_env.playground import websocket
from android_env.playground.configs import emulator_config
from ml_collections.config_flags import config_flags

_PORT = flags.DEFINE_integer('port', 8080, 'Port to serve the web interface.')
_SERIAL = flags.DEFINE_string(
    'serial',
    None,
    'ADB serial of an already-running emulator or physical device (used when'
    ' --config is not set).',
)
_AVD_NAME = flags.DEFINE_string(
    'avd_name',
    None,
    'Local Android Virtual Device (AVD) name to launch (used when --config is'
    ' not set).',
)
_CONFIG = config_flags.DEFINE_config_file(
    'config',
    None,
    'File path to the AndroidEnv config.',
    lock_config=False,
)


def _resolve_config():
  """Resolves the Playground configuration from command-line flags."""
  if _CONFIG.value is not None:
    return _CONFIG.value
  if _SERIAL.value and _AVD_NAME.value:
    raise app.UsageError('Specify at most one of --serial or --avd_name.')
  if _SERIAL.value:
    return config_classes.AndroidDeviceConfig(serial=_SERIAL.value)
  if _AVD_NAME.value:
    return emulator_config.get_config(_AVD_NAME.value)
  return None


def _run_device_thread(state: state_lib.PlaygroundState, config):
  """Orchestrates device setup, running, and cleanup in background."""
  try:
    device, orientation, initial_pixels = device_runner.setup_device(
        state, config
    )
  except device_runner.DeviceSetupError as e:
    logging.exception('Error in device setup: %s', e)
    return

  if not state.running:
    logging.warning(
        'Server is not running; closing device without starting run loop.'
    )
    device.close()
    return

  try:
    device_runner.run_device(device, orientation, initial_pixels, state)
  except (RuntimeError, ValueError, KeyError, IndexError, OSError) as e:
    logging.exception('Error in device execution: %s', e)
    websocket.try_send_status(state, f'ERROR: {e}')
  finally:
    logging.info('Closing device...')
    device.close()


def _serve_http(state: state_lib.PlaygroundState, static_dir: str, port: int):
  """Starts the HTTP/WebSocket server and blocks until interrupted."""
  server_address = ('', port)
  server.PlaygroundServer.allow_reuse_address = True
  server.PlaygroundServer.daemon_threads = True
  with server.PlaygroundServer(
      server_address,
      server.StreamHandler,
      state,
      os.path.expanduser(static_dir),
  ) as httpd:
    logging.info('Serving static files from %s...', static_dir)
    logging.info(
        'Serving on port %s (http://localhost:%s/)...',
        port,
        port,
    )
    try:
      httpd.serve_forever()
    except KeyboardInterrupt:
      logging.info('KeyboardInterrupt caught, setting running=False')
      state.running = False
    finally:
      logging.info('Shutting down server...')


def main(_):
  config = _resolve_config()
  static_dir = server.get_default_static_dir()
  state = state_lib.PlaygroundState()

  formatter = std_logging.Formatter(
      '%(asctime)s [%(levelname)s] %(name)s: %(message)s'
  )
  custom_log_handler = log_handler.PlaygroundLogHandler(state)
  custom_log_handler.setFormatter(formatter)
  stderr_log_handler = std_logging.StreamHandler()
  stderr_log_handler.setLevel(std_logging.INFO)
  stderr_log_handler.setFormatter(formatter)

  absl_logger = logging.get_absl_logger()
  absl_logger.addHandler(custom_log_handler)
  absl_logger.addHandler(stderr_log_handler)

  # Start setup in background (must be daemon to avoid hanging on server
  # bind failure).
  setup_thread = threading.Thread(
      target=_run_device_thread,
      args=(
          state,
          config,
      ),
      daemon=True,
  )
  setup_thread.start()
  try:
    _serve_http(state, static_dir, _PORT.value)
  except OSError as e:
    logging.exception('Server failed to start on port %s: %s', _PORT.value, e)
  finally:
    logging.info('Shutting down agent...')
    state.running = False
    # Wait for setup thread to exit, but not forever (in case it is blocked
    # in boot).
    setup_thread.join(timeout=5.0)
    absl_logger.removeHandler(stderr_log_handler)
    absl_logger.removeHandler(custom_log_handler)
    stderr_log_handler.close()
    custom_log_handler.close()


def run() -> None:
  """Console-script entry point for `android-env-playground`."""
  app.run(main)


if __name__ == '__main__':
  run()
