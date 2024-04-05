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

"""The different kinds of actions that AndroidEnv supports.

The native action space of AndroidEnv consists of a tuple consisting of
- A position (x, y) ∈ [0, 1] x [0, 1], determining the location of the action on
  the screen, and
- A discrete value, indicating the action type, which is in this file.

See https://arxiv.org/abs/2105.13231, section 2.2 for details.
"""

import enum


@enum.unique
class ActionType(enum.IntEnum):
  """Integer values to describe each supported action in AndroidEnv.

  Note for KEY* types:
  - Only meaningful if connected to a _physical_ keyboard, _not_ virtual
    keyboard.
  - Added afterwards so they did not appear in the paper.

  Attributes:
    TOUCH: Touching the screen at a location.
    LIFE: Lifting the (imaginary) pointer from the screen at a location.
    REPEAT: Repeating the last chosen action.
    KEYDOWN: Sending a key down event.
    KEYUP: Sending a key up event.
    KEYPRESS: Sending a key down event, immediately followed by a key up event.
  """

  TOUCH = 0
  LIFT = 1
  REPEAT = 2
  KEYDOWN = 3
  KEYUP = 4
  KEYPRESS = 5
