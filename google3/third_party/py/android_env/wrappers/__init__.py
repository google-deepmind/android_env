"""Init file for android_env.wrappers package."""

from android_env.wrappers import discrete_action_wrapper
from android_env.wrappers import flat_interface_wrapper
from android_env.wrappers import float_pixels_wrapper
from android_env.wrappers import image_rescale_wrapper

DiscreteActionWrapper = discrete_action_wrapper.DiscreteActionWrapper
FlatInterfaceWrapper = flat_interface_wrapper.FlatInterfaceWrapper
FloatPixelsWrapper = float_pixels_wrapper.FloatPixelsWrapper
ImageRescaleWrapper = image_rescale_wrapper.ImageRescaleWrapper
