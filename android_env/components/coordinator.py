# coding=utf-8
# Copyright 2023 DeepMind Technologies Limited.
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

"""Coordinator handles interaction between internal components of AndroidEnv."""

import copy
import socket
import tempfile
import threading
import time
from typing import Any

from absl import logging
from android_env.components import action_type as action_type_lib
from android_env.components import adb_call_parser
from android_env.components import errors
from android_env.components import specs
from android_env.components import task_manager as task_manager_lib
from android_env.components import utils
from android_env.components.simulators import base_simulator
from android_env.proto import adb_pb2
from android_env.proto import state_pb2
from android_env.proto import task_pb2
import dm_env
import numpy as np


class Coordinator:
  """Handles interaction between internal components of AndroidEnv."""

  def __init__(
      self,
      simulator: base_simulator.BaseSimulator,
      task_manager: task_manager_lib.TaskManager,
      num_fingers: int = 1,
      interaction_rate_sec: float = 0.0,
      enable_key_events: bool = False,
      show_touches: bool = True,
      show_pointer_location: bool = True,
      show_status_bar: bool = False,
      show_navigation_bar: bool = False,
      periodic_restart_time_min: float = 0.0,
      tmp_dir: str | None = None,
  ):
    """Handles communication between AndroidEnv and its components.

    Args:
      simulator: A BaseSimulator instance.
      task_manager: The TaskManager, responsible for coordinating RL tasks.
      num_fingers: Number of virtual fingers of the agent.
      interaction_rate_sec: How often (in seconds) to fetch the screenshot from
        the simulator (asynchronously). If <= 0, stepping the environment blocks
        on fetching the screenshot (the environment is synchronous). If > 0,
        screenshots are grabbed in a separate thread at this rate; stepping
        returns the most recently grabbed screenshot.
      enable_key_events: Whether keyboard key events are enabled.
      show_touches: Whether to show circles on the screen indicating the
        position of the current touch.
      show_pointer_location: Whether to show blue lines on the screen indicating
        the position of the current touch.
      show_status_bar: Whether or not to show the status bar (at the top of the
        screen, displays battery life, time, notifications etc.).
      show_navigation_bar: Whether or not to show the navigation bar (at the
        bottom of the screen, displayes BACK and HOME buttons, etc.)
      periodic_restart_time_min: Time between periodic restarts in minutes. If >
        0.0, will trigger a simulator restart at the end of the next episode
        once the time has been reached.
      tmp_dir: Temporary directory to write transient data.
    """
    self._simulator = simulator
    self._task_manager = task_manager
    self._num_fingers = num_fingers
    self._enable_key_events = enable_key_events
    self._show_touches = show_touches
    self._show_pointer_location = show_pointer_location
    self._show_status_bar = show_status_bar
    self._show_navigation_bar = show_navigation_bar
    self._adb_call_parser: adb_call_parser.AdbCallParser = None
    self._periodic_restart_time_min = periodic_restart_time_min
    self._tmp_dir = tmp_dir or tempfile.gettempdir()
    self._orientation = np.zeros(4, dtype=np.uint8)
    self._interaction_rate_sec = interaction_rate_sec
    self._interaction_thread = None

    # The size of the device screen in pixels (H x W).
    self._screen_size = np.array([0, 0], dtype=np.int32)

    # Initialize stats.
    self._stats = {
        'relaunch_count': 0,
        'relaunch_count_periodic': 0,
        'relaunch_count_setup_steps': 0,
        'relaunch_count_reset_steps': 0,
        'relaunch_count_simulator_launch': 0,
        'relaunch_count_simulator_reset': 0,
        'relaunch_count_execute_action': 0,
        'relaunch_count_fetch_observation': 0,
        'relaunch_count_update_settings': 0,
        'failed_task_updates': 0,
    }

    # Initialize counters.
    self._simulator_healthy = False
    self._latest_observation_time = 0
    self._simulator_start_time = None

    logging.info('Starting the simulator...')
    self._launch_simulator()

  def action_spec(self) -> dict[str, dm_env.specs.Array]:
    return specs.base_action_spec(
        num_fingers=self._num_fingers,
        enable_key_events=self._enable_key_events)

  def observation_spec(self) -> dict[str, dm_env.specs.Array]:
    return specs.base_observation_spec(
        height=self._screen_size[0], width=self._screen_size[1])

  def _update_screen_size(self) -> None:
    """Sets the screen size from a screenshot ignoring the color channel."""
    screenshot = self._simulator.get_screenshot()
    self._screen_size = np.array(screenshot.shape[:2], dtype=np.int32)

  def _update_device_orientation(self) -> None:
    """Updates the current device orientation."""

    # Skip fetching the orientation if we already have it.
    if not np.all(self._orientation == np.zeros(4)):
      logging.info('self._orientation already set, not setting it again')
      return

    orientation_response = self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            get_orientation=adb_pb2.AdbRequest.GetOrientationRequest()))
    if orientation_response.status != adb_pb2.AdbResponse.Status.OK:
      logging.error('Got bad orientation: %r', orientation_response)
      return

    orientation = orientation_response.get_orientation.orientation
    if orientation not in {0, 1, 2, 3}:
      logging.error('Got bad orientation: %r', orientation_response)
      return

    # Transform into one-hot format.
    orientation_onehot = np.zeros([4], dtype=np.uint8)
    orientation_onehot[orientation] = 1
    self._orientation = orientation_onehot

  def _lift_all_fingers(self) -> None:
    """Performs a lift action with every finger."""
    lift_action = {
        'action_type': np.array(action_type_lib.ActionType.LIFT),
        'touch_position': np.array([0, 0]),
    }
    for i in range(2, self._num_fingers + 1):
      lift_action.update({
          f'action_type_{i}': np.array(action_type_lib.ActionType.LIFT),
          f'touch_position_{i}': np.array([0, 0]),
      })
    self._send_action_to_simulator(lift_action)

  def _should_periodic_relaunch(self) -> bool:
    """Checks if it is time to restart the simulator.

    If a periodic restart time was specified, the Coordinator will re-launch
    the simulator at regular time intervals. This helps to make sure that the
    simulator is not in a stale state even if the environment has been running
    for a significant amount of time.

    Returns:
      Boolean indicating if it is time to restart the simulator.
    """

    if self._periodic_restart_time_min and self._simulator_start_time:
      sim_alive_time = (time.time() - self._simulator_start_time) / 60.0
      logging.info('Simulator has been running for %f mins', sim_alive_time)
      if sim_alive_time > self._periodic_restart_time_min:
        logging.info('Maximum alive time reached. Restarting simulator.')
        self._stats['relaunch_count_periodic'] += 1
        return True
    return False

  def _launch_simulator(self, max_retries: int = 3):
    """Launches the simulator.

    Sets up the simulator and other task-related settings.

    Args:
      max_retries: Number of times to attempt a restart before raising an error.
    """

    self._simulator_healthy = False

    # Stop screenshot thread.
    if self._interaction_thread is not None:
      self._interaction_thread.stop()
      self._interaction_thread.join()

    # Attempt to restart the system a given number of times.
    num_tries = 1
    latest_error = None
    while True:
      if num_tries > max_retries:
        raise errors.TooManyRestartsError(
            'Maximum number of restart attempts reached.') from latest_error
      logging.info('Simulator launch attempt %d of %d', num_tries, max_retries)

      self._task_manager.stop()

      # Launch the simulator.
      self._simulator.launch()
      self._simulator_start_time = time.time()

      # From here on, the simulator is assumed to be up and running.
      self._adb_call_parser = self._create_adb_call_parser()
      try:
        self._update_settings()
      except errors.AdbControllerError as e:
        logging.exception('_update_settings() failed.')
        self._stats['relaunch_count_update_settings'] += 1
        self._latest_error = e
        num_tries += 1
        continue

      # Start the task.
      self._task_manager.start(
          adb_call_parser_factory=self._create_adb_call_parser,
          log_stream=self._simulator.create_log_stream(),
      )
      try:
        self._task_manager.setup_task()
      except errors.StepCommandError as error:
        logging.exception('Failed to set up the task. Restarting simulator.')
        self._stats['relaunch_count_setup_steps'] += 1
        latest_error = error
        num_tries += 1
        continue

      # Restart was successful.
      self._simulator_healthy = True
      self._stats['relaunch_count'] += 1
      break
    if self._interaction_rate_sec > 0:
      self._interaction_thread = InteractionThread(self._simulator,
                                                   self._interaction_rate_sec)
      self._interaction_thread.start()

  def _update_settings(self) -> None:
    """Updates some internal state and preferences given in the constructor."""

    self._update_screen_size()
    self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='show_touches',
                    value='1' if self._show_touches else '0'))))
    self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SYSTEM,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='pointer_location',
                    value='1' if self._show_pointer_location else '0'))))
    if self._show_navigation_bar and self._show_status_bar:
      policy_control_value = 'null*'
    elif self._show_navigation_bar and not self._show_status_bar:
      policy_control_value = 'immersive.status=*'
    elif not self._show_navigation_bar and self._show_status_bar:
      policy_control_value = 'immersive.navigation=*'
    else:
      policy_control_value = 'immersive.full=*'
    self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='policy_control', value=policy_control_value))))

  def _create_adb_call_parser(self):
    """Creates a new AdbCallParser instance."""
    return adb_call_parser.AdbCallParser(
        adb_controller=self._simulator.create_adb_controller(),
        tmp_dir=self._tmp_dir)

  def execute_adb_call(self, call: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    return self._adb_call_parser.parse(call)

  def rl_reset(self) -> dm_env.TimeStep:
    """Resets the RL episode."""

    # Relaunch the simulator if necessary.
    if not self._simulator_healthy or self._should_periodic_relaunch():
      self._launch_simulator()

    # Reset counters.
    self._latest_observation_time = 0
    for key in self._stats:
      if key.startswith('episode'):
        self._stats[key] = 0.0

    # Execute a lift action before resetting the task.
    self._lift_all_fingers()

    # Reset the task.
    self._task_manager.reset_task()
    self._update_device_orientation()

    # Get data from the simulator.
    simulator_signals = self._gather_simulator_signals()

    return self._task_manager.rl_reset(simulator_signals)

  def rl_step(self, agent_action: dict[str, np.ndarray]) -> dm_env.TimeStep:
    """Executes the selected action and returns a timestep.

    Args:
      agent_action: Selected action to perform on the simulated Android device.
        If `agent_action` is `None` it means that this is an RL reset (to start
        a new episode).

    Returns:
      An RL timestep.
    """

    self._send_action_to_simulator(agent_action)

    # Get data from the simulator.
    try:
      simulator_signals = self._gather_simulator_signals()
    except (errors.ReadObservationError, socket.error):
      logging.exception('Unable to fetch observation. Restarting simulator.')
      self._stats['relaunch_count_fetch_observation'] += 1
      self._simulator_healthy = False

    if not self._simulator_healthy:
      return dm_env.truncation(reward=0.0, observation=None)

    return self._task_manager.rl_step(simulator_signals)

  def _gather_simulator_signals(self) -> dict[str, np.ndarray]:
    """Gathers data from various sources to assemble the RL observation."""

    # Get current timestamp and update the delta.
    now = time.time()
    timestamp_delta = (0 if self._latest_observation_time == 0 else
                       (now - self._latest_observation_time) * 1e6)
    self._latest_observation_time = now

    # Grab pixels.
    if self._interaction_rate_sec > 0:
      pixels = self._interaction_thread.screenshot()  # Async mode.
    else:
      pixels = self._simulator.get_screenshot()  # Sync mode.

    return {
        'pixels': pixels,
        'orientation': self._orientation,
        'timedelta': np.array(timestamp_delta, dtype=np.int64),
    }

  def __del__(self):
    self.close()

  def _send_action_to_simulator(self, action: dict[str, np.ndarray]) -> None:
    """Sends the selected action to the simulator.

    The simulator will interpret the action as a touchscreen event and perform
    it accordingly. The effect this action triggers in the Android OS will be
    determined by the currently running application.

    Args:
      action: action which will get interpreted as a touchscreen event.
    """

    try:
      # If the action is a TOUCH or LIFT, send a touch event to the simulator.
      if (action['action_type'] == action_type_lib.ActionType.TOUCH or
          action['action_type'] == action_type_lib.ActionType.LIFT):
        prepared_action = self._prepare_touch_action(action)
        self._simulator.send_touch(prepared_action)
      # If the action is a key event, send a key event to the simulator.
      elif action['action_type'] == action_type_lib.ActionType.KEYDOWN:
        self._simulator.send_key(
            action['keycode'].item(0), event_type='keydown'
        )
      elif action['action_type'] == action_type_lib.ActionType.KEYUP:
        self._simulator.send_key(action['keycode'].item(0), event_type='keyup')
      elif action['action_type'] == action_type_lib.ActionType.KEYPRESS:
        self._simulator.send_key(action['keycode'].item(0), event_type='keypress')
    except (socket.error, errors.SendActionError):
      logging.exception('Unable to execute action. Restarting simulator.')
      self._stats['relaunch_count_execute_action'] += 1
      self._simulator_healthy = False

  def _prepare_touch_action(
      self, action: dict[str, np.ndarray]
  ) -> list[tuple[int, int, bool, int]]:
    """Turns an AndroidEnv action into values that the simulator can interpret.

    Converts float-valued 'touch_position' to integer coordinates corresponding
    to specific pixels, and 'action_type' to booleans indicating whether the
    screen is touched at said location or not. The result of this function can
    be sent directly to the underlying simulator (e.g. the Android Emulator,
    virtual machine, or a phone).

    Args:
      action: An action containing 'action_type' and 'touch_position'.

    Returns:
      A tuple with the format (x: int, y: int, down/up: bool).
    """

    touch_events = []
    width_height = self._screen_size[::-1]
    for i, finger_action in enumerate(self._split_touch_action(action)):
      is_touch = (
          finger_action['action_type'] == action_type_lib.ActionType.TOUCH)
      touch_position = finger_action['touch_position']
      touch_pixels = utils.touch_position_to_pixel_position(
          touch_position, width_height=width_height)
      touch_events.append((touch_pixels[0], touch_pixels[1], is_touch, i))
    return touch_events

  def _split_touch_action(
      self, action: dict[str, np.ndarray]
  ) -> list[dict[str, np.ndarray]]:
    """Splits a multitouch action into a list of single-touch actions."""

    single_touch_actions = [{
        'action_type': action['action_type'],
        'touch_position': action['touch_position'],
    }]
    for i in range(2, self._num_fingers + 1):
      single_touch_actions.append({
          'action_type': action[f'action_type_{i}'],
          'touch_position': action[f'touch_position_{i}'],
      })
    return single_touch_actions

  def _get_time_since_last_observation(self) -> float:
    """Computes time passed since the last observation was fetched."""

    return time.time() - self._latest_observation_time

  def stats(self) -> dict[str, Any]:
    """Returns various statistics."""

    output = copy.deepcopy(self._stats)
    output.update(self._task_manager.stats())
    return output

  def load_state(
      self, request: state_pb2.LoadStateRequest
  ) -> state_pb2.LoadStateResponse:
    """Loads a state.

    Args:
      request: A `LoadStateRequest` containing any parameters necessary to
        specify how/what state to load.

    Returns:
      A `LoadStateResponse` containing the status, error message (if
      applicable), and any other relevant information.
    """
    self._task_manager.stop()
    response = self._simulator.load_state(request)
    self._task_manager.start(
        adb_call_parser_factory=self._create_adb_call_parser,
        log_stream=self._simulator.create_log_stream(),
    )
    return response

  def save_state(
      self, request: state_pb2.SaveStateRequest
  ) -> state_pb2.SaveStateResponse:
    """Saves a state.

    Args:
      request: A `SaveStateRequest` containing any parameters necessary to
        specify how/what state to save.

    Returns:
      A `SaveStateResponse` containing the status, error message (if
      applicable), and any other relevant information.
    """
    return self._simulator.save_state(request)

  def close(self):
    """Cleans up the state of this Coordinator."""
    if self._interaction_thread is not None:
      self._interaction_thread.stop()
      self._interaction_thread.join()

    if hasattr(self, '_task_manager'):
      self._task_manager.stop()
    if hasattr(self, '_simulator'):
      self._simulator.close()


class InteractionThread(threading.Thread):
  """A thread that interacts with a simulator."""

  def __init__(self, simulator: base_simulator.BaseSimulator,
               interaction_rate_sec: float):
    super().__init__()
    self._simulator = simulator
    self._interaction_rate_sec = interaction_rate_sec
    self._should_stop = threading.Event()
    self._screenshot = self._simulator.get_screenshot()

  def run(self):
    last_read = time.time()
    while not self._should_stop.is_set():
      self._screenshot = self._simulator.get_screenshot()

      now = time.time()
      elapsed = now - last_read
      last_read = now
      sleep_time = self._interaction_rate_sec - elapsed
      if sleep_time > 0.0:
        time.sleep(sleep_time)
    logging.info('InteractionThread.run() finished.')

  def stop(self):
    logging.info('Stopping InteractionThread.')
    self._should_stop.set()

  def screenshot(self):
    return self._screenshot
