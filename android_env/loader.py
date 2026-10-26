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

"""Function for loading AndroidEnv."""

import os

from absl import logging
from android_env import env_interface
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.proto import task_pb2
from android_env.rl import environment as rl_environment
from android_env.wrappers import task_wrapper
from google.protobuf import text_format


def _load_task(task_config: config_classes.TaskConfig) -> task_pb2.Task:
  """Returns the task according to `task_config`."""

  task = task_pb2.Task()
  match task_config:
    case config_classes.FilesystemTaskConfig():
      with open(os.path.expanduser(task_config.path), 'r') as proto_file:
        text_format.Parse(proto_file.read(), task)
    case _:
      logging.error('Unsupported TaskConfig: %r', task_config)

  return task


def load(
    config: config_classes.AndroidEnvConfig,
) -> env_interface.AndroidEnvInterface:
  """Loads an AndroidEnv instance."""

  if isinstance(config.simulator, config_classes.AndroidDeviceConfig):
    device = android_device_loader.load_android_device(config.simulator)
    env = rl_environment.AndroidEnv(device=device)
    if config.task != config_classes.TaskConfig():
      task = _load_task(config.task)
      env = task_wrapper.TaskWrapper(env, task=task, config=config.task_manager)
    return env

  raise ValueError(f'Unsupported simulator config: {config.simulator}')
