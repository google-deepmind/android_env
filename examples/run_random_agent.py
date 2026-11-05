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

"""Example script demonstrating usage of AndroidEnv."""

from absl import app
from absl import flags
from absl import logging
from android_env import loader
from android_env.components import config_classes
from dm_env import specs
from ml_collections import config_flags
import numpy as np


def _default_config() -> config_classes.AndroidEnvConfig:
  """Returns the default configuration for AndroidEnv."""
  return config_classes.AndroidEnvConfig(
      task=config_classes.FilesystemTaskConfig(),
      device=config_classes.AndroidDeviceConfig(
          emulator_launcher=config_classes.EmulatorLauncherConfig(
              emulator_path='~/Android/Sdk/emulator/emulator',
              android_sdk_root='~/Android/Sdk',
              android_avd_home='~/.android/avd',
              run_headless=False,
          ),
          adb_controller=config_classes.AdbControllerConfig(
              adb_path='~/Android/Sdk/platform-tools/adb'
          ),
      ),
  )


_CONFIG = config_flags.DEFINE_config_dataclass(
    'config',
    _default_config(),
    'AndroidEnv configuration.',
)
_NUM_STEPS = flags.DEFINE_integer('num_steps', 1000, 'Number of steps to take.')


def main(_):
  with loader.load(_CONFIG.value) as env:
    action_spec = env.action_spec()

    def get_random_action() -> dict[str, np.ndarray]:
      """Returns a random AndroidEnv action."""
      action = {}
      for k, v in action_spec.items():
        if isinstance(v, specs.DiscreteArray):
          action[k] = np.random.randint(low=0, high=v.num_values, dtype=v.dtype)
        else:
          action[k] = np.random.random(size=v.shape).astype(v.dtype)
      return action

    _ = env.reset()

    for step in range(_NUM_STEPS.value):
      action = get_random_action()
      timestep = env.step(action=action)
      reward = timestep.reward
      logging.info('Step %r, action: %r, reward: %r', step, action, reward)


if __name__ == '__main__':
  logging.set_verbosity('info')
  logging.set_stderrthreshold('info')
  app.run(main)
