# coding=utf-8
# Copyright 2023 DeepMind Technologies Limited.
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

"""Acme DQN agent interacting with AndroidEnv."""

from absl import app
from absl import flags
from absl import logging
import acme
from acme import specs
from acme import wrappers as acme_wrappers
from acme.agents.tf import dqn
from acme.tf import networks
from android_env import loader
from android_env.wrappers import discrete_action_wrapper
from android_env.wrappers import float_pixels_wrapper
from android_env.wrappers import image_rescale_wrapper

# Simulator args
flags.DEFINE_string('avd_name', None, 'Name of AVD to use.')
flags.DEFINE_string('android_avd_home', '~/.android/avd', 'Path to AVD.')
flags.DEFINE_string('android_sdk_root', '~/Android/Sdk', 'Path to SDK.')
flags.DEFINE_string('emulator_path',
                    '~/Android/Sdk/emulator/emulator', 'Path to emulator.')
flags.DEFINE_string('adb_path',
                    '~/Android/Sdk/platform-tools/adb', 'Path to ADB.')

# Environment args
flags.DEFINE_string('task_path', None, 'Path to task textproto file.')

# Experiment args
flags.DEFINE_integer('num_episodes', 100, 'Number of episodes.')

FLAGS = flags.FLAGS


def apply_wrappers(env):
  """Applies a series of wrappers to the environment."""
  env = discrete_action_wrapper.DiscreteActionWrapper(env, action_grid=(10, 10))
  env = image_rescale_wrapper.ImageRescaleWrapper(
      env, zoom_factors=(0.25, 0.25))
  env = float_pixels_wrapper.FloatPixelsWrapper(env)
  env = acme_wrappers.SinglePrecisionWrapper(env)
  return env


def main(_):

  with loader.load(
      emulator_path=FLAGS.emulator_path,
      android_sdk_root=FLAGS.android_sdk_root,
      android_avd_home=FLAGS.android_avd_home,
      avd_name=FLAGS.avd_name,
      adb_path=FLAGS.adb_path,
      task_path=FLAGS.task_path,
      run_headless=False) as env:

    env = apply_wrappers(env)
    env_spec = specs.make_environment_spec(env)

    agent = dqn.DQN(
        environment_spec=env_spec,
        network=networks.DQNAtariNetwork(
            num_actions=env_spec.actions.num_values),
        batch_size=10,
        samples_per_insert=2,
        min_replay_size=10)

    loop = acme.EnvironmentLoop(env, agent)
    loop.run(num_episodes=FLAGS.num_episodes)


if __name__ == '__main__':
  logging.set_verbosity('info')
  logging.set_stderrthreshold('info')
  flags.mark_flags_as_required(['task_path', 'avd_name'])
  app.run(main)
