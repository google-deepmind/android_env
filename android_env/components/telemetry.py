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

"""Structured telemetry data classes for AndroidEnv.

This module defines structured telemetry data classes such as
`BatteryPowerMetrics`. Metrics support both attribute access
(e.g., `metrics.level_percent`, `metrics.power_mw`) and dictionary subscript
indexing (e.g., `metrics['level_percent']`).
"""

from collections.abc import Mapping
import dataclasses
from typing import Any

from absl import logging
from android_env.proto import device_env_service_pb2


@dataclasses.dataclass(frozen=True)
class BatteryPowerMetrics:
  """Structured telemetry metrics for Android device battery and power state.

  Supports attribute access (`metrics.level_percent`, `metrics.power_mw`).

  Example:
    >>> metrics = telemetry.BatteryPowerMetrics.from_proto(proto)
    >>> print(metrics.level_percent)
    85
    >>> print(metrics.power_mw)
    1890.0
    >>> print(metrics.voltage_mv)
    4200

  Attributes:
    level_percent: Battery charge level percentage [0-100].
    current_now_ua: Instantaneous current draw in microamperes (uA). Positive
      for discharge, negative for charging.
    voltage_mv: Battery voltage in millivolts (mV).
    power_mw: Instantaneous power in milliwatts (mW).
    temperature_celsius: Battery temperature in degrees Celsius (°C).
    status: Battery status string (e.g., 'CHARGING', 'DISCHARGING', 'FULL').
    plugged_source: Power source ('AC', 'USB', 'WIRELESS', 'UNPLUGGED').
    charge_counter_uah: Remaining charge counter in microampere-hours (uAh).
    thermal_status: Thermal status integer code (0 = NONE to 6 = SHUTDOWN).
    energy_counter_nwh: Total remaining battery energy in nanowatt-hours (nWh).
  """

  level_percent: int
  current_now_ua: int
  voltage_mv: int
  power_mw: float
  temperature_celsius: float
  status: str
  plugged_source: str
  charge_counter_uah: int
  thermal_status: int
  energy_counter_nwh: int

  @classmethod
  def from_proto(
      cls, proto: device_env_service_pb2.BatteryPowerMetrics
  ) -> 'BatteryPowerMetrics':
    """Creates a BatteryPowerMetrics instance from a protobuf message.

    Example:
      >>> metrics = BatteryPowerMetrics.from_proto(proto)
      >>> print(metrics.level_percent)
      85

    Args:
      proto: Protobuf message containing battery power metrics.

    Returns:
      An immutable BatteryPowerMetrics instance.
    """
    return cls(
        level_percent=proto.level_percent,
        current_now_ua=proto.current_now_ua,
        voltage_mv=proto.voltage_mv,
        power_mw=proto.power_mw,
        temperature_celsius=proto.temperature_celsius,
        status=proto.status,
        plugged_source=proto.plugged_source,
        charge_counter_uah=proto.charge_counter_uah,
        thermal_status=proto.thermal_status,
        energy_counter_nwh=proto.energy_counter_nwh,
    )


def _extract_from_obj_or_mapping(bp: Any) -> BatteryPowerMetrics | None:
  """Extracts BatteryPowerMetrics from a proto, dataclass, mock, or dict object.

  Args:
    bp: Source object containing battery power metric attributes or keys.

  Returns:
    Extracted BatteryPowerMetrics instance, or None if extraction fails.
  """
  if bp is None:
    return None
  if isinstance(bp, BatteryPowerMetrics):
    return bp
  if isinstance(bp, device_env_service_pb2.BatteryPowerMetrics):
    return BatteryPowerMetrics.from_proto(bp)

  def _get_val(obj: Any, name: str, default: Any) -> Any:
    val = getattr(obj, name, None)
    if val is None and isinstance(obj, (dict, Mapping)) and name in obj:
      val = obj[name]
    if hasattr(val, 'item'):
      val = val.item()
    if val is not None and isinstance(val, (int, float, str, bool)):
      return val
    return default

  level_percent = _get_val(bp, 'level_percent', None)
  if level_percent is not None:
    return BatteryPowerMetrics(
        level_percent=int(level_percent),
        current_now_ua=int(_get_val(bp, 'current_now_ua', 0)),
        voltage_mv=int(_get_val(bp, 'voltage_mv', 4000)),
        power_mw=float(_get_val(bp, 'power_mw', 0.0)),
        temperature_celsius=float(_get_val(bp, 'temperature_celsius', 25.0)),
        status=str(_get_val(bp, 'status', 'UNKNOWN')),
        plugged_source=str(_get_val(bp, 'plugged_source', 'UNPLUGGED')),
        charge_counter_uah=int(_get_val(bp, 'charge_counter_uah', 0)),
        thermal_status=int(_get_val(bp, 'thermal_status', 0)),
        energy_counter_nwh=int(_get_val(bp, 'energy_counter_nwh', 0)),
    )
  return None


def fetch_battery_power_metrics(env: Any) -> BatteryPowerMetrics | None:
  """Fetches battery metrics from task_extras or returns None if missing.

  Args:
    env: Android environment instance.

  Returns:
    BatteryPowerMetrics instance if present in task_extras, else None.
  """
  try:
    if hasattr(env, 'task_extras'):
      extras = env.task_extras(latest_only=True)
      if extras and extras.get('battery_power') is not None:
        bp = extras['battery_power']
        extracted = _extract_from_obj_or_mapping(bp)
        if extracted is not None:
          return extracted
  except (AttributeError, KeyError, TypeError, RuntimeError) as e:
    logging.vlog(1, 'Could not extract battery_power from task_extras: %s', e)

  return None


get_battery_metrics = fetch_battery_power_metrics
