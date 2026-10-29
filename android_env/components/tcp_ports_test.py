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

"""Tests for TCP ports allocation utilities."""

from unittest import mock

from absl.testing import absltest
from android_env.components import config_classes
from android_env.components import tcp_ports
import portpicker


class TcpPortsTest(absltest.TestCase):

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=9999)
  def test_pick_ports_all_unset(
      self, unused_mock_pick_unused, unused_mock_is_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig()
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 5555)
    self.assertEqual(launcher_config.emulator_console_port, 9999)
    self.assertEqual(launcher_config.grpc_port, 8554)

  def test_pick_ports_already_set(self):
    launcher_config = config_classes.EmulatorLauncherConfig(
        adb_port=1111,
        emulator_console_port=2222,
        grpc_port=3333,
        connect_to_existing=True,
    )
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 1111)
    self.assertEqual(launcher_config.emulator_console_port, 2222)
    self.assertEqual(launcher_config.grpc_port, 3333)
    self.assertTrue(launcher_config.connect_to_existing)

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=9999)
  def test_pick_ports_partial_resets_connect_to_existing(
      self, unused_mock_pick_unused, unused_mock_is_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig(
        adb_port=1111,
        connect_to_existing=True,
    )
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 1111)
    self.assertEqual(launcher_config.emulator_console_port, 9999)
    self.assertEqual(launcher_config.grpc_port, 8554)
    self.assertFalse(launcher_config.connect_to_existing)

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  def test_grpc_port(self, unused_mock_portpicker):
    launcher_config = config_classes.EmulatorLauncherConfig()
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.grpc_port, 8554)

  @mock.patch.object(portpicker, 'is_port_free', return_value=False)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=1234)
  def test_grpc_port_unavailable(
      self, unused_mock_pick_unused, unused_mock_is_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig()
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.grpc_port, 1234)

  @mock.patch.object(portpicker, 'is_port_free')
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=1234)
  def test_adb_port_selection(self, unused_mock_pick_unused, mock_is_port_free):
    # 5555 is busy, 5557 is free
    mock_is_port_free.side_effect = lambda p: p == 5557
    launcher_config = config_classes.EmulatorLauncherConfig()
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 5557)

  @mock.patch.object(portpicker, 'is_port_free', return_value=False)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=1234)
  def test_adb_port_all_busy(
      self, unused_mock_pick_unused, unused_mock_is_port_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig()
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 1234)

  @mock.patch.object(portpicker, 'is_port_free')
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=1234)
  def test_adb_port_selection_skips_even_ports(
      self, unused_mock_pick_unused, mock_is_port_free
  ):
    # 5555 is busy, 5556 is free, 5557 is free.
    # It should skip 5556 and pick 5557.
    mock_is_port_free.side_effect = lambda p: p in (5556, 5557)
    launcher_config = config_classes.EmulatorLauncherConfig()
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 5557)

  @mock.patch.object(portpicker, 'is_port_free')
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=1234)
  def test_adb_port_last_in_range(
      self, unused_mock_pick_unused, mock_is_port_free
  ):
    # Only the last port in the range (5585) is free.
    mock_is_port_free.side_effect = lambda p: p == 5585
    launcher_config = config_classes.EmulatorLauncherConfig()
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 5585)

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=9999)
  def test_pick_ports_negative(
      self, unused_mock_pick_unused, unused_mock_is_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig(
        adb_port=-1,
        emulator_console_port=-1,
        grpc_port=-1,
        connect_to_existing=True,
    )
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 5555)
    self.assertEqual(launcher_config.emulator_console_port, 9999)
    self.assertEqual(launcher_config.grpc_port, 8554)
    self.assertFalse(launcher_config.connect_to_existing)

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=9999)
  def test_pick_ports_only_adb_allocated_resets_connect_to_existing(
      self, unused_mock_pick_unused, unused_mock_is_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig(
        adb_port=0,
        emulator_console_port=2222,
        grpc_port=3333,
        connect_to_existing=True,
    )
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.adb_port, 5555)
    self.assertFalse(launcher_config.connect_to_existing)

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=9999)
  def test_pick_ports_only_console_allocated_resets_connect_to_existing(
      self, unused_mock_pick_unused, unused_mock_is_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig(
        adb_port=1111,
        emulator_console_port=0,
        grpc_port=3333,
        connect_to_existing=True,
    )
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.emulator_console_port, 9999)
    self.assertFalse(launcher_config.connect_to_existing)

  @mock.patch.object(portpicker, 'is_port_free', return_value=True)
  @mock.patch.object(portpicker, 'pick_unused_port', return_value=9999)
  def test_pick_ports_only_grpc_allocated_resets_connect_to_existing(
      self, unused_mock_pick_unused, unused_mock_is_free
  ):
    launcher_config = config_classes.EmulatorLauncherConfig(
        adb_port=1111,
        emulator_console_port=2222,
        grpc_port=0,
        connect_to_existing=True,
    )
    tcp_ports.pick_emulator_ports(launcher_config)
    self.assertEqual(launcher_config.grpc_port, 8554)
    self.assertFalse(launcher_config.connect_to_existing)


if __name__ == '__main__':
  absltest.main()
