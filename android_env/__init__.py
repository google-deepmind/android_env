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

"""AndroidEnv: The Android Interaction & Learning Platform."""

from android_env import env_interface
from android_env import loader
from android_env.components import android_device
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.rl import environment as rl_environment

__version__ = '2.0.0'

AdbControllerConfig = config_classes.AdbControllerConfig
AndroidDevice = android_device.AndroidDevice
AndroidDeviceConfig = config_classes.AndroidDeviceConfig
AndroidEnv = rl_environment.AndroidEnv
AndroidEnvConfig = config_classes.AndroidEnvConfig
AndroidEnvInterface = env_interface.AndroidEnvInterface
DeviceConnectionConfig = config_classes.DeviceConnectionConfig
EmulatorLauncherConfig = config_classes.EmulatorLauncherConfig
FilesystemTaskConfig = config_classes.FilesystemTaskConfig
TaskConfig = config_classes.TaskConfig
load = loader.load
load_android_device = android_device_loader.load_android_device

__all__ = (
    '__version__',
    'AdbControllerConfig',
    'AndroidDevice',
    'AndroidDeviceConfig',
    'AndroidEnv',
    'AndroidEnvConfig',
    'AndroidEnvInterface',
    'DeviceConnectionConfig',
    'EmulatorLauncherConfig',
    'FilesystemTaskConfig',
    'TaskConfig',
    'load',
    'load_android_device',
)
