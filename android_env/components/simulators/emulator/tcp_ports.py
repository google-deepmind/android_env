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

"""Utility functions for allocating emulator ports."""

from typing import Final

from absl import logging
from android_env.components import config_classes
import portpicker

_ADB_PORT_RANGE_START: Final[int] = 5555
_ADB_PORT_RANGE_STOP: Final[int] = 5587
_ADB_PORT_STEP: Final[int] = 2
_DEFAULT_GRPC_PORT: Final[int] = 8554


def _pick_adb_port() -> int:
  """Finds a free port for ADB in the standard range."""
  for port in range(
      _ADB_PORT_RANGE_START, _ADB_PORT_RANGE_STOP, _ADB_PORT_STEP
  ):
    if portpicker.is_port_free(port):
      return port
  return portpicker.pick_unused_port()


def _pick_emulator_grpc_port() -> int:
  """Finds a free port for Emulator gRPC."""
  if portpicker.is_port_free(_DEFAULT_GRPC_PORT):
    return _DEFAULT_GRPC_PORT
  return portpicker.pick_unused_port()


def pick_emulator_ports(config: config_classes.EmulatorLauncherConfig) -> None:
  """Allocates ports for the emulator if they are not already set.

  If `config.emulator_console_port` is not positive, it is set to
  `config.adb_port - 1` to align with the standard `emulator-<console_port>`
  serial naming convention.

  Args:
    config: The emulator launcher configuration to update in place.
  """
  allocated_any = False
  if config.adb_port <= 0:
    config.adb_port = _pick_adb_port()
    allocated_any = True
  if config.emulator_console_port <= 0:
    config.emulator_console_port = config.adb_port - 1
    allocated_any = True
  if config.grpc_port <= 0:
    config.grpc_port = _pick_emulator_grpc_port()
    allocated_any = True

  if allocated_any:
    config.connect_to_existing = False
    logging.info(
        'Allocated ports for emulator: ADB=%d, Console=%d, gRPC=%d',
        config.adb_port,
        config.emulator_console_port,
        config.grpc_port,
    )
