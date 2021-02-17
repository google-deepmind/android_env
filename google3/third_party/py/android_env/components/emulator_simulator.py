"""A class that manages an Android Emulator."""

from typing import Any, Dict, Optional, List

from absl import logging
from android_env.components import base_simulator
from android_env.components import emulator_console
from android_env.components import emulator_launcher
from android_env.components import errors

import numpy as np
import portpicker


class EmulatorSimulator(base_simulator.BaseSimulator):
  """Controls an Android Emulator."""

  def __init__(self,
               emulator_launcher_args: Dict[str, Any],
               emulator_console_args: Dict[str, Any],
               **kwargs):

    self._adb_port = portpicker.pick_unused_port()
    self._console_port = portpicker.pick_unused_port()
    super().__init__(**kwargs)

    # Create EmulatorLauncher.
    emulator_launcher_args.update({
        'adb_port': self._adb_port,
        'adb_server_port': self._adb_server_port,
        'emulator_console_port': self._console_port,
        'local_tmp_dir': self._local_tmp_dir,
        'kvm_device': self._kvm_device,
    })
    logging.info('emulator_launcher_args: %r', emulator_launcher_args)
    self._launcher = emulator_launcher.EmulatorLauncher(
        **emulator_launcher_args)

    # Prepare EmulatorConsole.
    emulator_console_args.update({
        'console_port': self._console_port,
        'tmp_dir': self._local_tmp_dir,
    })
    logging.info('emulator_console_args: %r', emulator_console_args)
    self._emulator_console_args = emulator_console_args
    self._console = None

  def _start_console(self) -> None:
    self._console = emulator_console.EmulatorConsole(
        **self._emulator_console_args)

  def _restart_impl(self) -> None:
    if self._console is not None:
      self._console.close()
    self._launcher.restart()
    self._start_console()

  def _launch_impl(self) -> None:
    try:
      self._launcher.launch()
      self._start_console()
    except (errors.ConsoleConnectionError, errors.SimulatorCrashError):
      # If we fail to connect to the console on the initial launch, we try to
      # restart once.
      self.restart()

  def adb_device_name(self) -> str:
    return 'emulator-%s' % (self._adb_port - 1)

  def send_action(self, action: Dict[str, np.ndarray]) -> None:
    assert self._console, 'Console has not been initialized yet.'
    action = self._prepare_action(action)
    self._console.send_mouse_action(*action)

  def close(self):
    if self._console is not None:
      self._console.close()
    if hasattr(self, '_launcher'):
      self._launcher.close()
    super().close()

  def _get_observation(self) -> Optional[List[np.ndarray]]:
    assert self._console, 'Console has not been initialized yet.'
    return self._console.fetch_screenshot()
