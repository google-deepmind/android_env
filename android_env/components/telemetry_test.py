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

"""Unit tests for structured telemetry data classes."""

import dataclasses
from unittest import mock
from absl.testing import absltest
from android_env.components import telemetry
from android_env.proto import device_env_service_pb2


class BatteryPowerMetricsTest(absltest.TestCase):

  def _make_sample_proto(self) -> device_env_service_pb2.BatteryPowerMetrics:
    proto = device_env_service_pb2.BatteryPowerMetrics()
    proto.level_percent = 85
    proto.current_now_ua = 450000
    proto.voltage_mv = 4200
    proto.power_mw = 1890.0
    proto.temperature_celsius = 28.5
    proto.status = 'DISCHARGING'
    proto.plugged_source = 'UNPLUGGED'
    proto.charge_counter_uah = 3000000
    proto.thermal_status = 0
    proto.energy_counter_nwh = 15000000000
    return proto

  def test_from_proto_and_attribute_access(self):
    proto = self._make_sample_proto()
    metrics = telemetry.BatteryPowerMetrics.from_proto(proto)

    self.assertEqual(metrics.level_percent, 85)
    self.assertEqual(metrics.current_now_ua, 450000)
    self.assertEqual(metrics.voltage_mv, 4200)
    self.assertAlmostEqual(metrics.power_mw, 1890.0)
    self.assertAlmostEqual(metrics.temperature_celsius, 28.5)
    self.assertEqual(metrics.status, 'DISCHARGING')
    self.assertEqual(metrics.plugged_source, 'UNPLUGGED')
    self.assertEqual(metrics.charge_counter_uah, 3000000)
    self.assertEqual(metrics.thermal_status, 0)
    self.assertEqual(metrics.energy_counter_nwh, 15000000000)

  def test_immutability_and_replace(self):
    proto = self._make_sample_proto()
    metrics = telemetry.BatteryPowerMetrics.from_proto(proto)

    with self.assertRaises((dataclasses.FrozenInstanceError, AttributeError)):
      setattr(metrics, 'level_percent', 50)

    replaced = dataclasses.replace(metrics, level_percent=90)
    self.assertEqual(replaced.level_percent, 90)
    self.assertEqual(metrics.level_percent, 85)
    self.assertNotEqual(metrics, replaced)

  def test_extract_from_obj_or_mapping(self):
    proto = self._make_sample_proto()
    metrics = telemetry.BatteryPowerMetrics.from_proto(proto)

    # Test None input
    self.assertIsNone(telemetry._extract_from_obj_or_mapping(None))

    # Test returning existing BatteryPowerMetrics instance
    self.assertIs(telemetry._extract_from_obj_or_mapping(metrics), metrics)

    # Test extracting from proto message and verify from_proto call
    with mock.patch.object(
        telemetry.BatteryPowerMetrics,
        'from_proto',
        wraps=telemetry.BatteryPowerMetrics.from_proto,
    ) as mock_from_proto:
      extracted_proto = telemetry._extract_from_obj_or_mapping(proto)
      mock_from_proto.assert_called_once_with(proto)
      self.assertEqual(extracted_proto, metrics)

    # Test extracting from dict
    as_dict = {
        'level_percent': 85,
        'current_now_ua': 450000,
        'voltage_mv': 4200,
        'power_mw': 1890.0,
        'temperature_celsius': 28.5,
        'status': 'DISCHARGING',
        'plugged_source': 'UNPLUGGED',
        'charge_counter_uah': 3000000,
        'thermal_status': 0,
        'energy_counter_nwh': 15000000000,
    }
    extracted_dict = telemetry._extract_from_obj_or_mapping(as_dict)
    self.assertEqual(extracted_dict, metrics)

    # Test extracting from object with .item() scalar wrappers (e.g. numpy scalars)
    class FakeScalar:

      def __init__(self, val):
        self._val = val

      def item(self):
        return self._val

    class FakeNumpyObj:

      def __init__(self):
        self.level_percent = FakeScalar(85)
        self.current_now_ua = FakeScalar(450000)
        self.voltage_mv = FakeScalar(4200)
        self.power_mw = FakeScalar(1890.0)
        self.temperature_celsius = FakeScalar(28.5)
        self.status = 'DISCHARGING'
        self.plugged_source = 'UNPLUGGED'
        self.charge_counter_uah = FakeScalar(3000000)
        self.thermal_status = FakeScalar(0)
        self.energy_counter_nwh = FakeScalar(15000000000)

    extracted_numpy = telemetry._extract_from_obj_or_mapping(FakeNumpyObj())
    self.assertEqual(extracted_numpy, metrics)

    # Test invalid object (missing level_percent) returns None
    self.assertIsNone(
        telemetry._extract_from_obj_or_mapping({'other_key': 123})
    )

    # Test object with invalid non-primitive attribute types (e.g. list/dict) returns None
    class FakeInvalidTypesObj:
      level_percent = [85, 90]
      status = {'invalid': 'type'}

    self.assertIsNone(
        telemetry._extract_from_obj_or_mapping(FakeInvalidTypesObj())
    )
    self.assertIsNone(
        telemetry._extract_from_obj_or_mapping({'level_percent': [85, 90]})
    )

    # Verify attribute access takes precedence over dictionary subscripting
    class HybridObj(dict):
      level_percent = 95
      status = 'CHARGING'

    hybrid = HybridObj({'level_percent': 10, 'status': 'DISCHARGING'})
    extracted_hybrid = telemetry._extract_from_obj_or_mapping(hybrid)
    self.assertIsNotNone(extracted_hybrid)
    self.assertEqual(extracted_hybrid.level_percent, 95)
    self.assertEqual(extracted_hybrid.status, 'CHARGING')

  def test_fetch_battery_power_metrics_task_extras(self):
    mock_env = mock.Mock()
    mock_battery = self._make_sample_proto()
    mock_env.task_extras.return_value = {'battery_power': mock_battery}

    metrics = telemetry.fetch_battery_power_metrics(mock_env)
    self.assertIsNotNone(metrics)
    self.assertEqual(metrics.level_percent, 85)

  def test_fetch_battery_power_metrics_fallback_and_exception(self):
    mock_env = mock.Mock()
    mock_env.task_extras.return_value = {}
    self.assertIsNone(telemetry.fetch_battery_power_metrics(mock_env))

    mock_env_none = mock.Mock()
    mock_env_none.task_extras.return_value = {'battery_power': None}
    self.assertIsNone(telemetry.fetch_battery_power_metrics(mock_env_none))

    mock_env_err = mock.Mock()
    mock_env_err.task_extras.side_effect = RuntimeError('SDK error')
    self.assertIsNone(telemetry.fetch_battery_power_metrics(mock_env_err))


if __name__ == '__main__':
  absltest.main()
