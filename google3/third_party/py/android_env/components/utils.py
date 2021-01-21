"""Utils for AndroidEnv."""

# copybara:strip_begin
import collections
import importlib
import json
import os
from typing import Any, Dict, List, Sequence, Tuple, Union
# copybara:strip_end_and_replace_begin
# from typing import Sequence, Tuple
# copybara:replace_end

# copybara:strip_begin
from absl import logging
from android_env.proto import task_pb2
from dm_env import specs as dm_env_specs
import funcsigs
import ml_collections
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


# copybara:strip_begin
def transpose_pixels(frame: np.ndarray) -> np.ndarray:
  """Converts image from shape (H, W, C) to (W, H, C) and vice-versa.

  Some software libraries like pygame need the data to be in width-major order.
  This function can be used to convert AndroidEnv observations to this format.

  Args:
    frame: Array representing Android screen.

  Returns:
    Transpose of array representing Android screen.
  """
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


def flatten_dict(dictionary):
  """Flatten a dictionary by joining keys using the character '.'."""
  output_dict = {}
  for key, value in dictionary.items():
    if isinstance(value, dict):
      if value:
        output_dict.update(
            {'{}.{}'.format(key, k): v for k, v in flatten_dict(value).items()})
      else:  # For empty dict values.
        output_dict[key] = value
    else:
      output_dict[key] = value
  return output_dict


def parse_dict(d):
  """Parses string values in a settings dictionary into Python objects."""
  for k, v in d.items():
    d[k] = _str_to_value(v)
  return d


def _str_to_value(v):
  """Converts from a string back to a typed value."""
  if isinstance(v, str):
    if v.lower() == 'true':
      return True
    if v.lower() == 'false':
      return False
    if v.lower() == 'none':
      return None
    if v.isdigit():
      return int(v)
    try:
      return float(v)
    except ValueError:
      pass
  return v


def _listify(
    val: Union[Dict[str, Any], List[Any]]) -> Union[Dict[str, Any], List[Any]]:
  """Converts dicts with purely numeric keys into lists."""
  if isinstance(val, dict) and val:
    if all(k.isdigit() for k in val):
      return [
          _listify(v)
          for _, v in sorted(val.items(), key=lambda k__: int(k__[0]))
      ]
    else:
      return {k: _listify(v) for k, v in val.items()}
  return val


def _unflatten_dict(flat_args: Dict[str, str]) -> Dict[str, Any]:
  """Unflattens dict, does the reverse of `flatten_dict`."""

  args_out = {}
  for k, v in flat_args.items():
    out = args_out
    parts = k.split('.')
    for p in parts[:-1]:
      out = out.setdefault(p, {})
    new_v = _str_to_value(v)
    out[parts[-1]] = new_v
  out_dict = _listify(args_out)
  assert isinstance(out_dict, dict)
  return out_dict


def expand_vars(dictionary: Dict[Any, Any]) -> Dict[Any, Any]:
  """Recursively expands environment variables in string values."""
  for key in dictionary:
    value = dictionary[key]
    if isinstance(value, str):
      dictionary[key] = os.path.expandvars(value)
    elif isinstance(value, dict):
      dictionary[key] = expand_vars(value)
  return dictionary


def merge_settings(default_config: ml_collections.ConfigDict,
                   settings: Dict[str, str]) -> Dict[str, Any]:
  """Merges a default config dict with a flattenned settings string dict."""
  # The json encode/decode converts tuples to lists to remove type ambiguity.
  config = json.loads(json.dumps(default_config.to_dict()))
  dict_settings = _unflatten_dict(settings)

  def update(d, u):
    for k, v in u.items():
      if isinstance(v, collections.Mapping):
        d[k] = update(d.get(k, {}), v)
      else:
        d[k] = v
    return d

  return update(config, dict_settings)


def is_bounded(spec):
  return isinstance(spec, dm_env_specs.BoundedArray)


def is_discrete(spec):
  return isinstance(spec, dm_env_specs.DiscreteArray)


def update_spec_name(spec, name):
  """Returns a copy of the given spec with the new name."""
  if is_discrete(spec):
    return dm_env_specs.DiscreteArray(
        num_values=spec.num_values, dtype=spec.dtype, name=name)
  if is_bounded(spec):
    return dm_env_specs.BoundedArray(
        shape=spec.shape,
        dtype=spec.dtype,
        minimum=spec.minimum,
        maximum=spec.maximum,
        name=name)
  return dm_env_specs.Array(shape=spec.shape, dtype=spec.dtype, name=name)


def update_spec_dtype(spec, dtype):
  """Returns a copy of the given spec with the new dtype."""
  if is_discrete(spec):
    return dm_env_specs.DiscreteArray(
        num_values=spec.num_values, dtype=dtype, name=spec.name)
  if is_bounded(spec):
    return dm_env_specs.BoundedArray(
        shape=spec.shape,
        dtype=dtype,
        minimum=spec.minimum,
        maximum=spec.maximum,
        name=spec.name)
  return dm_env_specs.Array(shape=spec.shape, dtype=dtype, name=spec.name)


def maybe_convert_to_discrete(spec):
  """Converts `spec` to a a DiscreteArray if it has the right properties."""
  if is_discrete(spec):
    return spec
  if is_bounded(spec) and spec.dtype == np.int32:
    if not spec.shape and spec.minimum == 0:
      return dm_env_specs.DiscreteArray(
          num_values=spec.maximum + 1, dtype=np.int32, name=spec.name)
    elif spec.shape == (1,) and spec.minimum == [0]:
      return dm_env_specs.DiscreteArray(
          num_values=spec.maximum[0] + 1, dtype=np.int32, name=spec.name)
  return spec


def maybe_convert_discrete(spec):
  """Converts `spec` to shape (1,) if it is scalar."""
  if is_discrete(spec):
    return dm_env_specs.BoundedArray(
        shape=(1,),
        dtype=spec.dtype,
        minimum=[spec.minimum],
        maximum=[spec.maximum],
        name=spec.name)
  return spec


def get_empty_dict_from_spec(
    specs: Dict[str, dm_env_specs.Array]) -> Dict[str, np.ndarray]:
  """Creates a dictionary of np.zeros() values for each spec in `specs`."""
  return {
      name: np.zeros(spec.shape, dtype=spec.dtype)
      for name, spec in specs.items()
  }


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
