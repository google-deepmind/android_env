"""Prepares and launches the emulator."""

import os
import shutil  # copybara:strip
import signal
import time

from absl import logging
from android_env.components import errors
import pexpect
from pexpect.popen_spawn import PopenSpawn

from google3.pyglib import gfile  # copybara:strip


class EmulatorLauncher():
  """Handles launching the emulator."""

  def __init__(
      self,
      local_tmp_dir: str = '/tmp',
      adb_port: int = None,
      adb_server_port: int = None,
      emulator_console_port: int = None,
      emulator_path: str = '',
      android_sdk_root: str = '',
      avd_name: str = '',
      run_headless: bool = False,
      kvm_device: str = '/dev/kvm',
      android_avd_home: str = '',
      startup_wait_time_sec: int = 80,
  ):
    """Installs required files locally and launches the emulator.

    Args:
      local_tmp_dir: Local directory for logs and maybe installing the AVD.
      adb_port: ADB port for the Android device.
      adb_server_port: Port of the ADB server deamon.
      emulator_console_port: Port for telnet communication with the emulator.
      emulator_path: Path to the emulator binary.
      android_sdk_root: Root directory of the Android SDK.
      avd_name: Name of the AVD.
      run_headless: Whether to run in headless mode.
      kvm_device: Path to the KVM device.
      android_avd_home: Local directory for AVDs.
      startup_wait_time_sec: Timeout for booting the emulator.
    """
    self._local_tmp_dir = local_tmp_dir
    self._adb_port = adb_port
    self._adb_server_port = adb_server_port
    self._emulator_console_port = emulator_console_port
    self._emulator_path = emulator_path
    self._android_sdk_root = android_sdk_root
    self._avd_name = avd_name
    self._run_headless = run_headless
    self._kvm_device = kvm_device
    self._android_avd_home = android_avd_home
    self._startup_wait_time_sec = startup_wait_time_sec
    self._emulator = None
    self._emulator_output = None

  def launch(self) -> None:
    """Launches the emulator."""
    logging.info('Booting the emulator [%s]', self._emulator_path)
    logging.info('avd: %s', self._avd_name)
    emulator_logfile = os.path.join(self._local_tmp_dir, 'emulator_output')
    # copybara:strip_begin
    self._emulator_output = gfile.Open(emulator_logfile, 'wb')
    # copybara:strip_end_and_replace_begin
    # self._emulator_output = open(emulator_logfile, 'wb')
    # copybara:replace_end
    base_lib_dir = self._emulator_path[:-8] + 'lib64/'
    ld_library_path = ':'.join([
        base_lib_dir + 'x11/', base_lib_dir + 'qt/lib/',
        base_lib_dir + 'gles_swiftshader/', base_lib_dir
    ])
    extra_env_vars = {
        'ANDROID_HOME': '',
        'ANDROID_SDK_ROOT': self._android_sdk_root,
        'ANDROID_AVD_HOME': self._android_avd_home,
        'ANDROID_EMULATOR_KVM_DEVICE': self._kvm_device,
        'ANDROID_ADB_SERVER_PORT': str(self._adb_server_port),
        'LD_LIBRARY_PATH': ld_library_path,
        'QT_DEBUG_PLUGINS': '1',
        'QT_XKB_CONFIG_ROOT': str(self._emulator_path[:-8] + 'qt_config/'),
    }
    logging.info('extra_env_vars: %s', str(extra_env_vars))
    env_vars = os.environ.copy()
    env_vars.update(extra_env_vars)

    run_headless = ['-no-skin', '-no-window'] if self._run_headless else []
    ports = ['-ports', '%s,%s' % (self._emulator_console_port, self._adb_port)]
    command = [
        self._emulator_path,
        '-no-snapshot',
        '-gpu',
        'swiftshader_indirect',
        '-no-audio',
        '-verbose',
        '-avd',
        self._avd_name,
    ] + run_headless + ports
    logging.info('Command: %s:', ' '.join(command))
    start_time = time.time()
    try:
      self._emulator = PopenSpawn(
          command, logfile=self._emulator_output, env=env_vars)
      wait_time = self._startup_wait_time_sec
      logging.info('Waiting for boot for %0.1f seconds...', wait_time)
      boot_expected_log = 'emulator: INFO: boot completed'
      self._emulator.expect(boot_expected_log, timeout=wait_time)
      logging.info('Emulator log matched: %s', self._emulator.after)
    except pexpect.ExceptionPexpect as e:
      self._print_emulator_logs()
      raise errors.SimulatorCrashError('The emulator has crashed: %r' % e)

    elapsed_time = time.time() - start_time
    logging.info('Done booting the emulator (in %f seconds).', elapsed_time)

  def restart(self) -> None:
    logging.info('Restarting the emulator...')
    self._shutdown()
    self.launch()
    logging.info('Done restarting the emulator.')

  def close(self):
    logging.info('Closing the emulator...')
    self._shutdown()
    # copybara:strip_begin
    try:
      shutil.rmtree(self._android_avd_home)
    except OSError as e:
      logging.error('Error cleaning up EmulatorLauncher: %s', e)
    # copybara:strip_end
    logging.info('Done closing the emulator.')

  def __del__(self):
    """Forces a close at deletion to properly clean local files."""
    self.close()

  def _print_emulator_logs(self) -> None:
    """Prints all buffered emulator logs. Requires self._emulator to exist."""

    logging.info('Dumping emulator logs.')
    if self._emulator.before:
      for line in self._emulator.before.decode('utf-8').split('\n'):
        logging.info(line)

  def _shutdown(self) -> None:
    if self._emulator:
      logging.info('Shutting down the emulator...')
      self._emulator.kill(signal.SIGKILL)
      self._emulator.wait()
      self._emulator_output.close()
      logging.info('Done shutting down the emulator.')
