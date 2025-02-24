# coding=utf-8
# Copyright 2024 DeepMind Technologies Limited.
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

"""Functions to convert actions between different components' formats."""

from absl import logging
from android_env.components import action_type as action_type_lib
from android_env.components import errors
from android_env.components import pixel_fns
from android_env.components.simulators import base_simulator
import numpy as np


def send_action_to_simulator(
    action: dict[str, np.ndarray],
    simulator: base_simulator.BaseSimulator,
    screen_width: int,
    screen_height: int,
    num_fingers: int,
) -> bool:
  """Sends the selected action to the given simulator.

  The simulator will interpret the action according to `action["action_type"]`.
  The effect this action triggers in the Android OS will be determined by the
  currently running application.

  Args:
    action: action which will get interpreted as a touchscreen event.
    simulator: The simulator that will receive the action.
    screen_width: The width of the touchscreen in pixels.
    screen_height: The height of the touchscreen in pixels.
    num_fingers: The number of fingers used in this simulator.
  """

  try:
    match action['action_type']:
      # If the action is a TOUCH or LIFT, send a touch event to the simulator.
      case action_type_lib.ActionType.TOUCH | action_type_lib.ActionType.LIFT:
        prepared_action = _prepare_touch_action(
            action, screen_width, screen_height, num_fingers
        )
        simulator.send_touch(prepared_action)
      # If the action is a key event, send a key event to the simulator.
      case action_type_lib.ActionType.KEYDOWN:
        simulator.send_key(action['keycode'].item(0), event_type='keydown')
      case action_type_lib.ActionType.KEYUP:
        simulator.send_key(action['keycode'].item(0), event_type='keyup')
      case action_type_lib.ActionType.KEYPRESS:
        simulator.send_key(action['keycode'].item(0), event_type='keypress')
  except errors.SendActionError:
    logging.exception('Unable to execute action: %r', action)
    return False

  return True


def _prepare_touch_action(
    action: dict[str, np.ndarray],
    screen_width: int,
    screen_height: int,
    num_fingers: int,
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
    A tuple with the format (x: int, y: int, down/up: bool, finger_index: int).
  """

  touch_events = []
  for i, finger_action in enumerate(_split_touch_action(action, num_fingers)):
    is_touch = finger_action['action_type'] == action_type_lib.ActionType.TOUCH
    touch_position = finger_action['touch_position']
    touch_pixels = pixel_fns.touch_position_to_pixel_position(
        touch_position, width_height=(screen_width, screen_height)
    )
    touch_events.append((touch_pixels[0], touch_pixels[1], is_touch, i))
  return touch_events


def _split_touch_action(
    action: dict[str, np.ndarray], num_fingers: int
) -> list[dict[str, np.ndarray]]:
  """Splits a multitouch action into a list of single-touch actions."""

  single_touch_actions = [{
      'action_type': action['action_type'],
      'touch_position': action['touch_position'],
  }]
  for i in range(2, num_fingers + 1):
    single_touch_actions.append({
        'action_type': action[f'action_type_{i}'],
        'touch_position': action[f'touch_position_{i}'],
    })
  return single_touch_actions


def lift_all_fingers_action(num_fingers: int) -> dict[str, np.ndarray]:
  """A lift action with each finger."""

  # There's always at least one finger.
  lift_action = {
      'action_type': np.array(action_type_lib.ActionType.LIFT),
      'touch_position': np.array([0, 0]),
  }
  # Subsequent fingers have separate dict entries.
  for i in range(2, num_fingers + 1):
    lift_action |= {
        f'action_type_{i}': np.array(action_type_lib.ActionType.LIFT),
        f'touch_position_{i}': np.array([0, 0]),
    }
  return lift_action
