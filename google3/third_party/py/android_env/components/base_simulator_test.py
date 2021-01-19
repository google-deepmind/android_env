"""Tests for android_env.components.base_simulator."""

from typing import Optional, List

from absl.testing import absltest
from android_env.components import action_type
from android_env.components import adb_controller
from android_env.components import base_simulator
import mock
import numpy as np


class FakeSimulator(base_simulator.BaseSimulator):
  """A simulator that spits injected data."""

  def __init__(self, **kwargs):
    super().__init__(**kwargs)
    self._init_own_adb_controller()

  def adb_device_name(self) -> str:
    return 'FakeSimulator'

  def send_action(self, action) -> None:
    pass

  def _restart_impl(self) -> None:
    pass

  def _launch_impl(self) -> None:
    pass

  def _get_observation(self) -> Optional[List[np.ndarray]]:
    return [np.ones(shape=(640, 480, 3)), self._timestamp]

  def set_timestamp(self, timestamp: int):
    self._timestamp = timestamp


class BaseSimulatorTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self._adb_controller = mock.create_autospec(adb_controller.AdbController)

  def test_device_name(self):
    with mock.patch.object(
        adb_controller, 'AdbController', return_value=self._adb_controller):
      tmp_dir = absltest.get_default_test_tmpdir()
      simulator = FakeSimulator(
          adb_path='/my/adb',
          adb_port=5037,
          tmp_dir=tmp_dir,
          prompt_regex='awesome>')
      self.assertNotEmpty(simulator.adb_device_name())

  def test_launch(self):
    with mock.patch.object(
        adb_controller, 'AdbController', return_value=self._adb_controller):
      tmp_dir = absltest.get_default_test_tmpdir()
      simulator = FakeSimulator(
          adb_path='/my/adb',
          adb_port=5037,
          tmp_dir=tmp_dir,
          prompt_regex='awesome>')
      # The simulator should launch and not crash.
      self._adb_controller.get_screen_dimensions.return_value = (640, 480)
      simulator.launch()
      # After a successful launch(), the screen_dimensions property should
      # return something.
      np.testing.assert_equal(simulator.screen_dimensions, [640, 480])

  def test_launch_close(self):
    with mock.patch.object(
        adb_controller, 'AdbController', return_value=self._adb_controller):
      tmp_dir = absltest.get_default_test_tmpdir()
      simulator = FakeSimulator(
          adb_path='/my/adb',
          adb_port=5037,
          tmp_dir=tmp_dir,
          prompt_regex='awesome>')
      # The simulator should launch and not crash.
      self._adb_controller.get_screen_dimensions.return_value = (640, 480)
      simulator.launch()
      # Closing the simulator should also not crash.
      simulator.close()

  def test_get_observation(self):
    with mock.patch.object(
        adb_controller, 'AdbController', return_value=self._adb_controller):
      tmp_dir = absltest.get_default_test_tmpdir()
      simulator = FakeSimulator(
          adb_path='/my/adb',
          adb_port=5037,
          tmp_dir=tmp_dir,
          prompt_regex='awesome>')
      # The simulator should launch and not crash.
      self._adb_controller.get_screen_dimensions.return_value = (640, 480)
      simulator.launch()

      simulator.set_timestamp(123456)
      observation = simulator.get_observation()
      # Even though the FakeSimulator returns a 640x480x3 image, BaseSimulator
      # should add an extra layer for the last action.
      np.testing.assert_equal(observation['pixels'].shape, [640, 480, 3])
      # Because there was only a single step, the timestamp delta should be just
      # the timestamp returned by FakeSimulator.
      self.assertEqual(observation['timestamp'], 123456)

      # The orientation format should be a 4-dimension one-hot.
      np.testing.assert_equal(observation['orientation'].shape, [4])
      # Initially the orientation should not be set so we expect [0, 0, 0, 0].
      self.assertEqual(np.sum(observation['orientation']), 0)

      # After updating the device orientation, we do expect to get an actual
      # one-hot.
      self._adb_controller.get_orientation.return_value = '3'
      simulator.update_device_orientation()

      simulator.set_timestamp(123459)
      updated_observation = simulator.get_observation()
      np.testing.assert_equal(updated_observation['orientation'], [0, 0, 0, 1])
      # After setting the initial timestamp, we expect the timestamp delta to be
      # the difference between the current timestamp and the initial timestamp:
      # 123459 - 123456 = 3
      self.assertEqual(updated_observation['timestamp'], 3)

  def test_prepare_action(self):
    with mock.patch.object(
        adb_controller, 'AdbController', return_value=self._adb_controller):
      tmp_dir = absltest.get_default_test_tmpdir()
      simulator = FakeSimulator(
          adb_path='/my/adb',
          adb_port=5037,
          tmp_dir=tmp_dir,
          prompt_regex='awesome>')
      # The simulator should launch and not crash.
      self._adb_controller.get_screen_dimensions.return_value = (480, 640)
      simulator.launch()

      simulator.set_timestamp(123456)
      self.assertRaises(
          AssertionError, simulator._prepare_action, {
              'action_type': np.array(action_type.ActionType.REPEAT),
              'touch_position': [0.0, 0.0]
          })
      self.assertEqual(
          simulator._prepare_action({
              'action_type': np.array(action_type.ActionType.LIFT),
              'touch_position': [0.0, 0.0]
          }), (0, 0, False))
      self.assertEqual(
          simulator._prepare_action({
              'action_type': np.array(action_type.ActionType.TOUCH),
              'touch_position': [0.0, 0.0]
          }), (0, 0, True))
      self.assertEqual(
          simulator._prepare_action({
              'action_type': np.array(action_type.ActionType.TOUCH),
              'touch_position': [0.5, 0.2]
          }), (320, 96, True))
      self.assertEqual(
          simulator._prepare_action({
              'action_type': np.array(action_type.ActionType.TOUCH),
              'touch_position': [1.0, 1.0]
          }), (639, 479, True))


if __name__ == '__main__':
  absltest.main()
