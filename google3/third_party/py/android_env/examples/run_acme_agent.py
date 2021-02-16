"""ACME agent (DQN) interacting with AndroidEnv."""

from absl import app
from absl import flags
from absl import logging
import acme
from acme import specs
from acme import wrappers as acme_wrappers
from acme.agents.tf import dqn
from acme.tf import networks
import android_env
from android_env import wrappers

# Simulator args
flags.DEFINE_string('emulator_path', None, 'Path to emulator.')
flags.DEFINE_string('android_sdk_root', None, 'Path to SDK.')
flags.DEFINE_string('android_avd_home', None, 'Path to AVD.')
flags.DEFINE_string('avd_name', None, 'Name of AVD to use.')
flags.DEFINE_string('adb_path', None, 'Path to ADB.')
flags.DEFINE_boolean('run_headless', False, 'Optionally turn off display.')

# Environment args
flags.DEFINE_string('task_path', None, 'Path to task textproto file.')

# Experiment args
flags.DEFINE_integer('num_episodes', 100, 'Number of episodes.')

FLAGS = flags.FLAGS


def apply_wrappers(env):
  """Applies a series of wrappers to the environment."""
  env = wrappers.DiscreteActionWrapper(env, action_grid=(10, 10))
  env = wrappers.ImageRescaleWrapper(env, zoom_factors=(0.25, 0.25))
  env = wrappers.FloatPixelsWrapper(env)
  env = acme_wrappers.SinglePrecisionWrapper(env)
  return env


def main(_):

  env = android_env.load(
      emulator_path=FLAGS.emulator_path,
      android_sdk_root=FLAGS.android_sdk_root,
      android_avd_home=FLAGS.android_avd_home,
      avd_name=FLAGS.avd_name,
      adb_path=FLAGS.adb_path,
      task_path=FLAGS.task_path,
      run_headless=FLAGS.run_headless,
  )
  env = apply_wrappers(env)
  env_spec = specs.make_environment_spec(env)

  agent = dqn.DQN(
      environment_spec=env_spec,
      network=networks.DQNAtariNetwork(
          num_actions=env_spec.actions.num_values),
      batch_size=10,
      samples_per_insert=2,
      min_replay_size=10)

  loop = acme.EnvironmentLoopV2(env, agent)
  loop.run(num_episodes=FLAGS.num_episodes)

  env.close()


if __name__ == '__main__':
  logging.set_verbosity('info')
  logging.set_stderrthreshold('info')
  flags.mark_flags_as_required([
      'emulator_path',
      'android_sdk_root',
      'android_avd_home',
      'avd_name',
      'adb_path',
      'task_path',
  ])
  app.run(main)
