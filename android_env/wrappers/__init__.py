# coding=utf-8
# Copyright 2021 DeepMind Technologies Limited.
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

"""Init file for android_env.wrappers package."""

from android_env.wrappers import discrete_action_wrapper
from android_env.wrappers import flat_interface_wrapper
from android_env.wrappers import float_pixels_wrapper
from android_env.wrappers import image_rescale_wrapper

DiscreteActionWrapper = discrete_action_wrapper.DiscreteActionWrapper
FlatInterfaceWrapper = flat_interface_wrapper.FlatInterfaceWrapper
FloatPixelsWrapper = float_pixels_wrapper.FloatPixelsWrapper
ImageRescaleWrapper = image_rescale_wrapper.ImageRescaleWrapper
