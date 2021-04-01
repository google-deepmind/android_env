"""Tests for coordinator.py."""

import time

from absl.testing import absltest
from android_env.components import action_type
from android_env.components import coordinator
from android_env.components import emulator_simulator
from android_env.components import errors
from android_env.components import task_manager
import mock
import numpy as np


class CoordinatorTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._simulator = mock.create_autospec(emulator_simulator.EmulatorSimulator)
    self._task_manager = mock.create_autospec(task_manager.TaskManager)

    self._coordinator = coordinator.Coordinator(
        simulator=self._simulator,
        task_manager=self._task_manager,
        step_timeout_sec=2,
        max_steps_per_sec=60,
        periodic_restart_time_min=0)

  def test_restart_simulator(self):
    self._coordinator.restart_simulator()

  def test_reset(self):
    self._coordinator.reset()

  def test_process_action(self):
    self._simulator.get_observation.return_value = {'observation': 0}
    observation = self._coordinator.execute_action(
        action={'action_type': np.array(action_type.ActionType.LIFT)})
    self.assertDictEqual(observation, {'observation': 0})

  def test_process_action_error(self):
    self._simulator.get_observation.side_effect = errors.ReadObservationError()
    observation = self._coordinator.execute_action(
        action={'action_type': np.array(action_type.ActionType.LIFT)})
    self.assertTrue(self._coordinator._should_restart)
    self.assertIsNone(observation)

  def test_execute_action_touch(self):
    self._simulator.get_observation.return_value = {'observation': 0}
    self._simulator.send_action.return_value = True
    action = {'action_type': np.array(action_type.ActionType.TOUCH)}
    _ = self._coordinator.execute_action(action)
    self._simulator.send_action.assert_called_once_with(action)

  def test_execute_action_repeat(self):
    self._simulator.get_observation.return_value = {'observation': 0}
    self._simulator.send_action.return_value = True
    _ = self._coordinator.execute_action(
        {'action_type': np.array(action_type.ActionType.REPEAT)})
    self._simulator.send_action.assert_not_called()

  def test_execute_action_error(self):
    self._simulator.get_observation.return_value = {'observation': 0}
    self._simulator.send_action.side_effect = errors.SendActionError
    _ = self._coordinator.execute_action(
        {'action_type': np.array(action_type.ActionType.TOUCH)})
    self.assertTrue(self._coordinator._should_restart)

  def test_check_timeout_false(self):
    self._coordinator._latest_observation_local_time = time.time()
    timeout = self._coordinator.check_timeout()
    self.assertFalse(timeout)

  def test_check_timeout_true(self):
    self._coordinator._latest_observation_local_time = time.time()
    time.sleep(3)
    timeout = self._coordinator.check_timeout()
    self.assertTrue(timeout)

  def test_max_restarts_adb_error(self):
    # The method was called once at init.
    init_fn_call = self._simulator.create_adb_controller.call_count
    self._simulator.create_adb_controller.side_effect = (
        errors.AdbControllerError)
    self.assertRaises(errors.TooManyRestartsError,
                      self._coordinator.restart_simulator)
    # The method was called three more times when attempting to restart.
    self.assertEqual(init_fn_call + 3,
                     self._simulator.create_adb_controller.call_count)

  def test_max_restarts_setup_steps(self):
    init_fn_call = self._task_manager.setup_task.call_count
    self._task_manager.setup_task.side_effect = errors.StepCommandError
    self.assertRaises(errors.TooManyRestartsError,
                      self._coordinator.restart_simulator)
    # The method was called three more times when attempting to restart.
    self.assertEqual(init_fn_call + 3,
                     self._task_manager.setup_task.call_count)


if __name__ == '__main__':
  absltest.main()
