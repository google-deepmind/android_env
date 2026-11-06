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
from android_env.wrappers import tap_action_wrapper
import haiku as hk
from ml_collections import config_flags


def _default_config() -> config_classes.AndroidEnvConfig:
  """Returns the default configuration for AndroidEnv."""
  return config_classes.AndroidEnvConfig(
      task=config_classes.FilesystemTaskConfig(),
      device=config_classes.AndroidDeviceConfig(
          adb_path='~/Android/Sdk/platform-tools/adb',
          emulator_launcher=config_classes.EmulatorLauncherConfig(
              emulator_path='~/Android/Sdk/emulator/emulator',
              android_sdk_root='~/Android/Sdk',
              android_avd_home='~/.android/avd',
              run_headless=False,
          ),
      ),
  )


_CONFIG = config_flags.DEFINE_config_dataclass(
    'config',
    _default_config(),
    'AndroidEnv configuration.',
)
_NUM_STEPS = flags.DEFINE_integer(
    'num_steps', 1000, 'Number of steps to train.'
)


def apply_wrappers(env):
  """Applies a series of wrappers to the environment."""
  env = tap_action_wrapper.TapActionWrapper(env, touch_only=True)
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
    env = loader.load(_CONFIG.value)
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
      max_num_actor_steps=_NUM_STEPS.value,
  )

  experiments.run_experiment(experiment_config)


if __name__ == '__main__':
  logging.set_verbosity('info')
  logging.set_stderrthreshold('info')
  app.run(main)
