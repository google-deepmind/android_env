"""Function for loading AndroidEnv."""

import os

from android_env import android_env
from android_env.components import emulator_simulator
from android_env.proto import task_pb2

from google3.net.proto2.python.public import text_format


def load(adb_path: str,
         emulator_path: str,
         android_sdk_root: str,
         android_avd_home: str,
         avd_name: str,
         task_path: str,
         run_headless: bool = False) -> android_env.AndroidEnv:
  """Loads an AndroidEnv instance."""

  # Create simulator.
  simulator = emulator_simulator.EmulatorSimulator(
      emulator_launcher_args=dict(
          emulator_path=os.path.expanduser(emulator_path),
          android_sdk_root=os.path.expanduser(android_sdk_root),
          android_avd_home=os.path.expanduser(android_avd_home),
          avd_name=avd_name,
          run_headless=run_headless,
          gpu_mode='swiftshader_indirect',
      ),
      emulator_console_args={},
      adb_path=adb_path,
      adb_server_port=5037,
      prompt_regex=r'\w*:\/ \$',
  )

  # Prepare task.
  task = task_pb2.Task()
  with open(task_path, 'r') as proto_file:
    text_format.Parse(proto_file.read(), task)

  # Load environment.
  return android_env.AndroidEnv(
      simulator=simulator,
      task=task,
  )
