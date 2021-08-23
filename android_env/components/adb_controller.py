# coding=utf-8
# Copyright 2021 DeepMind Technologies Limited.
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

"""A class to manage and control an external ADB process."""

import os
import pathlib
import re
import subprocess
import sys
import threading
import time
from typing import List, Optional, Sequence, Tuple

from absl import logging
from android_env.components import errors
from android_env.proto import task_pb2
import pexpect

_MAX_INIT_RETRIES = 20
_INIT_RETRY_SLEEP_SEC = 2.0

_DEFAULT_TIMEOUT_SECONDS = 120.0


class AdbController():
  """Manages communication with adb."""

  def __init__(self,
               device_name: str = '',
               adb_path: str = 'adb',
               adb_server_port: int = 5037,
               prompt_regex: str = r'generic_x86:/ \$',
               default_timeout: float = _DEFAULT_TIMEOUT_SECONDS):
    """Instantiates an AdbController object.

    Args:
      device_name: Name of the device to communicate with.
      adb_path: Path to the adb binary.
      adb_server_port: Port for adb server.
      prompt_regex: Shell prompt for pexpect in ADB controller.
      default_timeout: Default timeout in seconds.
    """

    self._device_name = device_name
    self._adb_path = adb_path
    self._adb_server_port = str(adb_server_port)
    self._prompt = prompt_regex
    self._default_timeout = default_timeout

    self._platform_sys = sys.platform
    self._execute_command_lock = threading.Lock()
    self._adb_shell = None
    self._shell_is_ready = False
    # Unset problematic environment variables. ADB commands will fail if these
    # are set. They are normally exported by AndroidStudio.
    if 'ANDROID_HOME' in os.environ:
      del os.environ['ANDROID_HOME']
    if 'ANDROID_ADB_SERVER_PORT' in os.environ:
      del os.environ['ANDROID_ADB_SERVER_PORT']

  def command_prefix(self) -> List[str]:
    """The command for instantiating an adb client to this server."""
    command_prefix = [self._adb_path, '-P', self._adb_server_port]
    if self._device_name:
      command_prefix.extend(['-s', self._device_name])
    return command_prefix

  def init_server(self, timeout: Optional[float] = None):
    """Initialize the ADB server deamon on the given port.

    This function should be called immediately after initializing the first
    adb_controller, and before launching the simulator.

    Args:
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.
    """
    # Make an initial device-independent call to ADB to start the deamon.
    device_name_tmp = self._device_name
    self._device_name = ''
    self._execute_command(['devices'], timeout=timeout)
    time.sleep(0.2)
    # Subsequent calls will use the device name.
    self._device_name = device_name_tmp

  def close(self) -> None:
    """Closes internal threads and processes."""
    logging.info('Closing ADB controller...')
    if self._adb_shell is not None:
      logging.info('Killing ADB shell')
      self._adb_shell.close(force=True)
      self._adb_shell = None
      self._shell_is_ready = False
    logging.info('Done closing ADB controller.')

  def _execute_command(
      self,
      args: List[str],
      timeout: Optional[float] = None) -> Optional[bytes]:
    """Executes an adb command.

    Args:
      args: A list of strings representing each adb argument.
          For example: ['install', '/my/app.apk']
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.

    Returns:
      The output of running such command as a string, None if it fails.
    """
    # The lock here prevents commands from multiple threads from messing up the
    # output from this AdbController object.
    with self._execute_command_lock:
      if self._platform_sys == 'win32':
        adb_output = self._execute_normal_command(args, timeout=timeout)
      elif args and args[0] == 'shell':
        adb_output = self._execute_shell_command(args[1:], timeout=timeout)
      else:
        adb_output = self._execute_normal_command(args, timeout=timeout)
    logging.debug('ADB output: %s', adb_output)
    return adb_output

  def _execute_normal_command(
      self,
      args: List[str],
      timeout: Optional[float] = None) -> Optional[bytes]:
    """Executes `adb args` and returns its output."""

    timeout = self._resolve_timeout(timeout)
    command = self.command_prefix() + args
    logging.info('Executing ADB command: %s', command)

    try:
      cmd_output = subprocess.check_output(
          command, stderr=subprocess.STDOUT, timeout=timeout)
      logging.info('Done executing ADB command: %s', command)
      return cmd_output
    except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as error:
      logging.exception('Failed to execute ADB command %s', command)
      raise error

  def _execute_shell_command(
      self,
      args: List[str],
      timeout: Optional[float] = None,
      max_num_retries: int = 3) -> Optional[bytes]:
    """Execute shell command."""

    timeout = self._resolve_timeout(timeout)
    if not self._shell_is_ready:
      self._init_shell(timeout=timeout)
    shell_args = ' '.join(args)
    logging.info('Executing ADB shell command: %s', shell_args)

    num_tries = 0
    while num_tries < max_num_retries:
      num_tries += 1
      try:
        self._adb_shell.sendline(shell_args)
        self._adb_shell.expect(self._prompt, timeout=timeout)
        logging.info('Done executing ADB shell command: %s', shell_args)
        output = self._adb_shell.before.partition('\n'.encode('utf-8'))[2]
        return output
      except (pexpect.exceptions.EOF, pexpect.exceptions.TIMEOUT):
        logging.exception('Shell command failed. Reinitializing the shell.')
        logging.warning('self._adb_shell.before: %r', self._adb_shell.before)
        self._init_shell(timeout=timeout)

    logging.exception('Reinitializing the shell did not solve the issue.')
    raise errors.AdbControllerPexpectError()

  def _init_shell(self, timeout: Optional[float] = None) -> None:
    """Starts an ADB shell process.

    Args:
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.

    Raises:
        errors.AdbControllerShellInitError when adb shell cannot be initialized.
    """

    timeout = self._resolve_timeout(timeout)
    command = ' '.join(self.command_prefix() + ['shell'])
    logging.info('Initialising ADB shell with command: %s', command)

    num_tries = 0
    while num_tries < _MAX_INIT_RETRIES:
      num_tries += 1
      try:
        logging.info('Spawning ADB shell...')
        self._adb_shell = pexpect.spawn(command, use_poll=True, timeout=timeout)
        # Setting this to None prevents a 50ms wait for each sendline.
        self._adb_shell.delaybeforesend = None
        self._adb_shell.delayafterread = None
        logging.info('Done spawning ADB shell. Consuming first prompt...')
        self._adb_shell.expect(self._prompt, timeout=timeout)
        logging.info('Done consuming first prompt.')
        self._shell_is_ready = True
        return
      except (pexpect.ExceptionPexpect, ValueError) as e:
        logging.exception(e)
        logging.error('self._adb_shell.before: %r', self._adb_shell.before)
        logging.error('Could not start ADB shell. Try %r of %r.',
                      num_tries, _MAX_INIT_RETRIES)
        time.sleep(_INIT_RETRY_SLEEP_SEC)

    raise errors.AdbControllerShellInitError(
        'Failed to start ADB shell. Max number of retries reached.')

  def _wait_for_device(self,
                       max_tries: int = 20,
                       sleep_time: float = 1.0,
                       timeout: Optional[float] = None) -> None:
    """Waits for the device to be ready.

    Args:
      max_tries: Number of times to check if device is ready.
      sleep_time: Sleep time between checks, in seconds.
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.

    Returns:
      True if the device is ready, False if the device timed out.
    Raises:
      errors.AdbControllerDeviceTimeoutError when the device is not ready after
        exhausting `max_tries`.
    """
    num_tries = 0
    while num_tries < max_tries:
      ready = self._check_device_is_ready(timeout=timeout)
      if ready:
        logging.info('Device is ready.')
        return
      time.sleep(sleep_time)
      logging.error('Device is not ready.')
    raise errors.AdbControllerDeviceTimeoutError('Device timed out.')

  def _check_device_is_ready(self, timeout: Optional[float] = None) -> bool:
    """Checks if the device is ready."""
    required_services = ['window', 'package', 'input', 'display']
    for service in required_services:
      check_output = self._execute_command(
          ['shell', 'service', 'check', service],
          timeout=timeout)
      if not check_output:
        logging.error('Check for service "%s" failed.', service)
        return False
      check_output = check_output.decode('utf-8').strip()
      if check_output != f'Service {service}: found':
        logging.error(check_output)
        return False
    return True

  def _resolve_timeout(self, timeout: Optional[float]) -> float:
    """Returns the correct timeout to be used for external calls."""
    return self._default_timeout if timeout is None else timeout

  # ===== SPECIFIC COMMANDS =====

  def install_binary(self,
                     src: str,
                     dest_dir: str,
                     timeout: Optional[float] = None):
    """Installs the specified binary on the device."""
    self._execute_command(
        ['shell', 'su', '0', 'mkdir', '-p', dest_dir],
        timeout=timeout)
    self._execute_command(
        ['shell', 'su', '0', 'chown', '-R', 'shell:', dest_dir],
        timeout=timeout)
    bin_name = pathlib.PurePath(src).name
    dest = pathlib.PurePath(dest_dir) / bin_name
    self.push_file(src, str(dest), timeout=timeout)

  def install_apk(self,
                  local_apk_path: str,
                  timeout: Optional[float] = None) -> None:
    """Installs an app given a `local_apk_path` in the filesystem.

    This function checks that `local_apk_path` exists in the file system, and
    will raise an exception in case it doesn't.

    Args:
      local_apk_path: Path to .apk file in the local filesystem.
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.
    """
    assert os.path.exists(local_apk_path), (
        'Could not find local_apk_path :%r' % local_apk_path)
    self._execute_command(['install', '-r', '-t', '-g', local_apk_path],
                          timeout=timeout)

  def uninstall_package(self,
                        package_name: str,
                        timeout: Optional[float] = None) -> None:
    """Uninstalls an app if it is already installed."""
    if self.is_package_installed(package_name, timeout):
      self._execute_command(['uninstall', package_name], timeout=timeout)

  def is_package_installed(self,
                           package_name: str,
                           timeout: Optional[float] = None) -> bool:
    """Checks that the given package is installed."""
    packages = self._execute_command(
        ['shell', 'pm', 'list', 'packages'], timeout=timeout)
    if not packages:
      return False
    packages = packages.decode('utf-8').split()
    # Remove 'package:' prefix for each package.
    packages = [pkg[8:] for pkg in packages if pkg[:8] == 'package:']
    logging.info('Installed packages: %r', packages)
    if package_name in packages:
      logging.info('Package %s found.', package_name)
      return True
    return False

  def start_activity(self,
                     full_activity: str,
                     extra_args: Optional[List[str]],
                     timeout: Optional[float] = None):
    if extra_args is None:
      extra_args = []
    self._execute_command(
        ['shell', 'am', 'start', '-S', '-n', full_activity] + extra_args,
        timeout=timeout)

  def start_intent(self,
                   action: str,
                   data_uri: str,
                   package_name: str,
                   timeout: Optional[float] = None):
    self._execute_command(
        ['shell', 'am', 'start', '-a', action, '-d', data_uri, package_name],
        timeout=timeout)

  def start_accessibility_service(self,
                                  accessibility_service_full_name,
                                  timeout: Optional[float] = None):
    self._execute_command(
        ['shell', 'settings', 'put', 'secure', 'enabled_accessibility_services',
         accessibility_service_full_name], timeout=timeout)

  def broadcast(self,
                receiver: str,
                action: str,
                extra_args: Optional[List[str]],
                timeout: Optional[float] = None):
    if extra_args is None:
      extra_args = []
    self._execute_command(
        ['shell', 'am', 'broadcast', '-n', receiver, '-a', action] + extra_args,
        timeout=timeout)

  def setprop(self,
              prop_name: str,
              value: str,
              timeout: Optional[float] = None):
    self._execute_command(
        ['shell', 'setprop', prop_name, value], timeout=timeout)

  def push_file(self, src: str, dest: str, timeout: Optional[float] = None):
    self._execute_command(
        ['push', src, dest], timeout=timeout)

  def force_stop(self, package: str, timeout: Optional[float] = None):
    self._execute_command(
        ['shell', 'am', 'force-stop', package], timeout=timeout)

  def clear_cache(self, package: str, timeout: Optional[float] = None):
    self._execute_command(
        ['shell', 'pm', 'clear', package], timeout=timeout)

  def grant_permissions(self,
                        package: str,
                        permissions: Sequence[str],
                        timeout: Optional[float] = None):
    for permission in permissions:
      logging.info('Granting permission: %r', permission)
      self._execute_command(
          ['shell', 'pm', 'grant', package, permission], timeout=timeout)

  def get_activity_dumpsys(self,
                           package_name: str,
                           timeout: Optional[float] = None) -> Optional[str]:
    """Returns the activity's dumpsys output in a UTF-8 string."""
    dumpsys_activity_output = self._execute_command(
        ['shell', 'dumpsys', 'activity', package_name, package_name],
        timeout=timeout)
    if dumpsys_activity_output:
      return dumpsys_activity_output.decode('utf-8')

  def get_current_activity(self,
                           timeout: Optional[float] = None) -> Optional[str]:
    """Returns the full activity name that is currently opened to the user.

    The format of the output is `package/package.ActivityName', for example:
    "com.example.vokram/com.example.vokram.MainActivity"

    Args:
      timeout: A timeout to use for this operation. If not set the default
        timeout set on the constructor will be used.

    Returns:
      None if no current activity can be extracted.
    """
    visible_task = self._execute_command(
        ['shell', 'am', 'stack', 'list', '|', 'grep', '-E', 'visible=true'],
        timeout=timeout)

    if not visible_task:
      am_stack_list = self._execute_command(
          ['shell', 'am', 'stack', 'list'],
          timeout=timeout)
      logging.error('Empty visible_task. `am stack list`: %r', am_stack_list)
      return None

    visible_task = visible_task.decode('utf-8')
    if self._platform_sys == 'win32':
      visible_task_list = re.findall(
          r'visible=true topActivity=ComponentInfo{(.+?)}', visible_task)
      if not visible_task_list:
        visible_task = ''
      else:
        visible_task = 'ComponentInfo{' + visible_task_list[0] + '}'

    p = re.compile(r'.*\{(.*)\}')
    matches = p.search(visible_task)
    if matches is None:
      logging.error(
          'Could not extract current activity. Will return nothing. '
          '`am stack list`: %r',
          self._execute_command(['shell', 'am', 'stack', 'list'],
                                timeout=timeout))
      return None

    return matches.group(1)

  def start_screen_pinning(self,
                           full_activity: str,
                           timeout: Optional[float] = None):
    current_task_id = self._fetch_current_task_id(full_activity, timeout)
    if current_task_id == -1:
      logging.info('Could not find task ID for activity [%r]', full_activity)
      raise errors.AdbControllerScreenPinningError
    self._execute_command(
        ['shell', 'am', 'task', 'lock', str(current_task_id)], timeout=timeout)

  def _fetch_current_task_id(self,
                             full_activity_name: str,
                             timeout: Optional[float] = None) -> int:
    """Returns the task ID of the given `full_activity_name`."""
    stack = self._execute_command(
        ['shell', 'am', 'stack', 'list'], timeout=timeout)
    stack_utf8 = stack.decode('utf-8')
    lines = stack_utf8.splitlines()

    if self._platform_sys == 'win32':
      regex = re.compile(
          r'^\ *taskId=(?P<id>[0-9]*): .* visible=true .*{%s}.*' %
          full_activity_name)
    else:
      regex = re.compile(
          r'^\ *taskId=(?P<id>[0-9]*): %s.*visible=true.*$' %
          full_activity_name)

    matches = [regex.search(line) for line in lines]
    for match in matches:
      if match is None:
        continue
      current_task_id_str = match.group('id')
      try:
        current_task_id = int(current_task_id_str)
        return current_task_id
      except ValueError:
        logging.info('Failed to parse task ID [%r].', current_task_id_str)
    logging.error('Could not find current activity in stack list: %r',
                  stack_utf8)
    # At this point if we could not find a task ID, there's nothing we can do.
    return -1

  def get_screen_dimensions(self,
                            timeout: Optional[float] = None) -> Tuple[int, int]:
    """Returns a (height, width)-tuple representing a screen size in pixels."""
    logging.info('Fetching screen dimensions...')
    self._wait_for_device(timeout=timeout)
    adb_output = self._execute_command(['shell', 'wm', 'size'], timeout=timeout)
    assert adb_output, 'Empty response from ADB for screen size.'
    adb_output = adb_output.decode('utf-8')
    # adb_output should be of the form "Physical size: 320x480".
    physical = re.match(r'.*Physical\ssize:\s([0-9]+x[0-9]+).*', adb_output)
    override = re.match(r'.*\nOverride\ssize:\s([0-9]+x[0-9]+).*', adb_output)
    dims_match = override or physical
    assert dims_match, f'Failed to match the screen dimensions. {adb_output}'
    dims = dims_match.group(1)
    logging.info('width x height: %s', dims)
    width, height = tuple(map(int, dims.split('x')))  # Split between W & H
    logging.info('Done fetching screen dimensions: (H x W) = (%r, %r)',
                 height, width)
    return (height, width)

  def get_orientation(self, timeout: Optional[float] = None) -> Optional[str]:
    """Returns the device orientation."""
    logging.info('Getting orientation...')
    dumpsys = self._execute_command(
        ['shell', 'dumpsys', 'input'], timeout=timeout)
    logging.info('dumpsys: %r', dumpsys)
    if not dumpsys:
      logging.error('Empty dumpsys.')
      return None
    dumpsys = dumpsys.decode('utf-8')
    lines = dumpsys.split('\n')  # Split by lines.
    skip_next = False
    for line in lines:
      # There may be multiple devices in dumpsys. An invalid device can be
      # identified by negative PhysicalWidth.
      physical_width = re.match(r'\s+PhysicalWidth:\s+(-?\d+)px', line)
      if physical_width:
        skip_next = int(physical_width.group(1)) < 0

      surface_orientation = re.match(r'\s+SurfaceOrientation:\s+(\d)', line)
      if surface_orientation is not None:
        if skip_next:
          continue
        orientation = surface_orientation.group(1)
        logging.info('Done getting orientation: %r', orientation)
        return orientation

    logging.error('Could not get the orientation. Returning None.')
    return None

  def rotate_device(self,
                    orientation: task_pb2.AdbCall.Rotate.Orientation,
                    timeout: Optional[float] = None) -> None:
    """Sets the device to the given `orientation`."""
    self._execute_command(
        ['shell', 'settings', 'put', 'system', 'user_rotation',
         str(orientation)], timeout=timeout)

  def set_touch_indicators(self,
                           show_touches: bool = True,
                           pointer_location: bool = True,
                           timeout: Optional[float] = None) -> None:
    """Sends command to turn touch indicators on/off."""
    logging.info('Setting show_touches indicator to %r', show_touches)
    logging.info('Setting pointer_location indicator to %r', pointer_location)
    show_touches = 1 if show_touches else 0
    pointer_location = 1 if pointer_location else 0
    self._wait_for_device(timeout=timeout)
    self._execute_command([
        'shell', 'settings', 'put', 'system', 'show_touches',
        str(show_touches)], timeout=timeout)
    self._execute_command([
        'shell', 'settings', 'put', 'system', 'pointer_location',
        str(pointer_location)], timeout=timeout)

  def set_bar_visibility(self,
                         navigation: bool = False,
                         status: bool = False,
                         timeout: Optional[float] = None) -> Optional[bytes]:
    """Show or hide navigation and status bars."""
    command = ['shell', 'settings', 'put', 'global', 'policy_control']
    if status and navigation:  # Show both bars.
      command += ['null*']
    elif not status and navigation:  # Hide status(top) bar.
      command += ['immersive.status=*']
    elif status and not navigation:  # Hide navigation(bottom) bar.
      command += ['immersive.navigation=*']
    else:  # Hide both bars.
      command += ['immersive.full=*']

    return self._execute_command(command, timeout=timeout)

  def disable_animations(self, timeout: Optional[float] = None):
    self._execute_command(
        ['shell', 'settings put global window_animation_scale 0.0'],
        timeout=timeout)
    self._execute_command(
        ['shell', 'settings put global transition_animation_scale 0.0'],
        timeout=timeout)
    self._execute_command(
        ['shell', 'settings put global animator_duration_scale 0.0'],
        timeout=timeout)

  def input_tap(self, x: int, y: int, timeout: Optional[float] = None) -> None:
    self._execute_command(
        ['shell', 'input', 'tap', str(x), str(y)], timeout=timeout)

  def input_text(self,
                 input_text: str,
                 timeout: Optional[float] = None) -> Optional[bytes]:
    return self._execute_command(
        ['shell', 'input', 'text', input_text], timeout=timeout)

  def input_key(self,
                key_code: str,
                timeout: Optional[float] = None) -> Optional[bytes]:
    """Presses a keyboard key.

    Please see https://developer.android.com/reference/android/view/KeyEvent for
    values of `key_code`.

    We currently only accept:

    KEYCODE_HOME (constant 3)
    KEYCODE_BACK (constant 4)
    KEYCODE_ENTER (constant 66)

    Args:
      key_code: The keyboard key to press.
      timeout: Optional time limit in seconds.

    Returns:
      The output of running such command as a string, None if it fails.
    """
    accepted_key_codes = ['KEYCODE_HOME', 'KEYCODE_BACK', 'KEYCODE_ENTER']
    assert key_code in accepted_key_codes, ('Rejected keycode: %r' % key_code)

    return self._execute_command(['shell', 'input', 'keyevent', key_code],
                                 timeout=timeout)
