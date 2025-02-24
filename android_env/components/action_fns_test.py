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

from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import action_fns
from android_env.components import action_type as action_type_lib
from android_env.components import errors
from android_env.components.simulators import base_simulator
import numpy as np


class ActionFnsTest(parameterized.TestCase):

  def test_send_action_to_simulator_missing_action_type(self):
    """A `KeyError` should be raised if the action is missing "action_type"."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    action = {'some_key': np.array(123, np.int32)}

    # Act & Assert.
    self.assertRaises(
        KeyError,
        action_fns.send_action_to_simulator,
        action,
        simulator,
        800,
        600,
        1,
    )

  def test_send_action_to_simulator_sendactionerror(self):
    """Returns `False` if the simulator raises a SendActionError."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    simulator.send_touch.side_effect = errors.SendActionError('oops!')
    action = {
        'action_type': action_type_lib.ActionType.TOUCH,
        'touch_position': np.array([0.3, 0.5], np.float32),
    }

    # Act.
    output = action_fns.send_action_to_simulator(
        action,
        simulator,
        800,
        600,
        1,
    )

    # Assert.
    self.assertFalse(output)
    simulator.send_touch.assert_called_once()

  def test_send_action_to_simulator_touch_success_one_finger(self):
    """Returns `True` with a proper 1-finger touch action."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    action = {
        'action_type': action_type_lib.ActionType.TOUCH,
        'touch_position': np.array([0.2, 0.5], np.float32),
    }

    # Act.
    output = action_fns.send_action_to_simulator(
        action,
        simulator,
        800,
        600,
        1,
    )

    # Assert.
    self.assertTrue(output)
    simulator.send_touch.assert_called_once_with(
        [(np.int32(160), np.int32(300), True, 0)]
    )

  def test_send_action_to_simulator_touch_success_multiple_finger(self):
    """Returns `True` with a proper 3-finger touch action."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    action = {
        'action_type': action_type_lib.ActionType.TOUCH,
        'touch_position': np.array([0.2, 0.5], np.float32),
        'action_type_2': action_type_lib.ActionType.LIFT,
        'touch_position_2': np.array([0.1, 0.2], np.float32),
        'action_type_3': action_type_lib.ActionType.TOUCH,
        'touch_position_3': np.array([0.5, 0.2], np.float32),
    }

    # Act.
    output = action_fns.send_action_to_simulator(
        action,
        simulator,
        800,
        600,
        3,
    )

    # Assert.
    self.assertTrue(output)
    simulator.send_touch.assert_called_once_with([
        (np.int32(160), np.int32(300), True, 0),
        (np.int32(80), np.int32(120), False, 1),
        (np.int32(400), np.int32(120), True, 2),
    ])

  def test_send_action_to_simulator_keydown_success(self):
    """Returns `True` with a proper keydown action."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    action = {
        'action_type': action_type_lib.ActionType.KEYDOWN,
        'keycode': np.array([21], np.int32),
    }

    # Act.
    output = action_fns.send_action_to_simulator(
        action,
        simulator,
        800,
        600,
        1,
    )

    # Assert.
    self.assertTrue(output)
    simulator.send_key.assert_called_once_with(21, event_type='keydown')

  def test_send_action_to_simulator_keyup_success(self):
    """Returns `True` with a proper keyup action."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    action = {
        'action_type': action_type_lib.ActionType.KEYUP,
        'keycode': np.array([42], np.int32),
    }

    # Act.
    output = action_fns.send_action_to_simulator(
        action,
        simulator,
        800,
        600,
        1,
    )

    # Assert.
    self.assertTrue(output)
    simulator.send_key.assert_called_once_with(42, event_type='keyup')

  def test_send_action_to_simulator_keypress_success(self):
    """Returns `True` with a proper keypress action."""

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    action = {
        'action_type': action_type_lib.ActionType.KEYPRESS,
        'keycode': np.array([96], np.int32),
    }

    # Act.
    output = action_fns.send_action_to_simulator(
        action,
        simulator,
        800,
        600,
        1,
    )

    # Assert.
    self.assertTrue(output)
    simulator.send_key.assert_called_once_with(96, event_type='keypress')

  @parameterized.named_parameters(
      (
          'one_finger',
          1,
          {
              'action_type': np.array(action_type_lib.ActionType.LIFT),
              'touch_position': np.array([0, 0]),
          },
      ),
      (
          'two_fingers',
          2,
          {
              'action_type': np.array(action_type_lib.ActionType.LIFT),
              'touch_position': np.array([0, 0]),
              'action_type_2': np.array(action_type_lib.ActionType.LIFT),
              'touch_position_2': np.array([0, 0]),
          },
      ),
  )
  def test_lift_all_fingers_action(
      self, num_fingers: int, expected_action: dict[str, np.ndarray]
  ):
    """Returns the expected action."""

    output = action_fns.lift_all_fingers_action(num_fingers)
    for k, v in expected_action.items():
      np.testing.assert_array_equal(v, output[k])


if __name__ == '__main__':
  absltest.main()
