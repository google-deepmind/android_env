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

"""Action mapping functions for AndroidEnv Playground."""

import dataclasses
from android_env.proto import device_env_service_pb2
import numpy as np


@dataclasses.dataclass(frozen=True)
class ClientAction:
  """Represents an action received from the playground client.

  Attributes:
    action_type: The type of action (e.g. 'touch_down', 'touch_move',
      'touch_up', 'text', 'keydown').
    x: Normalized X coordinate (0.0 to 1.0).
    y: Normalized Y coordinate (0.0 to 1.0).
    client_timestamp_ms: Timestamp in milliseconds when the action was generated
      on the client.
    recv_timestamp_ms: Timestamp in milliseconds when the action was received by
      the server.
    text: Optional text to type for 'text' action_type.
    keycode: Optional integer Android keycode for 'keydown' action_type.
    selection: Optional tuple (start, end) for 'set_selection' action_type.
  """

  action_type: str
  x: float
  y: float
  client_timestamp_ms: float
  recv_timestamp_ms: float
  text: str | None = None
  keycode: int | None = None
  selection: tuple[int, int] | None = None


def coalesce_actions(actions: list[ClientAction]) -> list[ClientAction]:
  """Coalesces consecutive touch_move actions in a list, preserving timestamps."""
  if not actions:
    return []
  compressed = []
  for act in actions:
    if not compressed:
      compressed.append(act)
      continue

    prev_act = compressed[-1]
    if prev_act.action_type == 'touch_move' and act.action_type == 'touch_move':
      compressed[-1] = act
    else:
      compressed.append(act)
  return compressed


def map_client_action_to_proto(
    act: ClientAction, pos: np.ndarray | None = None
) -> device_env_service_pb2.Action:
  """Maps a ClientAction directly to an AndroidEnv protobuf Action."""
  proto_action = device_env_service_pb2.Action()
  match act.action_type:
    case 'touch_down':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN
      if pos is not None:
        proto_action.touch_position.x = float(pos[0])
        proto_action.touch_position.y = float(pos[1])
    case 'touch_move':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE
      if pos is not None:
        proto_action.touch_position.x = float(pos[0])
        proto_action.touch_position.y = float(pos[1])
    case 'touch_up':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_TOUCH_UP
      if pos is not None:
        proto_action.touch_position.x = float(pos[0])
        proto_action.touch_position.y = float(pos[1])
    case 'keydown':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_KEY_EVENT
      if act.keycode is not None:
        proto_action.keycode = int(act.keycode)
    case 'text':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_SET_TEXT
      if act.text is not None:
        proto_action.text = str(act.text)
    case 'set_selection':
      proto_action.action_type = (
          device_env_service_pb2.ACTION_TYPE_SET_SELECTION
      )
      if act.selection is not None:
        proto_action.selection_start = int(act.selection[0])
        proto_action.selection_end = int(act.selection[1])
    case 'cut':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_CUT
    case 'copy':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_COPY
    case 'paste':
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_PASTE
    case _:
      proto_action.action_type = device_env_service_pb2.ACTION_TYPE_UNSPECIFIED
  return proto_action
