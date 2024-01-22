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

"""Base specs for AndroidEnv."""

from android_env.components import action_type
from android_env.proto import task_pb2
from dm_env import specs
import numpy as np


_PROTO_DTYPE_TO_NUMPY_DTYPE = {
    task_pb2.ArraySpec.DataType.FLOAT: np.float32,
    task_pb2.ArraySpec.DataType.DOUBLE: np.float64,
    task_pb2.ArraySpec.DataType.INT8: np.int8,
    task_pb2.ArraySpec.DataType.INT16: np.int16,
    task_pb2.ArraySpec.DataType.INT32: np.int32,
    task_pb2.ArraySpec.DataType.INT64: np.int64,
    task_pb2.ArraySpec.DataType.UINT8: np.uint8,
    task_pb2.ArraySpec.DataType.UINT16: np.uint16,
    task_pb2.ArraySpec.DataType.UINT32: np.uint32,
    task_pb2.ArraySpec.DataType.UINT64: np.uint64,
    task_pb2.ArraySpec.DataType.BOOL: np.bool_,
    task_pb2.ArraySpec.DataType.STRING_U1: np.dtype(('U1')),
    task_pb2.ArraySpec.DataType.STRING_U16: np.dtype(('<U16')),
    task_pb2.ArraySpec.DataType.STRING_U25: np.dtype(('<U25')),
    task_pb2.ArraySpec.DataType.STRING_U250: np.dtype(('<U250')),
    task_pb2.ArraySpec.DataType.STRING: np.dtype(('<U0')),
    task_pb2.ArraySpec.DataType.OBJECT: np.dtype('O'),
}


def base_action_spec(
    num_fingers: int = 1, enable_key_events: bool = False
) -> dict[str, specs.Array]:
  """Default action spec for AndroidEnv.

  Args:
    num_fingers: Number of virtual fingers of the agent.
    enable_key_events: Whether keyboard key events are enabled.

  Returns:
    A dict of action specs, each item corresponding to a virtual finger.
    action_type: An integer of type ActionType: TOUCH=0, LIFT=1, REPEAT=2
    touch_position: Position [x, y] of the touch action, where x, y are float
      values between 0.0 and 1.0 corresponding to the relative position on the
      screen. IGNORED when (action_type != ActionType.TOUCH).
    keycode: code representing the desired key press in XKB format. See the
      emulator_controller_pb2 for details.
    action_type_i: Action type for additional fingers (i>1).
    touch_position_i: Touch position for additional fingers (i>1).
  """

  num_actions = len(action_type.ActionType) if enable_key_events else 3

  action_spec = {
      'action_type':
          specs.DiscreteArray(num_values=num_actions, name='action_type'),
      'touch_position':
          specs.BoundedArray(
              shape=(2,),
              dtype=np.float32,
              minimum=[0.0, 0.0],
              maximum=[1.0, 1.0],
              name='touch_position'),
  }

  for i in range(2, num_fingers + 1):
    action_spec.update({
        f'action_type_{i}':
            specs.DiscreteArray(
                num_values=len(action_type.ActionType),
                name=f'action_type_{i}'),
        f'touch_position_{i}':
            specs.BoundedArray(
                shape=(2,),
                dtype=np.float32,
                minimum=[0.0, 0.0],
                maximum=[1.0, 1.0],
                name=f'touch_position_{i}'),
    })

  if enable_key_events:
    action_spec['keycode'] = specs.DiscreteArray(
        num_values=(1 << 16) - 1, name='keycode')

  return action_spec


def base_observation_spec(height: int, width: int) -> dict[str, specs.Array]:
  """Default observation spec for AndroidEnv.

  Args:
    height: Height of the device screen in pixels.
    width: Width of the device screen in pixels.

  Returns:
    pixels: Spec for the RGB screenshot of the device. Has shape (H, W, 3)
    timedelta: Spec for time delta since the last observation (in microseconds).
        The first timestep immediately after reset() will have this value set to
        0.
    orientation: Spec for the latest orientation in a one-hot representation:
        [1, 0, 0, 0]: PORTRAIT  (0 degrees)
        [0, 1, 0, 0]: LANDSCAPE (90 degrees clockwise)
        [0, 0, 1, 0]: PORTRAIT  (180 degrees) ("upside down")
        [0, 0, 0, 1]: LANDSCAPE (270 degrees clockwise)
  """

  return {
      'pixels':
          specs.BoundedArray(
              shape=(height, width, 3),
              dtype=np.uint8,
              name='pixels',
              minimum=0,
              maximum=255),
      'timedelta':
          specs.Array(shape=(), dtype=np.int64, name='timedelta'),
      'orientation':
          specs.BoundedArray(
              shape=np.array([4]),
              dtype=np.uint8,
              name='orientation',
              minimum=0,
              maximum=1),
  }
