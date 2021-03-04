"""Base specs for AndroidEnv."""

from typing import Dict

from android_env.components import action_type
from android_env.proto import task_pb2
import dm_env
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
}


def base_action_spec() -> Dict[str, specs.Array]:
  """Default action spec for AndroidEnv."""

  return {
      'action_type':  # An integer of type ActionType:
          # TOUCH=0, LIFT=1, REPEAT=2
          specs.DiscreteArray(
              num_values=len(action_type.ActionType),
              name='action_type'),
      'touch_position':  # Position [x, y] of the touch action
          # IGNORED when (action_type != ActionType.TOUCH)
          # x, y are float values between 0.0 and 1.0 corresponding
          # to the relative position on the screen
          specs.BoundedArray(
              shape=(2,),
              dtype=np.float32,
              minimum=[0.0, 0.0],
              maximum=[1.0, 1.0],
              name='touch_position'),
  }


def base_observation_spec(
    screen_dimension: np.ndarray) -> Dict[str, specs.Array]:
  """Default observation spec for AndroidEnv."""

  return {
      'pixels':  # The screenshot of the device.
          specs.Array(
              shape=np.append(
                  screen_dimension,  # [H, W]
                  3),  # [R, G, B]
              dtype=np.uint8,
              name='pixels'),
      'timestamp':  # Time delta (in microseconds) since the last observation.
          specs.Array(shape=(), dtype=np.int64, name='timestamp'),
      'orientation':  # The latest orientation in a one-hot representation:
          #   [1, 0, 0, 0]: PORTRAIT  (0 degrees)
          #   [0, 1, 0, 0]: LANDSCAPE (90 degrees clockwise)
          #   [0, 0, 1, 0]: PORTRAIT  (180 degrees) ("upside down")
          #   [0, 0, 0, 1]: LANDSCAPE (270 degrees clockwise)
          specs.Array(shape=np.array([4]), dtype=np.uint8, name='orientation'),
  }


def task_extras_spec(task: task_pb2.Task) -> Dict[str, dm_env.specs.Array]:
  """Task extras spec for AndroidEnv, as read from a task_pb2.Task."""

  return {
      spec.name: _convert_spec(spec)
      for spec in task.extras_spec
  }


def _convert_spec(array_spec: task_pb2.ArraySpec) -> specs.Array:
  """Converts ArraySpec proto to dm_env specs.Array."""

  return specs.Array(
      shape=array_spec.shape,
      dtype=_PROTO_DTYPE_TO_NUMPY_DTYPE[array_spec.dtype],
      name=array_spec.name)
