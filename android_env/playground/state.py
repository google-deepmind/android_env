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

"""Shared state for AndroidEnv Playground."""

from collections.abc import Mapping
import queue
import threading
from typing import Any


class PlaygroundState:
  """Holds the shared state for the AndroidEnv playground.

  This class acts as a thread-safe container for state variables shared between
  the main server thread and the background AndroidEnv execution thread.
  """

  def __init__(self):
    """Initializes the shared state."""
    # The most recent processed screen frame (JPEG bytes)
    self.current_frame = None
    # Lock protecting updates to current_frame
    self.frame_lock = threading.Lock()
    # Queue for actions received from client to be consumed by AndroidEnv
    self.action_queue = queue.Queue()
    # Flag to control the background AndroidEnv run loop
    self.running = True
    # Active WebSocket connection socket for streaming frames
    self.active_ws = None
    # Lock protecting access to active_ws
    self.active_ws_lock = threading.RLock()
    # Flag indicating if we are waiting for an ACK from client for sent frame
    self.waiting_for_ack = False
    # Timestamp of when the last frame was sent to the client
    self.last_frame_sent_time = 0.0

    # Log history buffer
    self.logs_lock = threading.RLock()
    self.logs: list[dict[str, Any]] = []
    self.max_logs = 10000

    # Status message
    self._status: str | None = None
    self._status_lock = threading.Lock()

    # Task reload flags
    self._active_task_id: str | None = None
    self._reload_lock = threading.Lock()

    # Episode reset flag and ADB command queue
    self._reset_requested = False
    self._reset_lock = threading.Lock()
    self.adb_queue: queue.Queue[str] = queue.Queue()

    # Stats accumulation
    self.stats_lock = threading.Lock()
    self.pending_stats = {
        'ack_latency': [],
        'env_step_ms': [],
        'action_transit_ms': [],
        'action_queue_ms': [],
        'action_total_pre_step_ms': [],
    }
    self.battery_power_stats: dict[str, Any] | None = None
    self.episode_stats: dict[str, Any] | None = None

  def set_active_ws(self, sock):
    """Thread-safely sets the active WebSocket connection.

    Args:
      sock: The socket object representing the active WebSocket client.
    """
    with self.active_ws_lock:
      self.active_ws = sock

  def get_active_ws(self):
    """Thread-safely retrieves the active WebSocket connection.

    Returns:
      The active socket object, or None if no client is connected.
    """
    with self.active_ws_lock:
      return self.active_ws

  def set_status(self, status: str) -> None:
    """Thread-safely sets the latest status message."""
    with self._status_lock:
      self._status = status

  def get_status(self) -> str | None:
    """Thread-safely retrieves the latest status message."""
    with self._status_lock:
      return self._status

  def add_stat(self, category: str, value: float):
    """Thread-safely adds a stat value to the pending stats."""
    with self.stats_lock:
      if category in self.pending_stats:
        self.pending_stats[category].append(value)

  def set_battery_power_stats(self, metrics: Any):
    """Thread-safely sets the latest battery and power telemetry metrics."""

    def _get_val(obj: Any, name: str) -> Any:
      if isinstance(obj, (dict, Mapping)):
        val = obj.get(name)
      else:
        val = getattr(obj, name, None)
      if hasattr(val, 'item'):
        val = val.item()
      return val

    extracted = {}
    for key in (
        'level_percent',
        'voltage_mv',
        'current_now_ua',
        'power_mw',
        'temperature_celsius',
        'status',
        'plugged_source',
        'charge_counter_uah',
        'energy_counter_nwh',
        'thermal_status',
    ):
      v = _get_val(metrics, key)
      if v is not None:
        extracted[key] = v

    with self.stats_lock:
      self.battery_power_stats = extracted

  def get_battery_power_stats(self) -> dict[str, Any] | None:
    """Thread-safely retrieves the latest battery and power telemetry metrics."""
    with self.stats_lock:
      return (
          dict(self.battery_power_stats)
          if self.battery_power_stats is not None
          else None
      )

  def set_episode_stats(self, episode_stats: dict[str, Any]) -> None:
    """Thread-safely sets the latest RL episode telemetry metrics."""
    with self.stats_lock:
      self.episode_stats = dict(episode_stats)

  def get_episode_stats(self) -> dict[str, Any] | None:
    """Thread-safely retrieves the latest RL episode telemetry metrics."""
    with self.stats_lock:
      return (
          dict(self.episode_stats) if self.episode_stats is not None else None
      )

  def flush_stats(self) -> dict[str, Any]:
    """Thread-safely flushes and returns the averaged pending stats."""
    with self.stats_lock:
      stats = {}
      for k, v in self.pending_stats.items():
        if v:
          stats[k] = sum(v) / len(v)
          v.clear()
      if self.battery_power_stats is not None:
        stats['battery_power'] = dict(self.battery_power_stats)
      if self.episode_stats is not None:
        stats['episode'] = dict(self.episode_stats)
      return stats

  def set_reload(self, task_id: str):
    """Thread-safely sets the active task id for reload."""
    with self._reload_lock:
      self._active_task_id = task_id

  def get_reload(self) -> str | None:
    """Thread-safely retrieves the active task id."""
    with self._reload_lock:
      return self._active_task_id

  def clear_reload(self):
    """Thread-safely clears the active task id reload flag."""
    with self._reload_lock:
      self._active_task_id = None

  def set_reset(self) -> None:
    """Thread-safely requests an episode reset."""
    with self._reset_lock:
      self._reset_requested = True

  def get_reset(self) -> bool:
    """Thread-safely returns whether an episode reset is requested."""
    with self._reset_lock:
      return self._reset_requested

  def clear_reset(self) -> None:
    """Thread-safely clears the episode reset flag."""
    with self._reset_lock:
      self._reset_requested = False

  def add_log(self, log_entry: dict[str, Any]):
    """Thread-safely appends a log entry to history."""
    with self.logs_lock:
      self.logs.append(log_entry)
      if len(self.logs) > self.max_logs:
        self.logs.pop(0)

  def get_logs(self) -> list[dict[str, Any]]:
    """Thread-safely returns a copy of log history."""
    with self.logs_lock:
      return list(self.logs)

  def clear_logs(self):
    """Thread-safely clears log history."""
    with self.logs_lock:
      self.logs.clear()
