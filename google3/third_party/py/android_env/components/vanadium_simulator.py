r"""A class that manages an Android on Vanadium.

For local visualization, you can connect to the simulator via VNC:

java -jar /google/data/ro/teams/cloud-android/jviewer/tightvnc-jviewer.jar \
 localhost:6444 -showConnectionDialog=No -ShowControls=No

VNC communication is currently only supported when running locally.
"""

import time
from typing import Any, Dict, Optional, List
from absl import logging

from android_env.components import base_simulator
from android_env.components import vanadium_communicator
from android_env.components import vanadium_launcher

import numpy as np
import portpicker


class VanadiumSimulator(base_simulator.BaseSimulator):
  """Controls an Android on Vanadium.
  """

  def __init__(self, vanadium_launcher_args: Dict[str, Any],
               communication_binaries_path: str, **kwargs):
    super().__init__(**kwargs)
    self._communication_binaries_path = communication_binaries_path
    self._adb_local_port = portpicker.pick_unused_port()
    self._vmm_ssh_port = portpicker.pick_unused_port()

    vanadium_launcher_args.update({
        'adb_local_port': self._adb_local_port,
        'local_tmp_dir': self._local_tmp_dir,
        'ssh_port': self._vmm_ssh_port,
        'kvm_device': self._kvm_device,
    })
    logging.info('vanadium_launcher_args: %r', vanadium_launcher_args)
    self._launcher = vanadium_launcher.VanadiumLauncher(
        **vanadium_launcher_args)
    self._communicator = None

  def adb_device_name(self) -> str:
    return 'localhost:' + str(self._adb_local_port)

  def _restart_impl(self) -> None:
    self._vanadium_close()
    self._launch_impl()

  def _launch_impl(self) -> None:
    self._launcher.launch()
    self._communicator = vanadium_communicator.VanadiumCommunicator(
        adb_control_sendevent=self.create_adb_controller(),
        adb_control_screencap=self.create_adb_controller(),
        communication_binaries_path=self._communication_binaries_path,
    )

  def send_action(self, action: Dict[str, np.ndarray]) -> None:
    assert self._communicator, 'Communicator has not been initialized yet.'

    if action is not None:
      action = self._prepare_action(action)
      self._communicator.send_mouse_action(*action)

  def _vanadium_close(self):
    if self._launcher is not None:
      self._launcher.close()
    if self._communicator is not None:
      self._communicator.close()

  def close(self):
    self._vanadium_close()
    super().close()

  def _get_observation(self) -> Optional[List[np.ndarray]]:
    assert self._communicator, 'Communicator has not been initialized yet.'
    screenshot = self._communicator.fetch_screenshot()
    timestamp_us = np.int64(time.time() * 1e6)
    return [screenshot, timestamp_us]

  def create_adb_controller(self):
    adb_control = super().create_adb_controller(
        tcp_host='localhost', tcp_port=self._adb_local_port)
    return adb_control
