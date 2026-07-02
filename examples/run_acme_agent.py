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

"""Acme JAX DQN agent interacting with AndroidEnv."""

from absl import app
from absl import flags
from absl import logging
from acme import wrappers as acme_wrappers
from acme.agents.jax import dqn
from acme.jax import experiments
from acme.jax import networks as acme_jax_networks
from acme.jax import utils as acme_jax_utils
from android_env import loader
from android_env.components import config_classes
from android_env.wrappers import discrete_action_wrapper
from android_env.wrappers import flat_interface_wrapper
from android_env.wrappers import float_pixels_wrapper
from android_env.wrappers import image_rescale_wrapper
import haiku as hk

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
flags.DEFINE_integer('num_steps', 1000, 'Number of steps to train.')

FLAGS = flags.FLAGS


def apply_wrappers(env):
  """Applies a series of wrappers to the environment."""
  env = discrete_action_wrapper.DiscreteActionWrapper(env, action_grid=(10, 10))
  env = image_rescale_wrapper.ImageRescaleWrapper(
      env, zoom_factors=(0.25, 0.25))
  env = float_pixels_wrapper.FloatPixelsWrapper(env)
  env = flat_interface_wrapper.FlatInterfaceWrapper(
      env, flat_actions=True, flat_observations=True
  )
  env = acme_wrappers.SinglePrecisionWrapper(env)
  return env


def make_network(environment_spec) -> dqn.DQNNetworks:
  """Creates networks for training DQN."""
  num_actions = environment_spec.actions.num_values
  network_fn = acme_jax_networks.dqn_atari_network(num_actions)
  network_hk = hk.without_apply_rng(hk.transform(network_fn))
  obs = acme_jax_utils.add_batch_dim(
      acme_jax_utils.zeros_like(environment_spec.observations)
  )
  network = acme_jax_networks.FeedForwardNetwork(
      init=lambda rng: network_hk.init(rng, obs), apply=network_hk.apply
  )
  typed_network = acme_jax_networks.non_stochastic_network_to_typed(network)
  return dqn.DQNNetworks(policy_network=typed_network)


def main(_):

  def env_factory(seed):
    del seed
    config = config_classes.AndroidEnvConfig(
        task=config_classes.FilesystemTaskConfig(path=FLAGS.task_path),
        simulator=config_classes.EmulatorConfig(
            emulator_launcher=config_classes.EmulatorLauncherConfig(
                emulator_path=FLAGS.emulator_path,
                android_sdk_root=FLAGS.android_sdk_root,
                android_avd_home=FLAGS.android_avd_home,
                avd_name=FLAGS.avd_name,
                run_headless=FLAGS.run_headless,
            ),
            adb_controller=config_classes.AdbControllerConfig(
                adb_path=FLAGS.adb_path
            ),
        ),
    )
    env = loader.load(config)
    env = apply_wrappers(env)
    return env

  # Construct the agent config.
  agent_config = dqn.DQNConfig(
      discount=0.99,
      eval_epsilon=0.0,
      learning_rate=5e-5,
      n_step=1,
      epsilon=0.01,
      target_update_period=2000,
      min_replay_size=10,
      max_replay_size=1000,
      samples_per_insert=2.0,
      batch_size=10,
  )

  loss_fn = dqn.PrioritizedDoubleQLearning(
      discount=agent_config.discount, max_abs_reward=1.0
  )

  dqn_builder = dqn.DQNBuilder(agent_config, loss_fn=loss_fn)

  experiment_config = experiments.ExperimentConfig(
      builder=dqn_builder,
      environment_factory=env_factory,
      network_factory=make_network,
      seed=1,
      max_num_actor_steps=FLAGS.num_steps,
  )

  experiments.run_experiment(experiment_config)


if __name__ == '__main__':
  logging.set_verbosity('info')
  logging.set_stderrthreshold('info')
  flags.mark_flags_as_required(['task_path', 'avd_name'])
  app.run(main)
