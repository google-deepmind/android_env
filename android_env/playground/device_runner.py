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

"""Device runner for AndroidEnv Playground."""

import os
import queue
import shlex
import tempfile
import time
from typing import Any
from absl import logging
from android_env.components import android_device
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.components import errors
from android_env.components import setup_step_interpreter

from google.protobuf import text_format
from android_env.playground import actions as actions_lib
from android_env.playground import coordinates
from android_env.playground import frame_processing
from android_env.playground import state as state_lib
from android_env.playground import websocket
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2
from android_env.proto import task_pb2
import numpy as np


class DeviceSetupError(errors.AndroidEnvError, RuntimeError):
  """Raised when setting up or resetting the device fails."""


def _update_orientation(curr_orient: int, orientation_container: list[int]):
  """Updates orientation in container if it changed, logging the change."""
  if curr_orient != orientation_container[0]:
    logging.info(
        'Orientation changed: %d -> %d', orientation_container[0], curr_orient
    )
    orientation_container[0] = curr_orient


def _extract_screenshot(
    device_state: device_env_service_pb2.DeviceState,
) -> np.ndarray | None:
  """Extracts RGB pixels from decoded screenshot signal in DeviceState."""
  for signal in device_state.signals:
    if (
        signal.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT
        and signal.HasField('screenshot')
        and signal.screenshot.HasField('decoded')
        and signal.screenshot.decoded.raw_pixels
    ):
      decoded = signal.screenshot.decoded
      arr = np.frombuffer(decoded.raw_pixels, dtype=np.uint8)
      return arr.reshape((decoded.height, decoded.width, 3))
  return None


def _update_frame(
    state: state_lib.PlaygroundState,
    pixels: np.ndarray,
    orientation: int,
):
  """Processes the frame, updates state, and sends it to the client."""
  jpeg_bytes = frame_processing.process_frame(pixels, orientation)
  with state.frame_lock:
    state.current_frame = jpeg_bytes
  websocket.try_send_frame(state, jpeg_bytes)


def _get_actions(
    state: state_lib.PlaygroundState, frame_rate_secs: float
) -> list[actions_lib.ClientAction]:
  """Reads and coalesces actions from the state queue."""
  actions_to_take = []
  try:
    actions_to_take.append(
        state.action_queue.get(timeout=frame_rate_secs / 2.0)
    )
    while True:
      actions_to_take.append(state.action_queue.get_nowait())
  except queue.Empty:
    pass

  raw_queue_size = len(actions_to_take)
  actions_to_take = actions_lib.coalesce_actions(actions_to_take)
  if raw_queue_size > 1:
    logging.vlog(
        1,
        'Coalesced %d actions into %d',
        raw_queue_size,
        len(actions_to_take),
    )
  return actions_to_take


def _send_client_actions(
    device: android_device.AndroidDevice,
    actions: list[actions_lib.ClientAction],
    state: state_lib.PlaygroundState,
    orientation_container: list[int],
    last_pos: np.ndarray,
    raw_shape: tuple[int, int],
) -> tuple[np.ndarray, np.ndarray | None]:
  """Sends client actions to the device and updates timing stats."""
  device_state = None
  for i, act_data in enumerate(actions):
    if state.get_reload() is not None:
      logging.info(
          'Reload requested during action execution. Aborting remaining'
          ' actions.'
      )
      break
    pos = coordinates.map_client_coordinates(
        act_data.x, act_data.y, orientation_container[0], raw_shape
    )
    last_pos = pos

    now_ms = time.time() * 1000
    transit_ms = act_data.recv_timestamp_ms - act_data.client_timestamp_ms
    queue_ms = now_ms - act_data.recv_timestamp_ms
    total_pre_step_ms = now_ms - act_data.client_timestamp_ms
    logging.vlog(
        1,
        'Action %d/%d [%s]: Transit: %.2f ms, Queue: %.2f ms, Total'
        ' pre-step: %.2f ms',
        i + 1,
        len(actions),
        act_data.action_type,
        transit_ms,
        queue_ms,
        total_pre_step_ms,
    )
    state.add_stat('action_transit_ms', transit_ms)
    state.add_stat('action_queue_ms', queue_ms)
    state.add_stat('action_total_pre_step_ms', total_pre_step_ms)

    proto_action = actions_lib.map_client_action_to_proto(act_data, pos)

    start_step = time.time()
    device.send_action(proto_action)
    step_duration_ms = (time.time() - start_step) * 1000
    logging.vlog(1, 'device.send_action took: %.2f ms', step_duration_ms)
    state.add_stat('device_send_action_ms', step_duration_ms)
    state.add_stat('env_step_ms', step_duration_ms)

    device_state = device.get_state()
    _update_orientation(device_state.orientation, orientation_container)

  if device_state is None:
    device_state = device.get_state()
    _update_orientation(device_state.orientation, orientation_container)

  pixels = _extract_screenshot(device_state)
  if pixels is not None:
    _update_frame(state, pixels, orientation_container[0])

  return last_pos, pixels


