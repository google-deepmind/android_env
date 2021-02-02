"""Tests for android_env.components.vanadium_simulator."""

from absl.testing import absltest
from android_env.components import action_type
from android_env.components import adb_controller
from android_env.components import vanadium_communicator
from android_env.components import vanadium_launcher
from android_env.components import vanadium_simulator
import mock
import numpy as np


class VanadiumSimulatorTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._adb_controller = mock.create_autospec(adb_controller.AdbController)
    self._launcher = mock.create_autospec(vanadium_launcher.VanadiumLauncher)
    self._communicator = mock.create_autospec(
        vanadium_communicator.VanadiumCommunicator)

    mock.patch.object(
        adb_controller, 'AdbController',
        return_value=self._adb_controller).start()
    mock.patch.object(
        vanadium_launcher, 'VanadiumLauncher',
        return_value=self._launcher).start()

  def test_close(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = vanadium_simulator.VanadiumSimulator(
        vanadium_launcher_args={},
        adb_path='/my/adb',
        adb_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>',
        communication_binaries_path='')

    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    with mock.patch.object(
        vanadium_communicator,
        'VanadiumCommunicator',
        return_value=self._communicator):
      simulator.launch()
      simulator.close()

  def test_get_observation(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = vanadium_simulator.VanadiumSimulator(
        vanadium_launcher_args={},
        adb_path='/my/adb',
        adb_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>',
        communication_binaries_path='')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    with mock.patch.object(
        vanadium_communicator,
        'VanadiumCommunicator',
        return_value=self._communicator):
      simulator.launch()

    self._communicator.fetch_screenshot.return_value = np.random.randint(
        low=0, high=255, dtype=np.uint8, size=(1234, 5678, 3))

    simulator._orientation = 1
    observation = simulator.get_observation()
    # The observation should have three components:
    #   - an image
    #   - the timestamp
    #   - the orientation.
    self.assertLen(observation, 3)
    # The first element (the "image") should have the same screen dimensions as
    # reported by ADB and it should have 3 channels (RGB).
    self.assertEqual(observation['pixels'].shape, (1234, 5678, 3))

  def test_send_action(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = vanadium_simulator.VanadiumSimulator(
        vanadium_launcher_args={},
        adb_path='/my/adb',
        adb_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>',
        communication_binaries_path='')

    # The simulator should launch and not crash.
    self._adb_controller.get_screen_dimensions.return_value = (5000, 1000)
    with mock.patch.object(
        vanadium_communicator,
        'VanadiumCommunicator',
        return_value=self._communicator):
      simulator.launch()

    simulator.send_action(
        {'action_type': np.array(action_type.ActionType.TOUCH),
         'touch_position': np.array([0.25, 0.75])})
    simulator.send_action(
        {'action_type': np.array(action_type.ActionType.TOUCH),
         'touch_position': np.array([0.75, 0.50])})
    simulator.send_action(
        {'action_type': np.array(action_type.ActionType.LIFT),
         'touch_position': np.array([0.66, 0.33])})
    # We expect VanadiumSimulator to send the following calls:
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
    self._communicator.send_mouse_action.assert_has_calls([
        mock.call(250, 3750, True),
        mock.call(750, 2500, True),
        mock.call(0, 0, False),
    ])

  def test_tcp_connection(self):
    tmp_dir = absltest.get_default_test_tmpdir()
    simulator = vanadium_simulator.VanadiumSimulator(
        vanadium_launcher_args={},
        adb_path='/my/adb',
        adb_port=5037,
        tmp_dir=tmp_dir,
        prompt_regex='awesome>',
        communication_binaries_path='')

    self._adb_controller.get_screen_dimensions.return_value = (1234, 5678)
    with mock.patch.object(
        vanadium_communicator,
        'VanadiumCommunicator',
        return_value=self._communicator):
      self._adb_controller.tcp_connect.assert_not_called()
      simulator.launch()
      # Creating more adb_controllers should not trigger more connections or
      # disconnections
      _ = simulator.create_adb_controller()
      self._adb_controller.tcp_connect.assert_called_once()
      self._adb_controller.tcp_disconnect.assert_not_called()
      simulator.close()
      self._adb_controller.tcp_disconnect.assert_called_once()


if __name__ == '__main__':
  absltest.main()
