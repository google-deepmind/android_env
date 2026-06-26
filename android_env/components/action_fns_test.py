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

import timeit
from unittest import mock

from absl import flags
from absl.testing import absltest
from absl.testing import parameterized
from android_env.components import action_fns
from android_env.components import action_type as action_type_lib
from android_env.components import errors
from android_env.components import pixel_fns
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
        'action_type': np.array(action_type_lib.ActionType.TOUCH),
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
        'action_type': np.array(action_type_lib.ActionType.TOUCH),
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
        'action_type': np.array(action_type_lib.ActionType.TOUCH),
        'touch_position': np.array([0.2, 0.5], np.float32),
        'action_type_2': np.array(action_type_lib.ActionType.LIFT),
        'touch_position_2': np.array([0.1, 0.2], np.float32),
        'action_type_3': np.array(action_type_lib.ActionType.TOUCH),
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

  @parameterized.named_parameters(
      ('keydown', action_type_lib.ActionType.KEYDOWN, 21, 'keydown'),
      ('keyup', action_type_lib.ActionType.KEYUP, 42, 'keyup'),
      ('keypress', action_type_lib.ActionType.KEYPRESS, 96, 'keypress'),
  )
  def test_send_action_to_simulator_key_event_success(
      self, action_type, keycode, event_type
  ):

    # Arrange.
    simulator = mock.create_autospec(base_simulator.BaseSimulator)
    action = {
        'action_type': np.array(action_type),
        'keycode': np.array([keycode], np.int32),
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
    simulator.send_key.assert_called_once_with(keycode, event_type=event_type)

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


_RUN_BENCHMARKS = flags.DEFINE_bool(
    'run_benchmarks', False, 'Whether to run microbenchmarks.'
)


def _old_split_touch_action(action, num_fingers):
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


def _old_prepare_touch_action(action, screen_width, screen_height, num_fingers):
  touch_events = []
  for i, finger_action in enumerate(
      _old_split_touch_action(action, num_fingers)
  ):
    is_touch = finger_action['action_type'] == action_type_lib.ActionType.TOUCH
    touch_position = finger_action['touch_position']
    touch_pixels = pixel_fns.touch_position_to_pixel_position(
        touch_position, width_height=(screen_width, screen_height)
    )
    touch_events.append((touch_pixels[0], touch_pixels[1], is_touch, i))
  return touch_events


_BENCHMARK_ACTION_1F = {
    'action_type': np.array(action_type_lib.ActionType.TOUCH),
    'touch_position': np.array([0.2, 0.5], np.float32),
}

_BENCHMARK_ACTION_3F = {
    'action_type': np.array(action_type_lib.ActionType.TOUCH),
    'touch_position': np.array([0.2, 0.5], np.float32),
    'action_type_2': np.array(action_type_lib.ActionType.LIFT),
    'touch_position_2': np.array([0.1, 0.2], np.float32),
    'action_type_3': np.array(action_type_lib.ActionType.TOUCH),
    'touch_position_3': np.array([0.5, 0.2], np.float32),
}


class ActionFnsBenchmark(parameterized.TestCase):

  def test_prepare_touch_action(self):
    if not _RUN_BENCHMARKS.value:
      self.skipTest('Benchmark disabled')

    number = 100000

    # 1 finger
    t_old_1 = timeit.Timer(
        '_old_prepare_touch_action(_BENCHMARK_ACTION_1F, 800, 600, 1)',
        globals=globals(),
    )
    res_old_1 = t_old_1.timeit(number=number)
    print(
        f'BenchmarkPrepareTouchAction_1f_Old {number}'
        f' {res_old_1 / number * 1e9:.0f} ns/op'
    )

    t_new_1 = timeit.Timer(
        'action_fns._prepare_touch_action(_BENCHMARK_ACTION_1F, 800, 600, 1)',
        globals=globals(),
    )
    res_new_1 = t_new_1.timeit(number=number)
    print(
        f'BenchmarkPrepareTouchAction_1f_New {number}'
        f' {res_new_1 / number * 1e9:.0f} ns/op'
    )

    # 3 fingers
    t_old_3 = timeit.Timer(
        '_old_prepare_touch_action(_BENCHMARK_ACTION_3F, 800, 600, 3)',
        globals=globals(),
    )
    res_old_3 = t_old_3.timeit(number=number)
    print(
        f'BenchmarkPrepareTouchAction_3f_Old {number}'
        f' {res_old_3 / number * 1e9:.0f} ns/op'
    )

    t_new_3 = timeit.Timer(
        'action_fns._prepare_touch_action(_BENCHMARK_ACTION_3F, 800, 600, 3)',
        globals=globals(),
    )
    res_new_3 = t_new_3.timeit(number=number)
    print(
        f'BenchmarkPrepareTouchAction_3f_New {number}'
        f' {res_new_3 / number * 1e9:.0f} ns/op'
    )


if __name__ == '__main__':
  absltest.main()