def _update_battery_stats(
    device_state: device_env_service_pb2.DeviceState,
    state: state_lib.PlaygroundState,
) -> None:
  """Fetches battery power metrics from device_state and updates state if present."""
  for signal in device_state.signals:
    if (
        signal.type == device_env_service_pb2.DEVICE_SIGNAL_BATTERY_POWER
        and signal.HasField('battery_power')
    ):
      state.set_battery_power_stats(signal.battery_power)
      return


def _load_task_proto(task_id: str, tmp_dir: str) -> task_pb2.Task:
  """Resolves a task_id, inline textproto, or file path into a Task protobuf."""
  if '\n' in task_id or any(
      k in task_id for k in ('setup_steps', 'reset_steps', 'id:')
  ):
    return text_format.Parse(task_id, task_pb2.Task())

  expanded_path = os.path.expanduser(task_id)
  del tmp_dir
  task = task_pb2.Task()
  with open(expanded_path, 'r') as proto_file:
    text_format.Parse(proto_file.read(), task)
  return task


def _get_interpreter_for_device(
    device: android_device.AndroidDevice,
) -> setup_step_interpreter.SetupStepInterpreter:
  """Creates a SetupStepInterpreter configured for the given AndroidDevice."""
  parser = getattr(device, '_adb_call_parser', None)
  if parser is None:

    class _AdbParserAdapter:

      def __init__(self, dev: android_device.AndroidDevice):
        self._dev = dev

      def parse(self, call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
        return self._dev.execute_adb_call(call)

    parser = _AdbParserAdapter(device)
  return setup_step_interpreter.SetupStepInterpreter(parser)  # pyrefly: ignore[bad-argument-type]


def _handle_task_reload(
    device: android_device.AndroidDevice,
    state: state_lib.PlaygroundState,
    orientation_container: list[int],
    current_task: task_pb2.Task | None,
) -> tuple[task_pb2.Task | None, np.ndarray | None]:
  """Checks state for a pending task reload request and executes setup steps."""
  task_id = state.get_reload()
  if not task_id:
    return current_task, None

  state.clear_reload()
  websocket.try_send_status(state, f'Loading task: {task_id}...')
  with tempfile.TemporaryDirectory(prefix='android_env_task_') as tmp_dir:
    try:
      task = _load_task_proto(task_id, tmp_dir)
    except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
      logging.exception('Failed to load task %s: %s', task_id, e)
      websocket.try_send_status(state, f'ERROR loading task {task_id}: {e}')
      return current_task, None

    try:
      interpreter = _get_interpreter_for_device(device)
      interpreter.interpret(task.setup_steps)
    except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
      logging.exception(
          'Failed to execute task setup steps for %s: %s', task_id, e
      )
      websocket.try_send_status(state, f'ERROR setting up task {task_id}: {e}')
      return current_task, None

  pixels = None
  try:
    device_state = device.get_state()
    _update_orientation(device_state.orientation, orientation_container)
    pixels = _extract_screenshot(device_state)
    if pixels is not None:
      _update_frame(state, pixels, orientation_container[0])
  except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
    logging.exception(
        'Failed to get device state after loading task %s: %s', task_id, e
    )

  websocket.try_send_status(state, f'Ready! Task: {task_id}')
  return task, pixels


def _handle_episode_reset(
    device: android_device.AndroidDevice,
    state: state_lib.PlaygroundState,
    orientation_container: list[int],
    current_task: task_pb2.Task | None,
) -> np.ndarray | None:
  """Checks state for a pending episode reset request and executes reset steps."""
  if not state.get_reset():
    return None

  state.clear_reset()
  websocket.try_send_status(state, 'Resetting episode...')
  try:
    if current_task is not None and current_task.reset_steps:
      interpreter = _get_interpreter_for_device(device)
      interpreter.interpret(current_task.reset_steps)
  except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
    logging.exception('Failed to reset episode: %s', e)
    websocket.try_send_status(state, f'ERROR resetting episode: {e}')
    return None

  pixels = None
  try:
    device_state = device.get_state()
    _update_orientation(device_state.orientation, orientation_container)
    pixels = _extract_screenshot(device_state)
    if pixels is not None:
      _update_frame(state, pixels, orientation_container[0])
  except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
    logging.exception('Failed to get device state after reset: %s', e)
    websocket.try_send_status(state, f'ERROR resetting episode: {e}')
    return None

  websocket.try_send_status(state, 'Ready! Episode reset.')
  return pixels


def _execute_single_adb_command(
    device: android_device.AndroidDevice,
    state: state_lib.PlaygroundState,
    cmd: str,
) -> None:
  """Parses and executes a single ADB command against device and sends response."""
  try:
    args = shlex.split(cmd)
  except ValueError as e:
    websocket.try_send_adb_response(
        state,
        command=cmd,
        status='FAILED_PRECONDITION',
        output='',
        error=f'Invalid command syntax: {e}',
    )
    return

  if args[:1] == ['adb']:
    args = args[1:]

  if not args:
    websocket.try_send_adb_response(
        state,
        command=cmd,
        status='FAILED_PRECONDITION',
        output='',
        error='Empty ADB command.',
    )
    return

  start_ms = time.time() * 1000
  request = adb_pb2.AdbRequest(
      generic=adb_pb2.AdbRequest.GenericRequest(args=args)
  )
  try:
    response = device.execute_adb_call(request)
  except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
    duration_ms = time.time() * 1000 - start_ms
    websocket.try_send_adb_response(
        state,
        command=cmd,
        status='INTERNAL_ERROR',
        output='',
        error=str(e),
        duration_ms=duration_ms,
    )
    return

  duration_ms = time.time() * 1000 - start_ms
  try:
    status_name = adb_pb2.AdbResponse.Status.Name(response.status)
  except ValueError:
    status_name = str(response.status)
  output_text = response.generic.output.decode('utf-8', errors='replace')
  websocket.try_send_adb_response(
      state,
      command=cmd,
      status=status_name,
      output=output_text,
      error=response.error_message,
      duration_ms=duration_ms,
  )


def _handle_adb_commands(
    device: android_device.AndroidDevice, state: state_lib.PlaygroundState
) -> None:
  """Drains and executes all queued ADB commands."""
  while True:
    try:
      cmd = state.adb_queue.get_nowait()
    except queue.Empty:
      break
    _execute_single_adb_command(device, state, cmd)


def run_device(
    device: android_device.AndroidDevice,
    initial_orientation: int,
    initial_pixels: np.ndarray,
    state: state_lib.PlaygroundState,
) -> None:
  """Runs the device loop, handling actions and updating frames."""
  frame_rate_secs = 1.0 / 30.0
  prev_frame_time = time.time()
  last_pos = np.array([0.0, 0.0], dtype=np.float32)

  orientation_container = [initial_orientation]
  last_stats_send_time = time.time()
  current_pixels = initial_pixels
  current_task: task_pb2.Task | None = None

  # Send initial frame
  _update_frame(state, current_pixels, orientation_container[0])

  while state.running:
    current_task, new_pixels = _handle_task_reload(
        device, state, orientation_container, current_task
    )
    if new_pixels is not None:
      current_pixels = new_pixels

    new_pixels = _handle_episode_reset(
        device, state, orientation_container, current_task
    )
    if new_pixels is not None:
      current_pixels = new_pixels

    _handle_adb_commands(device, state)

    actions = _get_actions(state, frame_rate_secs)

    if actions:
      try:
        last_pos, new_pixels = _send_client_actions(
            device,
            actions,
            state,
            orientation_container,
            last_pos,
            current_pixels.shape[:2],
        )
        if new_pixels is not None:
          current_pixels = new_pixels
      except Exception:  # pylint: disable=broad-exception-caught
        logging.exception('Error processing client actions')
    else:
      # Idle: poll device state for screen changes without injecting dummy
      # actions.
      try:
        device_state = device.get_state()
        _update_orientation(device_state.orientation, orientation_container)
        pixels = _extract_screenshot(device_state)
        if pixels is not None:
          current_pixels = pixels
          _update_frame(state, current_pixels, orientation_container[0])
      except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
        logging.vlog(1, 'Failed to fetch device state during idle poll: %s', e)

    # Limit frame rate
    now = time.time()
    elapsed = now - prev_frame_time
    if elapsed < frame_rate_secs:
      time.sleep(frame_rate_secs - elapsed)
    prev_frame_time = time.time()

    # Periodically send accumulated stats (every 500ms)
    now = time.time()
    if now - last_stats_send_time > 0.5:
      try:
        device_state = device.get_state()
        _update_battery_stats(device_state, state)
      except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
        logging.vlog(1, 'Failed to fetch device state for stats: %s', e)
      stats = state.flush_stats()
      if stats:
        websocket.try_send_stats(state, stats)
      last_stats_send_time = now


def setup_device(
    state: state_lib.PlaygroundState,
    config: Any,
) -> tuple[android_device.AndroidDevice, int, np.ndarray]:
  """Loads and connects to AndroidDevice, returning the device, orientation and first frame pixels."""

  def set_status(text: str):
    logging.info('Status: %s', text)
    websocket.try_send_status(state, text)

  set_status('Loading configuration...')
  if not config:
    logging.error('No configuration provided.')
    set_status('ERROR: No config')
    raise DeviceSetupError('No configuration provided.')

  # Extract device config if wrapped in an AndroidEnvConfig.
  if isinstance(config, config_classes.AndroidEnvConfig):
    device_config = config.simulator
  else:
    device_config = config

  if not isinstance(device_config, config_classes.AndroidDeviceConfig):
    raise DeviceSetupError(
        f'Expected AndroidDeviceConfig, got {type(device_config).__name__}'
    )

  set_status('Launching Device / Connecting (this may take 1-2 mins)...')
  try:
    device = android_device_loader.load_android_device(device_config)
  except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
    logging.exception('Error during device setup')
    set_status(f'ERROR: {e}')
    raise DeviceSetupError(f'Error during device setup: {e}') from e

  set_status('Fetching initial device state...')
  try:
    device_state = device.get_state()
    orientation = device_state.orientation
    pixels = _extract_screenshot(device_state)
    if pixels is None:
      raise errors.ReadObservationError(
          'Initial device state is missing decoded screenshot.'
      )
  except (errors.AndroidEnvError, RuntimeError, ValueError, OSError) as e:
    logging.exception('Error after loading device, closing device.')
    device.close()
    set_status(f'ERROR: {e}')
    raise DeviceSetupError(f'Error fetching initial device state: {e}') from e

  _update_battery_stats(device_state, state)
  set_status(f'Ready! Orientation: {orientation}')
  return device, orientation, pixels
