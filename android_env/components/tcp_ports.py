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

from absl import logging
from android_env.components import config_classes
import portpicker


def _pick_adb_port() -> int:
  """Finds a free port for ADB in the standard range."""
  for p in range(5555, 5587, 2):
    if portpicker.is_port_free(p):
      return p
  return portpicker.pick_unused_port()


def _pick_emulator_grpc_port() -> int:
  """Finds a free port for Emulator gRPC."""
  if portpicker.is_port_free(8554):
    return 8554
  else:
    return portpicker.pick_unused_port()


def pick_emulator_ports(config: config_classes.EmulatorLauncherConfig) -> None:
  """Allocates ports for the emulator if they are not already set."""
  allocated_any = False
  if config.adb_port <= 0:
    config.adb_port = _pick_adb_port()
    allocated_any = True
  if config.emulator_console_port <= 0:
    config.emulator_console_port = portpicker.pick_unused_port()
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
