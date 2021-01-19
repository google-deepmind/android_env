"""Tests for android_env.components.logcat_thread."""

import json
import subprocess
import threading

from absl.testing import absltest
from android_env.components import logcat_thread
import mock
import numpy as np


class FakeStream():
  """This class simulates the logs coming from ADB."""

  def __init__(self):
    self._values = []
    self._kill = False
    self._lock = threading.Lock()

  def send_value(self, value):
    with self._lock:
      self._values.append(value)

  def has_next_value(self):
    return bool(self._values)

  def kill(self):
    self._kill = True

  def __iter__(self):
    while True:
      if self._kill:
        return
      if not self._values:
        continue
      else:
        with self._lock:
          next_value = self._values.pop(0)
        yield next_value


class FakeProc():
  """Fake process that exposes a fake stdout stream."""

  def __init__(self):
    self.stdout = FakeStream()
    self.is_alive = True

  def kill(self):
    self.stdout.kill()
    self.is_alive = False


def make_stdout(data):
  """Returns a valid log output with given data as message."""
  return '         1553110400.424  5583  5658 D Tag: %s' % data


class LogcatThreadTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.mock_popen = self.enter_context(
        mock.patch.object(subprocess, 'Popen', autospec=True))
    self.fake_proc = FakeProc()
    self.mock_popen.return_value = self.fake_proc

  def tearDown(self):
    self.fake_proc.stdout.kill()
    super().tearDown()

  def test_base(self):
    logcat = logcat_thread.LogcatThread(adb_path='adb_bin')
    self.mock_popen.assert_called_once()
    self.assertEqual(0, logcat.get_and_reset_reward())
    self.assertEqual({}, logcat.get_and_reset_extras())
    self.assertFalse(logcat.get_and_reset_episode_end())
    self.assertIsNone(logcat.reset_counters())

  def test_cmd(self):
    _ = logcat_thread.LogcatThread(
        filters=None,
        device_name='my_device',
        adb_path='adb_bin',
        adb_port='12345')
    expected_cmd = [
        'adb_bin', '-P', '12345', '-s', 'my_device', 'logcat', '-v', 'epoch'
    ]
    self.mock_popen.assert_called_once_with(
        expected_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True)

  def test_cmd_with_filters(self):
    _ = logcat_thread.LogcatThread(filters=['filter1', 'filter2'])
    expected_cmd = [
        'adb', '-P', '5037', 'logcat', '-v', 'epoch', 'filter1', 'filter2'
    ]
    self.mock_popen.assert_called_once_with(
        expected_cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True)

  def test_kill(self):
    logcat = logcat_thread.LogcatThread()
    self.assertTrue(self.fake_proc.is_alive)
    logcat.kill()
    self.assertFalse(self.fake_proc.is_alive)

  def test_score_parsing(self):
    logcat = logcat_thread.LogcatThread()
    self.mock_popen.assert_called_once()
    self.assertEqual(0, logcat.get_and_reset_reward())
    self.fake_proc.stdout.send_value('Invalid_log_string Score: 10.0')
    self.assertEqual(0, logcat.get_and_reset_reward())
    self.fake_proc.stdout.send_value(make_stdout('Score: 10.0'))
    # Wait until the log has been processed by the thread.
    while self.fake_proc.stdout.has_next_value():
      pass
    self.assertAlmostEqual(10.0, logcat.get_and_reset_reward())
    self.assertAlmostEqual(0.0, logcat.get_and_reset_reward())
    self.fake_proc.stdout.send_value(make_stdout('Score: 15.0'))
    self.fake_proc.stdout.send_value(make_stdout('Score: 25.0'))
    while self.fake_proc.stdout.has_next_value():
      pass
    # Logcat should report the difference in score since the last flush.
    self.assertAlmostEqual(15.0, logcat.get_and_reset_reward())
    self.assertAlmostEqual(0.0, logcat.get_and_reset_reward())
    self.fake_proc.stdout.send_value(make_stdout('score: 35.0'))
    while self.fake_proc.stdout.has_next_value():
      pass
    self.assertAlmostEqual(10.0, logcat.get_and_reset_reward())

  def test_reward_parsing(self):
    logcat = logcat_thread.LogcatThread()
    self.mock_popen.assert_called_once()
    self.assertEqual(0, logcat.get_and_reset_reward())
    self.fake_proc.stdout.send_value(make_stdout('Reward: 3.0'))
    # Wait until the log has been processed by the thread.
    while self.fake_proc.stdout.has_next_value():
      pass
    self.assertAlmostEqual(3.0, logcat.get_and_reset_reward())
    self.assertAlmostEqual(0.0, logcat.get_and_reset_reward())
    self.fake_proc.stdout.send_value(make_stdout('Reward: 4.0'))
    self.fake_proc.stdout.send_value(make_stdout('Reward: 5.0'))
    self.fake_proc.stdout.send_value(make_stdout('reward: 6.0'))
    while self.fake_proc.stdout.has_next_value():
      pass
    # The reward should be accumulated between flushes.
    self.assertAlmostEqual(15.0, logcat.get_and_reset_reward())
    self.assertAlmostEqual(0.0, logcat.get_and_reset_reward())

  def test_episode_end(self):
    logcat = logcat_thread.LogcatThread()
    self.mock_popen.assert_called_once()
    self.assertEqual(False, logcat.get_and_reset_episode_end())
    self.fake_proc.stdout.send_value(make_stdout('episode end'))
    # Wait until the log has been processed by the thread.
    while self.fake_proc.stdout.has_next_value():
      pass
    self.assertEqual(True, logcat.get_and_reset_episode_end())
    self.assertEqual(False, logcat.get_and_reset_episode_end())

  def test_extras(self):
    logcat = logcat_thread.LogcatThread()
    self.mock_popen.assert_called_once()
    self.assertEqual({}, logcat.get_and_reset_extras())
    self.fake_proc.stdout.send_value(make_stdout('extra: an_extra [1,2,3]'))
    # If an extra is sent more than once, only the last value will be kept.
    self.fake_proc.stdout.send_value(make_stdout('extra: an_extra [4,5,6]'))
    self.fake_proc.stdout.send_value(make_stdout('extra: another_extra 0.5'))
    self.fake_proc.stdout.send_value(
        make_stdout('extra: multi_dimension_extra [[1,1,1],[1,1,1]]'))
    # Wait until the logs have been processed by the thread.
    while self.fake_proc.stdout.has_next_value():
      pass
    extras = logcat.get_and_reset_extras()
    np.testing.assert_almost_equal([[1, 2, 3], [4, 5, 6]],
                                   extras.get('an_extra'))
    np.testing.assert_almost_equal([0.5], extras.get('another_extra'))
    np.testing.assert_almost_equal([[[1, 1, 1], [1, 1, 1]]],
                                   extras.get('multi_dimension_extra'))
    self.assertEqual({}, logcat.get_and_reset_extras())

  def test_messsage(self):
    logcat = logcat_thread.LogcatThread()
    self.mock_popen.assert_called_once()

    self.assertFalse(logcat.has_received_message())

    logcat.listen_for_message('my_message')
    self.assertFalse(logcat.has_received_message())
    self.fake_proc.stdout.send_value(make_stdout('my_message'))
    self.fake_proc.stdout.send_value(make_stdout('another_message'))
    while self.fake_proc.stdout.has_next_value():
      pass
    self.assertTrue(logcat.has_received_message())

    logcat.listen_for_message('another_message')
    self.assertFalse(logcat.has_received_message())
    self.fake_proc.stdout.send_value(make_stdout('another_message'))
    while self.fake_proc.stdout.has_next_value():
      pass
    self.assertTrue(logcat.has_received_message())

    logcat.reset_counters()
    self.assertFalse(logcat.has_received_message())

  def test_reset(self):
    logcat = logcat_thread.LogcatThread()
    self.mock_popen.assert_called_once()
    self.fake_proc.stdout.send_value(make_stdout('extra: an_extra [1,2,3]'))
    self.fake_proc.stdout.send_value(make_stdout('Reward: 4.0'))
    self.fake_proc.stdout.send_value(make_stdout('episode end'))
    # Wait until the logs have been processed by the thread.
    while self.fake_proc.stdout.has_next_value():
      pass
    logcat.reset_counters()
    # The reset should have cleared all the values.
    self.assertEqual(0, logcat.get_and_reset_reward())
    self.assertEqual({}, logcat.get_and_reset_extras())
    self.assertFalse(logcat.get_and_reset_episode_end())

  def test_json_extras(self):
    extra = {
        'extra_scalar': 0,
        'extra_list': [1, 2, 3, 4],
        'extra_dict': {
            'foo': 'bar'
        },
        'extra_string': 'a_string'
    }
    extra_update = {'extra_string': 'a_new_string', 'extra_float': 0.6}
    # Extras send more than once will report only the latest value.
    expected_extra = {
        'extra_scalar': [0],
        'extra_list': [[1, 2, 3, 4]],
        'extra_dict': [{
            'foo': 'bar'
        }],
        'extra_string': ['a_string', 'a_new_string'],
        'extra_float': [0.6]
    }
    logcat = logcat_thread.LogcatThread()
    self.mock_popen.assert_called_once()
    self.fake_proc.stdout.send_value(
        make_stdout('json_extra: %s' % json.dumps(extra)))
    self.fake_proc.stdout.send_value(
        make_stdout('json_extra: %s' % json.dumps(extra_update)))
    while self.fake_proc.stdout.has_next_value():
      pass

    extras = logcat.get_and_reset_extras()
    np.testing.assert_almost_equal(
        expected_extra.get('extra_scalar'), extras.get('extra_scalar'))
    np.testing.assert_almost_equal(
        expected_extra.get('extra_list'), extras.get('extra_list'))
    np.testing.assert_equal(
        expected_extra.get('extra_string'), extras.get('extra_string'))
    np.testing.assert_almost_equal(
        expected_extra.get('extra_float'), extras.get('extra_float'))
    np.testing.assert_equal(
        expected_extra.get('extra_dict'), extras.get('extra_dict'))

  def test_log_prefix(self):
    logcat = logcat_thread.LogcatThread(log_prefix='prefix:')
    self.fake_proc.stdout.send_value(make_stdout('prefix: Reward: 4.0'))
    self.fake_proc.stdout.send_value(make_stdout('episode end'))
    # Wait until the logs have been processed by the thread.
    while self.fake_proc.stdout.has_next_value():
      pass
    # The reward should have been processed.
    self.assertEqual(4.0, logcat.get_and_reset_reward())
    # The episode_end should have been ignored because it lacks the prefix.
    self.assertFalse(logcat.get_and_reset_episode_end())


if __name__ == '__main__':
  absltest.main()
