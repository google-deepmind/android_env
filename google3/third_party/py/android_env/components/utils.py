"""Utils for AndroidEnv."""

# copybara:strip_begin
import importlib
from typing import Any, Dict, Sequence, Tuple
# copybara:strip_end_and_replace_begin
# from typing import Sequence, Tuple
# copybara:replace_end


from absl import logging  # copybara:strip
from android_env.proto import task_pb2
# copybara:strip_begin
from dm_env import specs as dm_env_specs
import funcsigs
# copybara:strip_end
import numpy as np


def touch_position_to_pixel_position(
    touch_position: np.ndarray,
    width_height: Sequence[int],
) -> Tuple[int, int]:
  """Maps touch position in [0,1] to the corresponding pixel on the screen."""
  touch_pixels = (touch_position * width_height).astype(np.int32)
  cap_idx = lambda v, idx_len: min(v, idx_len - 1)
  return tuple(map(cap_idx, touch_pixels, width_height))


def transpose_pixels(frame: np.ndarray) -> np.ndarray:
  """Converts image from shape (H, W, C) to (W, H, C) and vice-versa."""
  return np.transpose(frame, axes=(1, 0, 2))


def orient_pixels(
    frame: np.ndarray,
    orientation: task_pb2.AdbCall.Rotate.Orientation) -> np.ndarray:
  """Rotates screen pixels according to the given orientation."""
  if orientation == task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_90:
    frame = np.rot90(frame, k=3, axes=(0, 1))
  elif orientation == task_pb2.AdbCall.Rotate.Orientation.PORTRAIT_180:
    frame = np.rot90(frame, k=2, axes=(0, 1))
  elif orientation == task_pb2.AdbCall.Rotate.Orientation.LANDSCAPE_270:
    frame = np.rot90(frame, k=1, axes=(0, 1))
  return frame


# copybara:strip_begin
def instantiate_class(full_class_name: str, **kwargs):
  """Imports the class defined by `full_class_name` and instantiate it.

  Args:
    full_class_name: The fully-qualified class name such as
      'my_package.my_module.MyClass'. It must not be empty and it should have at
      least one '.' in its name. It should also point to a valid class name.
    **kwargs: Arguments to be passed to the init of the class to be
      instantiated.

  Returns:
    An object of the type specified by `full_class_name`.
  """
  mod_name, class_name = full_class_name.rsplit('.', 1)
  logging.info('mod_name: %s', mod_name)
  logging.info('class_name: %s', class_name)
  module = importlib.import_module(mod_name)
  imported_class = getattr(module, class_name)
  return imported_class(**kwargs)


def get_class_default_params(class_object) -> Dict[str, Any]:
  """Returns a dictionary of a class parameters that have a default value.

  Parameters with no default value are ignored.
  Args:
    class_object: An uninstantiated class.
  """
  return dict([(k, v.default)
               for k, v in funcsigs.signature(class_object).parameters.items()
               if v.default is not funcsigs.Parameter.empty])


def convert_int_to_float(data: np.ndarray,
                         data_spec: dm_env_specs.Array,
                         float_type: np.dtype = np.float32):
  """Converts an array of int values to floats between 0 and 1."""
  if not np.issubdtype(data.dtype, np.integer):
    raise TypeError(f'{data.dtype} is not an integer type')
  if not np.issubdtype(float_type, np.floating):
    raise TypeError(f'{float_type} is not a floating-point type')
  if isinstance(data_spec, dm_env_specs.BoundedArray):
    value_min = data_spec.minimum
    value_max = data_spec.maximum
  else:
    # We use the int type to figure out the boundaries.
    iinfo = np.iinfo(data_spec.dtype)
    value_min = iinfo.min
    value_max = iinfo.max
  return float_type(1.0 * (data - value_min) / (value_max - value_min))
# copybara:strip_end
