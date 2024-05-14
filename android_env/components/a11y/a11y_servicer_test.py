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

"""Tests for a11y_servicer."""

import asyncio
from collections.abc import AsyncIterator, Iterable
from typing import TypeVar
from unittest import IsolatedAsyncioTestCase, mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.components.a11y import a11y_servicer
from android_env.proto.a11y import a11y_pb2
from android_env.proto.a11y import android_accessibility_forest_pb2
import grpc


_T = TypeVar('_T')


async def _aiter(xs: Iterable[_T]) -> AsyncIterator[_T]:
  """Utility to make an AsyncIterator from Iterable."""

  for x in xs:
    yield x


def one_window_one_node_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  window = forest.windows.add()
  node = window.tree.nodes.add()
  node.class_name = 'foo'
  node.is_clickable = True
  node.hint_text = 'Foo hint'
  return forest


def one_window_two_nodes_forest() -> (
    android_accessibility_forest_pb2.AndroidAccessibilityForest
):
  forest = android_accessibility_forest_pb2.AndroidAccessibilityForest()
  window = forest.windows.add()
  node = window.tree.nodes.add()
  node.class_name = 'bar'
  node.is_clickable = True
  node.hint_text = 'Bar hint'
  node = window.tree.nodes.add()
  node.class_name = 'bar'
  node.is_clickable = False
  node.hint_text = 'Bar hint 2'
  return forest


def empty_dict() -> dict[str, str]:
  return {}


def single_item_dict_with_special_chars() -> dict[str, str]:
  return {'foo': 'bar\r\t\nbaz'}


class A11yServicerTest(parameterized.TestCase, IsolatedAsyncioTestCase):

  def test_servicer_sendforest(self):
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    servicer = a11y_servicer.A11yServicer()
    servicer.resume()
    response = servicer.SendForest(one_window_one_node_forest(), mock_context)
    self.assertEqual(response.error, '')
    response = servicer.SendForest(one_window_two_nodes_forest(), mock_context)
    self.assertEqual(response.error, '')
    forests = servicer.gather_forests()
    self.assertLen(forests, 2)
    self.assertEqual(forests[0], one_window_one_node_forest())
    self.assertEqual(forests[1], one_window_two_nodes_forest())

  async def test_servicer_bidi_forests(self):
    """Checks that the bidirectional interface accepts forests."""

    # Arrange.
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    servicer = a11y_servicer.A11yServicer()

    # Act.
    servicer.resume()
    responses = [
        x
        async for x in servicer.Bidi(
            _aiter([
                a11y_pb2.ClientToServer(
                    event=a11y_pb2.EventRequest(
                        event=single_item_dict_with_special_chars()
                    )
                ),
                a11y_pb2.ClientToServer(forest=one_window_two_nodes_forest()),
            ]),
            mock_context,
        )
    ]
    forest = await servicer.get_forest()

    # Assert.
    self.assertEqual(responses[0], a11y_pb2.ServerToClient())
    self.assertEqual(responses[1], a11y_pb2.ServerToClient())
    self.assertIsNotNone(forest)
    self.assertEqual(forest, one_window_two_nodes_forest())

  def test_servicer_sendforest_latest_only(self):
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    servicer = a11y_servicer.A11yServicer(latest_forest_only=True)
    servicer.resume()
    response = servicer.SendForest(one_window_one_node_forest(), mock_context)
    self.assertEqual(response.error, '')
    response = servicer.SendForest(one_window_two_nodes_forest(), mock_context)
    self.assertEqual(response.error, '')
    forests = servicer.gather_forests()
    self.assertLen(forests, 1)
    self.assertEqual(forests[0], one_window_two_nodes_forest())

  def test_servicer_sendevent(self):
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    servicer = a11y_servicer.A11yServicer()
    servicer.resume()
    response = servicer.SendEvent(
        a11y_pb2.EventRequest(event=empty_dict()), mock_context
    )
    self.assertEqual(response.error, '')
    response = servicer.SendEvent(
        a11y_pb2.EventRequest(event=single_item_dict_with_special_chars()),
        mock_context,
    )
    self.assertEqual(response.error, '')
    events = servicer.gather_events()
    self.assertLen(events, 2)
    self.assertEqual(events[0].event, empty_dict())
    self.assertEqual(events[1].event, single_item_dict_with_special_chars())

  async def test_servicer_bidi_events(self):
    """Checks that the bidirectional interface accepts events."""

    # Arrange.
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    servicer = a11y_servicer.A11yServicer()

    # Act.
    servicer.resume()
    responses = [
        x
        async for x in servicer.Bidi(
            _aiter([
                a11y_pb2.ClientToServer(
                    event=a11y_pb2.EventRequest(event=empty_dict())
                ),
                a11y_pb2.ClientToServer(
                    event=a11y_pb2.EventRequest(
                        event=single_item_dict_with_special_chars()
                    )
                ),
            ]),
            mock_context,
        )
    ]
    events = servicer.gather_events()

    # Assert.
    self.assertEqual(responses[0], a11y_pb2.ServerToClient())
    self.assertEqual(responses[1], a11y_pb2.ServerToClient())
    self.assertLen(events, 2)
    self.assertEqual(events[0].event, empty_dict())
    self.assertEqual(events[1].event, single_item_dict_with_special_chars())

  def test_servicer_pause_and_clear_pauses(self):
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    servicer = a11y_servicer.A11yServicer()
    servicer.resume()
    servicer.pause_and_clear()
    response = servicer.SendEvent(
        a11y_pb2.EventRequest(event=empty_dict()), mock_context
    )
    self.assertEqual(response.error, '')
    response = servicer.SendForest(one_window_one_node_forest(), mock_context)
    self.assertEqual(response.error, '')
    events = servicer.gather_events()
    self.assertEmpty(events)
    forests = servicer.gather_forests()
    self.assertEmpty(forests)

  def test_servicer_pause_and_clear_clears(self):
    mock_context = mock.create_autospec(grpc.ServicerContext, instance=True)
    servicer = a11y_servicer.A11yServicer()
    servicer.resume()
    response = servicer.SendEvent(
        a11y_pb2.EventRequest(event=empty_dict()), mock_context
    )
    self.assertEqual(response.error, '')
    response = servicer.SendForest(one_window_one_node_forest(), mock_context)
    self.assertEqual(
        response.error,
        '',
    )
    servicer.pause_and_clear()
    events = servicer.gather_events()
    self.assertEmpty(events)
    forests = servicer.gather_forests()
    self.assertEmpty(forests)


if __name__ == '__main__':
  absltest.main()
