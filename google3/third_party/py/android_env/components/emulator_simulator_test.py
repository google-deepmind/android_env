"""Tests for android_env.components.emulator_simulator."""

import subprocess

from absl.testing import absltest
from android_env.components import action_type
from android_env.components import adb_controller
from android_env.components import emulator_console
from android_env.components import emulator_launcher
from android_env.components import emulator_simulator
from android_env.components import errors
import mock
import numpy as np


class EmulatorSimulatorTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._adb_controller = mock.create_autospec(adb_controller.AdbController)
    self._launcher = mock.create_autospec(emulator_launcher.EmulatorLauncher)
    self._console = mock.create_autospec(emulator_console.EmulatorConsole)

    mock.patch.object(
        adb_controller, 'AdbController',
        return_value=self._adb_controller).start()
    mock.patch.object(
        emulator_launcher, 'EmulatorLauncher',
        return_value=self._launcher).start()

  def test_adb_device_name_not_empty(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')
    self.assertNotEmpty(simulator.adb_device_name())

  @mock.patch.object(subprocess, 'check_output', autospec=True)
  def test_launch_error(self, unused_mock_check_output):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    with mock.patch.object(
        emulator_console,
        'EmulatorConsole',
        return_value=self._console,
        side_effect=errors.ConsoleConnectionError('Something went wrong.')):
      self.assertRaises(errors.ConsoleConnectionError, simulator.launch)
    # The simulator should try once to restart the launcher.
    self._launcher.restart.assert_called_once()

  def test_close(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    with mock.patch.object(
        emulator_console, 'EmulatorConsole', return_value=self._console):
      simulator.launch()

      # For whatever reason clients may want to close the EmulatorSimulator.
      # We just want to check that the simulator does not crash and/or leak
      # resources.
      simulator.close()

  def test_restart(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    with mock.patch.object(
        emulator_console, 'EmulatorConsole', return_value=self._console):
      simulator.launch()

      # For whatever reason clients may want to restart the EmulatorSimulator.
      simulator.restart()
      # When that happens we just want to check that EmulatorSimulator called
      # EmulatorConsole.close() before starting it again.
      self._console.close.assert_called_once()

  def test_get_observation(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    with mock.patch.object(
        emulator_console, 'EmulatorConsole', return_value=self._console):
      simulator.launch()

    self._console.fetch_screenshot.return_value = [
        np.random.randint(
            low=0, high=255, dtype=np.uint8, size=(1234, 5678, 3)),
        np.array(54321)
    ]
    observation = simulator.get_observation()
    # The observation should have three components:
    #   - an image
    #   - the timedelta
    #   - the orientation.
    self.assertLen(observation, 3)
    # The first element (the "image") should have the same screen dimensions as
    # reported by ADB and it should have 3 channels (RGB).
    self.assertEqual(observation['pixels'].shape, (1234, 5678, 3))

  def test_send_action(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = emulator_simulator.EmulatorSimulator(
        emulator_launcher_args={},
        emulator_console_args={},
        adb_path='/my/adb',
        adb_server_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (5000, 1000)
    with mock.patch.object(
        emulator_console, 'EmulatorConsole', return_value=self._console):
      simulator.launch()

    simulator.send_action(
        {'action_type': np.array([action_type.ActionType.TOUCH]),
         'touch_position': np.array([0.25, 0.75])})
    simulator.send_action(
        {'action_type': np.array([action_type.ActionType.TOUCH]),
         'touch_position': np.array([0.75, 0.50])})
    simulator.send_action(
        {'action_type': np.array([action_type.ActionType.LIFT]),
         'touch_position': np.array([0.66, 0.33])})
    # We expect EmulatorSimulator to send the following calls:
    # 1st call:
    #     x-coordinate: 10000 * 0.25 = 250
    #     y-coordinate: 50000 * 0.75 = 3750
    #     down: True  # It's a touch command.
    # 2nd call:
    #     x-coordinate: 10000 * 0.75 = 750
    #     y-coordinate: 50000 * 0.50 = 2500
    #     down: True  # It's a touch command.
    # 3rd call:
    #     x-coordinate: 0
    #     y-coordinate: 0
    #     down: False  # It's a lift command.
    self._console.send_mouse_action.assert_has_calls([
        mock.call(250, 3750, True),
        mock.call(750, 2500, True),
        mock.call(0, 0, False),
    ])


if __name__ == '__main__':
  absltest.main()
