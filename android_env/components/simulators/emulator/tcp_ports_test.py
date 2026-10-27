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
from android_env.components.simulators.emulator import tcp_ports
import portpicker


class TcpPortsTest(absltest.TestCase):

  @mock.patch.object(
      portpicker,
      'is_port_free',
      autospec=True,
      spec_set=True,
      return_value=True,
  )
  @mock.patch.object(
      portpicker,
      'pick_unused_port',
      autospec=True,
      spec_set=True,
      return_value=9999,
  )
  def test_pick_ports_all_unset(
      self,
      mock_pick_unused: mock.MagicMock,
      mock_is_free: mock.MagicMock,
  ) -> None:
    launcher_config = config_classes.EmulatorLauncherConfig(
        connect_to_existing=True
    )

    tcp_ports.pick_emulator_ports(launcher_config)

    self.assertEqual(launcher_config.adb_port, 5555)
    self.assertEqual(launcher_config.emulator_console_port, 5554)
    self.assertEqual(launcher_config.grpc_port, 8554)
    self.assertFalse(launcher_config.connect_to_existing)
    mock_is_free.assert_has_calls([mock.call(5555), mock.call(8554)])
    self.assertEqual(mock_is_free.call_count, 2)
    mock_pick_unused.assert_not_called()

  @mock.patch.object(portpicker, 'is_port_free', autospec=True, spec_set=True)
  @mock.patch.object(
      portpicker, 'pick_unused_port', autospec=True, spec_set=True
  )
  def test_pick_ports_already_set_preserves_values(
      self,
      mock_pick_unused: mock.MagicMock,
      mock_is_free: mock.MagicMock,
  ) -> None:
    for testcase_name, adb_port, console_port, grpc_port in (
        ('custom_positive_ports', 1111, 2222, 3333),
        ('exact_positive_boundary_one', 1, 1, 1),
    ):
      with self.subTest(testcase_name=testcase_name):
        mock_is_free.reset_mock()
        mock_pick_unused.reset_mock()
        launcher_config = config_classes.EmulatorLauncherConfig(
            adb_port=adb_port,
            emulator_console_port=console_port,
            grpc_port=grpc_port,
            connect_to_existing=True,
        )

        tcp_ports.pick_emulator_ports(launcher_config)

        self.assertEqual(launcher_config.adb_port, adb_port)
        self.assertEqual(launcher_config.emulator_console_port, console_port)
        self.assertEqual(launcher_config.grpc_port, grpc_port)
        self.assertTrue(launcher_config.connect_to_existing)
        mock_is_free.assert_not_called()
        mock_pick_unused.assert_not_called()

  @mock.patch.object(
      portpicker,
      'is_port_free',
      autospec=True,
      spec_set=True,
      return_value=True,
  )
  @mock.patch.object(
      portpicker,
      'pick_unused_port',
      autospec=True,
      spec_set=True,
      return_value=9999,
  )
  def test_console_port_aligned_with_preset_adb_port(
      self,
      mock_pick_unused: mock.MagicMock,
      mock_is_free: mock.MagicMock,
  ) -> None:
    for (
        testcase_name,
        adb_port,
        initial_console_port,
        expected_console_port,
    ) in (
        ('zero_console_port_with_preset_adb', 1111, 0, 1110),
        ('negative_console_port_with_preset_adb', 5554, -1, 5553),
    ):
      with self.subTest(testcase_name=testcase_name):
        mock_is_free.reset_mock()
        mock_pick_unused.reset_mock()
        launcher_config = config_classes.EmulatorLauncherConfig(
            adb_port=adb_port,
            emulator_console_port=initial_console_port,
            grpc_port=3333,
            connect_to_existing=True,
        )

        tcp_ports.pick_emulator_ports(launcher_config)

        self.assertEqual(launcher_config.adb_port, adb_port)
        self.assertEqual(
            launcher_config.emulator_console_port, expected_console_port
        )
        self.assertEqual(launcher_config.grpc_port, 3333)
        self.assertFalse(launcher_config.connect_to_existing)
        mock_is_free.assert_not_called()
        mock_pick_unused.assert_not_called()

  @mock.patch.object(
      portpicker,
      'is_port_free',
      autospec=True,
      spec_set=True,
      return_value=True,
  )
  @mock.patch.object(
      portpicker,
      'pick_unused_port',
      autospec=True,
      spec_set=True,
      return_value=9999,
  )
  def test_partial_or_negative_allocation_resets_connect_to_existing(
      self,
      mock_pick_unused: mock.MagicMock,
      unused_mock_is_free: mock.MagicMock,
  ) -> None:
    scenarios = (
        (
            'only_adb_zero_preserves_positive_console',
            0,
            2222,
            3333,
            5555,
            2222,
            3333,
        ),
        (
            'only_adb_negative_preserves_positive_console',
            -1,
            2222,
            3333,
            5555,
            2222,
            3333,
        ),
        (
            'only_console_zero_aligns_to_adb_port',
            1111,
            0,
            3333,
            1111,
            1110,
            3333,
        ),
        (
            'only_console_negative_aligns_to_adb_port',
            1111,
            -1,
            3333,
            1111,
            1110,
            3333,
        ),
        (
            'only_grpc_zero_preserves_adb_and_console',
            1111,
            2222,
            0,
            1111,
            2222,
            8554,
        ),
        (
            'only_grpc_negative_preserves_adb_and_console',
            1111,
            2222,
            -1,
            1111,
            2222,
            8554,
        ),
        (
            'all_negative_ports_allocated_and_aligned',
            -1,
            -1,
            -1,
            5555,
            5554,
            8554,
        ),
    )
    for (
        testcase_name,
        initial_adb_port,
        initial_console_port,
        initial_grpc_port,
        expected_adb_port,
        expected_console_port,
        expected_grpc_port,
    ) in scenarios:
      with self.subTest(testcase_name=testcase_name):
        mock_pick_unused.reset_mock()
        launcher_config = config_classes.EmulatorLauncherConfig(
            adb_port=initial_adb_port,
            emulator_console_port=initial_console_port,
            grpc_port=initial_grpc_port,
            connect_to_existing=True,
        )

        tcp_ports.pick_emulator_ports(launcher_config)

        self.assertEqual(launcher_config.adb_port, expected_adb_port)
        self.assertEqual(
            launcher_config.emulator_console_port, expected_console_port
        )
        self.assertEqual(launcher_config.grpc_port, expected_grpc_port)
        self.assertFalse(launcher_config.connect_to_existing)
        mock_pick_unused.assert_not_called()

  @mock.patch.object(portpicker, 'is_port_free', autospec=True, spec_set=True)
  @mock.patch.object(
      portpicker,
      'pick_unused_port',
      autospec=True,
      spec_set=True,
      return_value=1234,
  )
  def test_adb_port_selection_in_standard_range(
      self,
      mock_pick_unused: mock.MagicMock,
      mock_is_port_free: mock.MagicMock,
  ) -> None:
    scenarios = (
        ('second_odd_port_when_first_busy', (5557, 8554), 5557, 5556),
        ('skips_even_ports_in_range', (5556, 5557, 8554), 5557, 5556),
        ('last_odd_port_in_range', (5585, 8554), 5585, 5584),
    )
    for (
        testcase_name,
        free_ports,
        expected_adb_port,
        expected_console_port,
    ) in scenarios:
      with self.subTest(testcase_name=testcase_name):
        mock_is_port_free.reset_mock()
        mock_pick_unused.reset_mock()
        mock_is_port_free.side_effect = (
            lambda port, available_ports=free_ports: port in available_ports
        )
        launcher_config = config_classes.EmulatorLauncherConfig()

        tcp_ports.pick_emulator_ports(launcher_config)

        self.assertEqual(launcher_config.adb_port, expected_adb_port)
        self.assertEqual(
            launcher_config.emulator_console_port, expected_console_port
        )
        self.assertEqual(launcher_config.grpc_port, 8554)
        mock_pick_unused.assert_not_called()

  @mock.patch.object(portpicker, 'is_port_free', autospec=True, spec_set=True)
  @mock.patch.object(
      portpicker,
      'pick_unused_port',
      autospec=True,
      spec_set=True,
      return_value=1234,
  )
  def test_adb_port_all_busy_falls_back_to_portpicker_and_aligns_console(
      self,
      mock_pick_unused: mock.MagicMock,
      mock_is_port_free: mock.MagicMock,
  ) -> None:
    # Ports 5553 and 5587 are outside [5555, 5587) and must not be selected.
    mock_is_port_free.side_effect = lambda port: port in (5553, 5587, 8554)
    launcher_config = config_classes.EmulatorLauncherConfig()

    tcp_ports.pick_emulator_ports(launcher_config)

    self.assertEqual(launcher_config.adb_port, 1234)
    self.assertEqual(launcher_config.emulator_console_port, 1233)
    self.assertEqual(launcher_config.grpc_port, 8554)
    mock_is_port_free.assert_any_call(8554)
    mock_pick_unused.assert_called_once_with()

  @mock.patch.object(
      portpicker,
      'is_port_free',
      autospec=True,
      spec_set=True,
      return_value=False,
  )
  @mock.patch.object(
      portpicker,
      'pick_unused_port',
      autospec=True,
      spec_set=True,
      side_effect=[4321, 8765],
  )
  def test_grpc_port_unavailable_falls_back_to_portpicker(
      self,
      mock_pick_unused: mock.MagicMock,
      mock_is_free: mock.MagicMock,
  ) -> None:
    launcher_config = config_classes.EmulatorLauncherConfig()

    tcp_ports.pick_emulator_ports(launcher_config)

    self.assertEqual(launcher_config.adb_port, 4321)
    self.assertEqual(launcher_config.emulator_console_port, 4320)
    self.assertEqual(launcher_config.grpc_port, 8765)
    mock_is_free.assert_any_call(8554)
    self.assertEqual(mock_pick_unused.call_count, 2)


if __name__ == '__main__':
  absltest.main()
