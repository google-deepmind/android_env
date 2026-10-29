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

"""Tests for action mapping and coalescing in AndroidEnv Playground."""

from absl.testing import absltest
from absl.testing import parameterized
from android_env.playground import actions as actions_lib
from android_env.proto import device_env_service_pb2
import numpy as np


class ActionsTest(parameterized.TestCase):

  def test_coalesce_actions_empty(self):
    self.assertEqual(actions_lib.coalesce_actions([]), [])

  def test_coalesce_actions_single(self):
    action = actions_lib.ClientAction(
        action_type='touch_down',
        x=0.1,
        y=0.2,
        client_timestamp_ms=1000.0,
        recv_timestamp_ms=1001.0,
    )
    self.assertEqual(actions_lib.coalesce_actions([action]), [action])

  def test_coalesce_actions_compress_moves(self):
    actions = [
        actions_lib.ClientAction(
            action_type='touch_down',
            x=0.1,
            y=0.2,
            client_timestamp_ms=1000.0,
            recv_timestamp_ms=1001.0,
        ),
        actions_lib.ClientAction(
            action_type='touch_move',
            x=0.15,
            y=0.25,
            client_timestamp_ms=1016.0,
            recv_timestamp_ms=1017.0,
        ),
        actions_lib.ClientAction(
            action_type='touch_move',
            x=0.2,
            y=0.3,
            client_timestamp_ms=1032.0,
            recv_timestamp_ms=1033.0,
        ),
        actions_lib.ClientAction(
            action_type='touch_up',
            x=0.2,
            y=0.3,
            client_timestamp_ms=1048.0,
            recv_timestamp_ms=1049.0,
        ),
    ]
    expected = [
        actions[0],
        actions[2],
        actions[3],
    ]
    self.assertEqual(actions_lib.coalesce_actions(actions), expected)

  @parameterized.parameters(
      (
          'touch_down',
          [0.1, 0.2],
          None,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN,
      ),
      (
          'touch_move',
          [0.3, 0.4],
          None,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_TOUCH_MOVE,
      ),
      (
          'touch_up',
          [0.5, 0.6],
          None,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_TOUCH_UP,
      ),
      (
          'keydown',
          None,
          66,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_KEY_EVENT,
      ),
      (
          'text',
          None,
          None,
          'hello',
          None,
          device_env_service_pb2.ACTION_TYPE_SET_TEXT,
      ),
      (
          'set_selection',
          None,
          None,
          None,
          (1, 4),
          device_env_service_pb2.ACTION_TYPE_SET_SELECTION,
      ),
      (
          'cut',
          None,
          None,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_CUT,
      ),
      (
          'copy',
          None,
          None,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_COPY,
      ),
      (
          'paste',
          None,
          None,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_PASTE,
      ),
      (
          'unsupported_unknown',
          None,
          None,
          None,
          None,
          device_env_service_pb2.ACTION_TYPE_UNSPECIFIED,
      ),
  )
  def test_map_client_action_to_proto(
      self,
      act_type,
      pos_list,
      keycode,
      text,
      selection,
      expected_proto_type,
  ):
    client_action = actions_lib.ClientAction(
        action_type=act_type,
        x=0.1,
        y=0.2,
        client_timestamp_ms=100.0,
        recv_timestamp_ms=102.0,
        keycode=keycode,
        text=text,
        selection=selection,
    )
    pos = np.array(pos_list, dtype=np.float32) if pos_list else None
    proto = actions_lib.map_client_action_to_proto(client_action, pos)

    self.assertEqual(proto.action_type, expected_proto_type)
    if pos_list:
      self.assertAlmostEqual(proto.touch_position.x, pos_list[0])
      self.assertAlmostEqual(proto.touch_position.y, pos_list[1])
    if keycode is not None:
      self.assertEqual(proto.keycode, keycode)
    if text is not None:
      self.assertEqual(proto.text, text)
    if selection is not None:
      self.assertEqual(proto.selection_start, selection[0])
      self.assertEqual(proto.selection_end, selection[1])


if __name__ == '__main__':
  absltest.main()
