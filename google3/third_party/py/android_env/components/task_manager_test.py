"""Tests for task_manager.py."""

from typing import Callable, Match, Pattern

from absl.testing import absltest
from android_env.components import adb_controller
from android_env.components import dumpsys_thread
from android_env.components import logcat_thread
from android_env.components import setup_step_interpreter
from android_env.components import task_manager
from android_env.proto import task_pb2
import mock


class TaskManagerTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.addCleanup(mock.patch.stopall)  # Disable previous patches.

    self._adb_controller = mock.create_autospec(adb_controller.AdbController)
    self._setup_step_interpreter = mock.create_autospec(
        setup_step_interpreter.SetupStepInterpreter)
    self._dumpsys_thread = mock.create_autospec(dumpsys_thread.DumpsysThread)
    self._logcat_thread = mock.create_autospec(logcat_thread.LogcatThread)

    mock.patch.object(
        adb_controller, 'AdbController',
        return_value=self._adb_controller).start()
    mock.patch.object(
        setup_step_interpreter,
        'SetupStepInterpreter',
        return_value=self._setup_step_interpreter).start()
    mock.patch.object(
        dumpsys_thread, 'DumpsysThread',
        return_value=self._dumpsys_thread).start()
    mock.patch.object(
        logcat_thread, 'LogcatThread',
        return_value=self._logcat_thread).start()

  def test_setup_task(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    task_mgr.setup_task(adb_controller=self._adb_controller)
    assert hasattr(task_mgr, '_logcat_thread')
    assert hasattr(task_mgr, '_setup_step_interpreter')

  def test_get_current_reward(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    task_mgr.setup_task(adb_controller=self._adb_controller)
    task_mgr._logcat_thread.get_and_reset_reward.return_value = 1.0
    reward = task_mgr.get_current_reward()
    self.assertEqual(reward, 1.0)

  def test_get_current_reward_none(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    task_mgr.setup_task(adb_controller=self._adb_controller)
    task_mgr._logcat_thread.get_and_reset_reward.return_value = None
    reward = task_mgr.get_current_reward()
    self.assertEqual(reward, 0.0)

  def test_get_current_extras(self):
    expected_extra = {'extra': 0}
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    task_mgr.setup_task(adb_controller=self._adb_controller)
    task_mgr._logcat_thread.get_and_reset_extras.return_value = expected_extra
    extra = task_mgr.get_current_extras()
    self.assertDictEqual(extra, expected_extra)

  def test_get_current_extras_none(self):
    task_mgr = task_manager.TaskManager(task=task_pb2.Task())
    task_mgr.setup_task(adb_controller=self._adb_controller)
    task_mgr._logcat_thread.get_and_reset_extras.return_value = None
    extra = task_mgr.get_current_extras()
    self.assertDictEqual(extra, {})

  def test_check_episode_end(self):
    # Replace `LogcatThread.add_event_listener` with one that simply calls `fn`
    # right away.
    def my_add_ev_listener(event: Pattern[str],
                           fn: Callable[[Pattern[str], Match[str]], None]):
      # Check that the event matches what's expected.
      self.assertIsNotNone(event.match('I am done!'))
      fn(event, 'some_match')

    task = task_pb2.Task()
    task.log_parsing_config.log_regexps.episode_end = 'I am done!'
    task_mgr = task_manager.TaskManager(task=task)
    self._logcat_thread.add_event_listener.side_effect = my_add_ev_listener
    task_mgr.setup_task(adb_controller=self._adb_controller)
    episode_end = task_mgr.check_if_episode_ended()
    self.assertTrue(episode_end)

if __name__ == '__main__':
  absltest.main()
