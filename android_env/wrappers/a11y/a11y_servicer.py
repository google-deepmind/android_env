# coding=utf-8
# Copyright 2025 DeepMind Technologies Limited.
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

"""Accessibility Servicer implementation."""

import asyncio
from collections.abc import AsyncIterator, Generator, Iterable
import threading

from absl import logging
from android_env.proto.a11y import a11y_pb2
from android_env.proto.a11y import a11y_pb2_grpc
from android_env.proto.a11y import android_accessibility_forest_pb2
import grpc


class A11yServicer(a11y_pb2_grpc.A11yServiceServicer):
  """Services the A11yService requests."""

  def __init__(self, latest_forest_only: bool = False):
    self._received_forests: list[
        android_accessibility_forest_pb2.AndroidAccessibilityForest
    ] = []
    self._received_events: list[a11y_pb2.EventRequest] = []
    self._lock_forests = threading.Lock()
    self._lock_events = threading.Lock()
    self._latest_forest_only = latest_forest_only
    self._paused = True

    # A11y Forest bookkeeping.
    self._get_forest = asyncio.Event()  # Whether to request a forest.
    self._forest_ready = asyncio.Event()  # Whether the forest is ready.
    self._latest_forest: (
        android_accessibility_forest_pb2.AndroidAccessibilityForest | None
    ) = None

  def SendForest(
      self,
      request: android_accessibility_forest_pb2.AndroidAccessibilityForest,
      context: grpc.ServicerContext,
  ) -> a11y_pb2.ForestResponse:
    self._process_forest(request)
    return a11y_pb2.ForestResponse()

  def SendEvent(
      self,
      request: a11y_pb2.EventRequest,
      context: grpc.ServicerContext,
  ) -> a11y_pb2.EventResponse:
    self._process_event(request)
    return a11y_pb2.EventResponse()

  async def Bidi(
      self,
      request_iterator: AsyncIterator[a11y_pb2.ClientToServer],
      context: grpc.aio.ServicerContext,
  ) -> AsyncIterator[a11y_pb2.ServerToClient]:
    """Processes incoming ClientToServer requests."""

    logging.info('Starting A11yServicer.Bidi()')

    # Send a dummy message to unblock clients in their loop.
    yield a11y_pb2.ServerToClient()

    # This block defines two coroutines:
    #
    # * `read_client_requests()`
    # * `check_forest()`
    #
    # They cooperate with each other and both populate a queue `q` which is
    # consumed in a loop below, which actually yields requests which are sent to
    # the client. The processing finishes when the clients "closes" the
    # connection, which causes `read_client_requests()` to put a special value,
    # `STOP_ITERATION`, in the queue.

    # Queue for communicating from coroutines to `Bidi()`.
    q = asyncio.Queue()

    should_run = True

    async def read_client_requests():
      """Coroutine for reading client requests."""

      nonlocal should_run
      async for request in request_iterator:
        field_name = request.WhichOneof('payload')
        match field_name:
          case 'event':
            self._process_event(request.event)
          case 'forest':
            self._latest_forest = request.forest
            self._forest_ready.set()
            self._get_forest.clear()  # Reset the `Event`.
          case _:
            logging.error('Unknown field %r', field_name)
        await q.put(a11y_pb2.ServerToClient())

      # Send a special value to stop processing this `Bidi` connection.
      await q.put('STOP_ITERATION')
      should_run = False

    async def check_forest():
      """Coroutine for sending "get forest" requests."""

      nonlocal should_run
      while should_run:
        await self._get_forest.wait()
        await q.put(a11y_pb2.ServerToClient(get_forest={}))

    tasks = asyncio.gather(read_client_requests(), check_forest())

    while should_run:
      v = await q.get()
      if v == 'STOP_ITERATION':
        break
      else:
        yield v

    await tasks

    logging.info('Finishing A11yServicer.Bidi()')

  async def get_forest(
      self,
  ) -> android_accessibility_forest_pb2.AndroidAccessibilityForest | None:
    """Issues a request to get the a11y forest from the client."""

    self._get_forest.set()  # Unblocks coroutine to send a request.
    await self._forest_ready.wait()  # Wait for forest to be ready.
    self._forest_ready.clear()  # Reset the `Event`.
    return self._latest_forest

  def gather_forests(
      self,
  ) -> list[android_accessibility_forest_pb2.AndroidAccessibilityForest]:
    forests = []
    with self._lock_forests:
      forests = self._received_forests
      self._received_forests = []
    return forests

  def gather_events(self) -> list[a11y_pb2.EventRequest]:
    events = []
    with self._lock_events:
      events = self._received_events
      self._received_events = []
    return events

  def pause_and_clear(self) -> None:
    """Temporarily stop receiving events/forests and clear the queue.

    Used when resetting the environment; in this case:
    - all events/forests that have been received since last timestep are things
      that happened in the last episode after its `LAST` timestep (so we should
      ignore them, done by clearing the lists).
    - we're about to receive a bunch of events/forests just as a result of
      resetting the environment. We don't want to count these either; thus we
      temporarily stop receiving new ones.
    """
    self._paused = True
    with self._lock_forests:
      self._received_forests = []
    with self._lock_events:
      self._received_events = []

  def resume(self) -> None:
    """Start receiving events/forests (e.g., after a reset)."""
    self._paused = False

  def _process_event(self, event: a11y_pb2.EventRequest) -> None:
    """Adds the given event to the internal buffer of events."""

    if not self._paused:
      with self._lock_events:
        self._received_events.append(event)

  def _process_forest(
      self, forest: android_accessibility_forest_pb2.AndroidAccessibilityForest
  ) -> None:
    """Adds the given forest to the internal buffer of forests."""

    if not self._paused:
      with self._lock_forests:
        if self._latest_forest_only:
          self._received_forests = [forest]
        else:
          self._received_forests.append(forest)
