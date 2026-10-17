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

"""Wraps AndroidEnv to add task support (rewards, setup/reset steps, extras)."""

from collections.abc import Generator, Iterable
import queue
import re
from typing import Any

from android_env import env_interface
from android_env.components import adb_call_parser as adb_call_parser_lib
from android_env.components import config_classes
from android_env.components import log_stream as log_stream_lib
from android_env.components import task_manager as task_manager_lib
from android_env.proto import adb_pb2
from android_env.proto import task_pb2
from android_env.wrappers import base_wrapper
import dm_env
import numpy as np

_LOGCAT_PREFIX_RE = re.compile(
    r'^\s*(?:\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d+|\d+\.\d+)'
    r'\s+\d+\s+\d+\s+\S\s+[^:]*:\s*'
)


def _normalize_log_line(line: str) -> str:
  """Formats a device log line into the epoch format expected by LogcatThread."""
  msg = _LOGCAT_PREFIX_RE.sub('', line)
  return f'         0.000     1     1 I AndroidEnv: {msg}'


class _SignalLogStream(log_stream_lib.LogStream):
  """LogStream backed by a synchronous queue fed from device state signals."""

  def __init__(self) -> None:
    super().__init__(verbose=False)
    self._queue: queue.Queue[str | None] = queue.Queue()

  def _get_stream_output(self) -> Generator[str, None, None]:
    while (line := self._queue.get()) is not None:
      yield line
      self._queue.task_done()

  def push_logs(self, lines: Iterable[str]) -> None:
    """Enqueues log lines and blocks until LogcatThread processes all of them."""
    for line in lines:
      self._queue.put(_normalize_log_line(line))
    self._queue.join()

  def stop_stream(self) -> None:
    self._queue.put(None)


class _AdbCallParserAdapter(adb_call_parser_lib.AdbCallParser):
  """Adapts AndroidEnvInterface.execute_adb_call to AdbCallParser interface."""

  def __init__(self, env: env_interface.AndroidEnvInterface):
    self._env = env

  def parse(self, request: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    return self._env.execute_adb_call(request)


class TaskWrapper(base_wrapper.BaseWrapper):
  """Wraps an AndroidEnv instance to support task-based RL execution."""

  def __init__(
      self,
      env: env_interface.AndroidEnvInterface,
      task: task_pb2.Task,
      config: config_classes.TaskManagerConfig | None = None,
      log_stream: log_stream_lib.LogStream | None = None,
  ) -> None:
    """Initializes TaskWrapper.

    Args:
      env: Base environment implementing AndroidEnvInterface.
      task: Task definition proto.
      config: TaskManager configuration.
      log_stream: Optional LogStream instance for log parsing.
    """
    super().__init__(env)
    self._task = task
    self._task_manager = task_manager_lib.TaskManager(task=task, config=config)
    self._signal_log_stream: _SignalLogStream | None = None
    self._log_stream = log_stream
    self._task_manager_started = False
    self._reset_next_step = True
    self._latest_extras: dict[str, np.ndarray] = {}

  def _ensure_task_manager_started(self) -> None:
    if self._task_manager_started:
      return
    if self._log_stream is None:
      self._signal_log_stream = _SignalLogStream()
      self._log_stream = self._signal_log_stream
    self._task_manager.start(
        adb_call_parser_factory=lambda: _AdbCallParserAdapter(self._env),
        log_stream=self._log_stream,
    )
    self._task_manager.setup_task()
    self._task_manager_started = True

  def _forward_device_logs(self) -> None:
    if self._signal_log_stream is None:
      return
    logs = self._env.task_extras(latest_only=False).get('logs', ())
    self._signal_log_stream.push_logs(logs)

  def _extract_timestep_extras(
      self, timestep: dm_env.TimeStep
  ) -> dm_env.TimeStep:
    if timestep.observation is not None:
      self._latest_extras = timestep.observation.pop('extras', {})
    return timestep

  def reset(self) -> dm_env.TimeStep:
    self._ensure_task_manager_started()
    self._task_manager.reset_task()
    timestep = self._env.reset()
    self._forward_device_logs()
    observation = dict(timestep.observation)
    rl_timestep = self._task_manager.rl_reset(observation)
    self._reset_next_step = False
    return self._extract_timestep_extras(rl_timestep)

  def step(self, action: Any) -> dm_env.TimeStep:
    if self._reset_next_step:
      return self.reset()
    processed_action = self._process_action(action)
    timestep = self._env.step(processed_action)
    self._forward_device_logs()
    observation = dict(timestep.observation)
    rl_timestep = self._task_manager.rl_step(observation)
    if rl_timestep.last():
      self._reset_next_step = True
    return self._extract_timestep_extras(rl_timestep)

  def task_extras(self, latest_only: bool = True) -> dict[str, Any]:
    extras = dict(self._env.task_extras(latest_only=latest_only))
    for key, spec in self._latest_extras.items():
      extra_values = spec.astype(spec.dtype)
      extras[key] = extra_values[-1] if latest_only else extra_values
    return extras

  def stats(self) -> dict[str, Any]:
    info = dict(self._env.stats())
    if self._task_manager_started:
      info.update(self._task_manager.stats())
    return info

  def stop_task(self) -> None:
    """Stops the current task manager without closing the wrapped environment."""
    if self._task_manager_started:
      self._task_manager.stop()
      self._task_manager_started = False

  def close(self) -> None:
    self.stop_task()
    super().close()
