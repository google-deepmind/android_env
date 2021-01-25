"""Tests for android_env.wrappers.base_wrapper."""

from absl.testing import absltest
import android_env
from android_env.wrappers import base_wrapper
import mock


class BaseWrapperTest(absltest.TestCase):

  def test_base_function_forwarding(self):
    base_env = mock.create_autospec(android_env.AndroidEnv)
    wrapped_env = base_wrapper.BaseWrapper(base_env)

    fake_ts = 'fake_ts'
    base_env.reset.return_value = fake_ts
    self.assertEqual(fake_ts, wrapped_env.reset())
    base_env.reset.assert_called_once()

    fake_ts = 'fake_ts'
    fake_action = 'fake_action'
    base_env.step.return_value = fake_ts
    self.assertEqual(fake_ts, wrapped_env.step(fake_action))
    base_env.step.assert_called_once_with(fake_action)

    fake_obs_spec = 'fake_obs_spec'
    base_env.observation_spec.return_value = fake_obs_spec
    self.assertEqual(fake_obs_spec, wrapped_env.observation_spec())
    base_env.observation_spec.assert_called_once()

    fake_action_spec = 'fake_action_spec'
    base_env.action_spec.return_value = fake_action_spec
    self.assertEqual(fake_action_spec, wrapped_env.action_spec())
    base_env.action_spec.assert_called_once()

    wrapped_env.close()
    base_env.close.assert_called_once()

    fake_return_value = 'fake'
    # AndroidEnv::some_random_function() does not exist and calling it should
    # raise an AttributeError.
    with self.assertRaises(AttributeError):
      base_env.some_random_function.return_value = fake_return_value

  def test_multiple_wrappers(self):
    base_env = mock.create_autospec(android_env.AndroidEnv)
    wrapped_env_1 = base_wrapper.BaseWrapper(base_env)
    wrapped_env_2 = base_wrapper.BaseWrapper(wrapped_env_1)

    wrapped_env_2.close()
    base_env.close.assert_called_once()

  def test_raw_env(self):
    base_env = 'fake_env'
    wrapped_env_1 = base_wrapper.BaseWrapper(base_env)
    wrapped_env_2 = base_wrapper.BaseWrapper(wrapped_env_1)
    self.assertEqual(base_env, wrapped_env_2.raw_env)

  def test_android_logs(self):
    base_env = mock.create_autospec(android_env.AndroidEnv)
    wrapped_env = base_wrapper.BaseWrapper(base_env)
    base_logs = {'base': 'logs'}
    base_env.android_logs.return_value = base_logs
    self.assertEqual(base_logs, wrapped_env.android_logs())

  def test_wrapped_android_logs(self):
    base_env = mock.create_autospec(android_env.AndroidEnv)

    class LoggingWrapper1(base_wrapper.BaseWrapper):

      def _wrapper_logs(self):
        return {
            'wrapper1': 'logs',
            'shared': 1,
        }

    class LoggingWrapper2(base_wrapper.BaseWrapper):

      def _wrapper_logs(self):
        return {
            'wrapper2': 'logs',
            'shared': 2,
        }

    wrapped_env = LoggingWrapper2(LoggingWrapper1(base_env))
    base_logs = {'base': 'logs'}
    base_env.android_logs.return_value = base_logs
    expected_logs = {
        'base': 'logs',
        'wrapper1': 'logs',
        'wrapper2': 'logs',
        'shared': 2,
    }

    self.assertEqual(expected_logs, wrapped_env.android_logs())


if __name__ == '__main__':
  absltest.main()
