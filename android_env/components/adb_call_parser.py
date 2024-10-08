# coding=utf-8
# Copyright 2024 DeepMind Technologies Limited.
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

"""Processes adb_pb2.AdbRequest commands."""

import os
import re
import subprocess
import sys
import tempfile

from absl import logging
from android_env.components import adb_controller as adb_control
from android_env.proto import adb_pb2

# A mapping from a Button enum to keycode strings.
#
# Please see https://developer.android.com/reference/android/view/KeyEvent
#
# We currently only accept the following entries:
_BUTTON_TO_KEYCODE = {
    adb_pb2.AdbRequest.PressButton.Button.HOME: 'KEYCODE_HOME',
    adb_pb2.AdbRequest.PressButton.Button.BACK: 'KEYCODE_BACK',
    adb_pb2.AdbRequest.PressButton.Button.ENTER: 'KEYCODE_ENTER',
}


class AdbCallParser:
  """Parses AdbRequest messages and executes corresponding adb commands."""

  def __init__(self, adb_controller: adb_control.AdbController):
    self._adb_controller = adb_controller
    self._handlers = {
        'install_apk': self._install_apk,
        'start_activity': self._start_activity,
        'force_stop': self._force_stop,
        'tap': self._tap,
        'press_button': self._press_button,
        'start_screen_pinning': self._start_screen_pinning,
        'send_broadcast': self._send_broadcast,
        'uninstall_package': self._handle_uninstall_package,
        'get_current_activity': self._get_current_activity,
        'get_orientation': self._get_orientation,
        'push': self._push,
        'pull': self._pull,
        'input_text': self._input_text,
        'settings': self._handle_settings,
        'generic': self._handle_generic,
        'package_manager': self._handle_package_manager,
        'dumpsys': self._handle_dumpsys,
    }

  def _execute_command(
      self, command_args: list[str], timeout: float | None
  ) -> tuple[adb_pb2.AdbResponse, bytes]:
    """Executes the command, catches errors and populates the response status.

    Args:
      command_args: a list of arguments for the ADB request.
      timeout: Timeout in seconds.

    Returns:
      A tuple of the AdbResponse with the status populated, and the output
      bytes from the command.
    """
    response = adb_pb2.AdbResponse(status=adb_pb2.AdbResponse.Status.OK)
    command_output = b''
    try:
      command_output = self._adb_controller.execute_command(
          command_args, timeout=timeout)
    except subprocess.CalledProcessError as adb_error:
      if adb_error.stdout is not None:
        response.status = adb_pb2.AdbResponse.Status.ADB_ERROR
        response.error_message = adb_error.stdout
    except subprocess.TimeoutExpired:
      response.status = adb_pb2.AdbResponse.Status.TIMEOUT
      response.error_message = 'Timeout'

    return response, command_output

  def parse(self, request: adb_pb2.AdbRequest) -> adb_pb2.AdbResponse:
    """Executes `request` and returns an appropriate response."""

    response = adb_pb2.AdbResponse(status=adb_pb2.AdbResponse.Status.OK)
    command_type = request.WhichOneof('command')
    logging.info('AdbRequest command type: %s', command_type)
    if command_type is None:
      response.status = adb_pb2.AdbResponse.Status.UNKNOWN_COMMAND
      response.error_message = 'AdbRequest.command is None.'
      return response

    if request.timeout_sec < 0:
      response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
      response.error_message = ('AdbRequest.timeout_sec cannot be negative. '
                                f'Got: {request.timeout_sec}')
      return response

    timeout: float | None = request.timeout_sec or None
    return self._handlers[command_type](request, timeout)

  def _force_stop(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Stops an application.

    Args:
      request: The external request containing the package to force stop.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse.
    """

    force_stop = request.force_stop
    response = adb_pb2.AdbResponse(status=adb_pb2.AdbResponse.Status.OK)
    if not force_stop.package_name:
      response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
      response.error_message = '`force_stop.package_name` cannot be empty.'
      return response

    response, _ = self._execute_command(
        ['shell', 'am', 'force-stop', force_stop.package_name], timeout)

    return response

  def _fetch_current_task_id(
      self, full_activity_name: str, timeout: float | None = None
  ) -> int:
    """Returns the task ID of the given `full_activity_name`.

    Args:
      full_activity_name: The full name of the activity whose corresponding
        task id we are looking for.
      timeout: Optional time limit in seconds.
    Returns:
      task_id: An integer corresponding to the specified activity.
    """

    stack = self._adb_controller.execute_command(
        ['shell', 'am', 'stack', 'list'], timeout=timeout)
    lines = stack.decode('utf-8').splitlines()

    regex = re.compile(
        r'^\ *taskId=(?P<id>[0-9]*): (?P<base_activity>[^\s]*) .*visible=true'
        r'.*topActivity=ComponentInfo{(?P<top_activity>[^\s]*)}$')

    for line in lines:
      match = regex.search(line)
      if match is None:
        continue

      current_task_id_str = match.group('id')
      base_activity = match.group('base_activity')
      top_activity = match.group('top_activity')

      # If neither of the matched activities equals the activity we are
      # looking for, we discard their task id and continue the search.
      if full_activity_name not in {base_activity, top_activity}:
        logging.info('Full activity %s was not found in current line %s',
                     full_activity_name, line)
        continue

      # Otherwise return the integer task id.
      try:
        return int(current_task_id_str)
      except ValueError:
        logging.info('Failed to parse task ID [%r].', current_task_id_str)

    # At this point if we could not find a task ID, there's nothing we can do.
    logging.error('Could not find current activity in stack list: %r', lines)
    return -1

  def _start_screen_pinning(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Pins an application.

    Args:
      request: The request containing the activity to pin.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse.
    """

    full_activity = request.start_screen_pinning.full_activity
    response = adb_pb2.AdbResponse(status=adb_pb2.AdbResponse.Status.OK)
    if not full_activity:
      response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
      response.error_message = (
          '`start_screen_pinning.full_activity` cannot be empty.')
      return response

    current_task_id = self._fetch_current_task_id(full_activity, timeout)
    if current_task_id == -1:
      response.status = adb_pb2.AdbResponse.Status.INTERNAL_ERROR
      response.error_message = ('Could not find task ID for activity '
                                f'[{full_activity}]')
      return response

    response, _ = self._execute_command(
        ['shell', 'am', 'task', 'lock',
         str(current_task_id)], timeout=timeout)

    return response

  def _send_broadcast(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Sends a broadcast.

    Args:
      request: The request with the information for the broadcast event.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse.
    """

    send_broadcast = request.send_broadcast
    response = adb_pb2.AdbResponse(status=adb_pb2.AdbResponse.Status.OK)
    if not send_broadcast.action:
      response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
      response.error_message = ('`send_broadcast.{action}` cannot be empty.')
      return response

    if send_broadcast.component:
      component_args = ['-n', send_broadcast.component]
    else:
      component_args = []

    response, _ = self._execute_command(
        ['shell', 'am', 'broadcast', '-a', send_broadcast.action]
        + component_args,
        timeout=timeout,
    )

    return response

  def _install_apk(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Installs an app given its local path in the filesystem.

    Args:
      request: The external request with an install_apk field.
        Contains information for the .apk installation.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse.
    """

    install_apk = request.install_apk
    response = adb_pb2.AdbResponse()
    location_type = install_apk.WhichOneof('location')
    logging.info('location_type: %s', location_type)

    match location_type:
      case 'filesystem':
        fpath = install_apk.filesystem.path
        if not os.path.exists(fpath):
          response.status = adb_pb2.AdbResponse.Status.INTERNAL_ERROR
          response.error_message = f'Could not find local_apk_path: {fpath}'
          return response

        response, _ = self._execute_command(
            ['install', '-r', '-t', '-g', fpath], timeout=timeout
        )
      case 'blob':
        with tempfile.NamedTemporaryFile(suffix='.apk') as f:
          fpath = f.name
          f.write(install_apk.blob.contents)

          response, _ = self._execute_command(
              ['install', '-r', '-t', '-g', fpath], timeout=timeout
          )
      case _:
        response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
        response.error_message = (
            f'Unsupported `install_apk.location` type: {location_type}'
        )
        return response

    return response

  def _start_activity(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Starts a given activity.

    Options for `start_activity`:
      `am start` command options:
      -D: enable debugging
      -W: wait for launch to complete
      --start-profiler <FILE>: start profiler and send results to <FILE>
      -P <FILE>: like above, but profiling stops when app goes idle
      -R: repeat the activity launch <COUNT> times.  Prior to each repeat,
          the top activity will be finished.
      -S: force stop the target app before starting the activity
      --opengl-trace: enable tracing of OpenGL functions

    Args:
      request: The request with information on what activity to start.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse. If successful, StartActivityResponse will contain the
      activity name and adb command output.
    """

    activity = request.start_activity.full_activity
    if not activity:
      return adb_pb2.AdbResponse(
          status=adb_pb2.AdbResponse.Status.FAILED_PRECONDITION,
          error_message='`start_activity.full_activity` cannot be empty.')

    force_stop = '-S' if request.start_activity.force_stop else ''
    response, command_output = self._execute_command(
        ['shell', 'am', 'start', force_stop, '-W', '-n', activity] +
        list(request.start_activity.extra_args or []),
        timeout=timeout)

    # Check command output for potential errors.
    expected_error = re.compile(r""".*Error.*""", re.VERBOSE)
    if expected_error.match(str(command_output)):
      return adb_pb2.AdbResponse(
          status=adb_pb2.AdbResponse.Status.INTERNAL_ERROR,
          error_message=f'start_activity failed with error: {command_output}')

    response.start_activity.full_activity = activity
    response.start_activity.output = command_output
    return response

  def _press_button(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Presses a keyboard key.

    Args:
      request: The request with information on what button to press.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse.
    """

    button = request.press_button.button
    if button not in _BUTTON_TO_KEYCODE:
      return adb_pb2.AdbResponse(
          status=adb_pb2.AdbResponse.Status.FAILED_PRECONDITION,
          error_message=('PressButton.button must be one of '
                         f'[{_BUTTON_TO_KEYCODE.keys()}]. '
                         f'Got: {button}. Please see `adb.proto`.'))

    keycode = _BUTTON_TO_KEYCODE[button]
    response, command_output = self._execute_command(
        ['shell', 'input', 'keyevent', keycode], timeout=timeout)
    response.press_button.output = command_output
    return response

  def _handle_uninstall_package(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Handles UninstallPackage messages.

    Args:
      request: The specification of what to uninstall.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse
    """

    package_name = request.uninstall_package.package_name
    response = adb_pb2.AdbResponse()
    # Every UninstallPackage should have a package_name.
    if not package_name:
      response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
      response.error_message = (
          '`uninstall_package.package_name` cannot be empty.')
      return response

    # Get list of installed packages and issue an uninstall only if it's
    # already installed.
    package_response = self._handle_package_manager(
        adb_pb2.AdbRequest(
            package_manager=adb_pb2.AdbRequest.PackageManagerRequest(
                list=adb_pb2.AdbRequest.PackageManagerRequest.List(
                    packages=adb_pb2.AdbRequest.PackageManagerRequest.List
                    .Packages()))))
    if package_name in package_response.package_manager.list.items:
      response, _ = self._execute_command(['uninstall', package_name], timeout)
    else:
      msg = (f'Cannot uninstall {package_name} since it is not installed.')
      logging.warning(msg)
      response.error_message = msg

    return response

  def _get_current_activity(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Fetches current activity.

    Args:
      request: The request with the `.get_current_activity` field set. This is
        unused, but it's in the signature so that all calls are uniform.
      timeout: Optional time limit in seconds.

    Returns:
      AdbResponse containing the current activity.
    """

    del request  # Unused.

    response, visible_task = self._execute_command(
        ['shell', 'am', 'stack', 'list', '|', 'grep', '-E', 'visible=true'],
        timeout=timeout)

    if response.status != adb_pb2.AdbResponse.Status.OK:
      return response

    if not visible_task:
      _, am_stack_list = self._execute_command(['shell', 'am', 'stack', 'list'],
                                               timeout=timeout)
      response.status = adb_pb2.AdbResponse.Status.INTERNAL_ERROR
      response.error_message = ('Empty visible_task. `am stack list`: '
                                f'{am_stack_list}')
      return response

    visible_task = visible_task.decode('utf-8')
    if sys.platform == 'win32':
      visible_task_list = re.findall(
          r'visible=true topActivity=ComponentInfo{(.+?)}', visible_task)
      if not visible_task_list:
        visible_task = ''
      else:
        visible_task = 'ComponentInfo{' + visible_task_list[0] + '}'

    p = re.compile(r'.*\{(.*)\}')
    matches = p.search(visible_task)
    if matches is None:
      _, am_stack_list = self._execute_command(['shell', 'am', 'stack', 'list'],
                                               timeout=timeout)
      response.status = adb_pb2.AdbResponse.Status.INTERNAL_ERROR
      response.error_message = (
          'Could not extract current activity. Will return nothing. '
          f'`am stack list`: {am_stack_list}')
      return response

    response.get_current_activity.full_activity = matches.group(1)
    return response

  def _get_orientation(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Fetches current device orientation.

    Args:
      request: The request with the `.get_orientation` field set.
      timeout: Optional time limit in seconds.

    Returns:
      AdbResponse containing the current device orientation. This is
          unused, but it's in the signature so that all calls are uniform.
    """

    del request  # Unused.

    logging.info('Getting orientation...')
    response = self._handle_dumpsys(
        adb_pb2.AdbRequest(
            dumpsys=adb_pb2.AdbRequest.DumpsysRequest(service='input')),
        timeout=timeout)
    output = response.dumpsys.output
    if not output:
      logging.error('Empty dumpsys output.')
      response.status = adb_pb2.AdbResponse.Status.INTERNAL_ERROR
      response.error_message = 'Failed to execute `dumpsys input`'
      return response

    output = output.decode('utf-8')
    lines = output.split('\n')  # Split by lines.
    skip_next = False
    for line in lines:
      # There may be multiple devices in output. An invalid device can be
      # identified by negative PhysicalWidth.
      physical_width = re.match(r'\s+PhysicalWidth:\s+(-?\d+)px', line)
      if physical_width:
        skip_next = int(physical_width.group(1)) < 0

      surface_orientation = re.match(
          r'\s+(SurfaceOrientation|InputDeviceOrientation):\s+(\d)', line
      )

      if surface_orientation is not None:
        if skip_next:
          continue
        if surface_orientation.re.groups < 2:
          continue
        orientation = surface_orientation.group(2)
        logging.info('Done getting orientation: %r', orientation)
        response.get_orientation.orientation = int(orientation)
        return response

    response.status = adb_pb2.AdbResponse.Status.INTERNAL_ERROR
    response.error_message = (
        'Could not find SurfaceOrientation/InputDeviceOrientation in dumpsys '
        'output'
    )
    return response

  def _push(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Uploads contents to the device.

    Args:
      request: The request with the contents to push to the device.
      timeout: Optional time limit in seconds.

    Returns:
      An empty AdbResponse.
    """

    path = request.push.path
    if not path:
      return adb_pb2.AdbResponse(
          status=adb_pb2.AdbResponse.Status.FAILED_PRECONDITION,
          error_message='Push.path is empty.')

    # Create temporary file with `push` contents.
    with tempfile.NamedTemporaryFile(delete=False) as f:
      fname = f.name
      f.write(request.push.content)
    # Issue `adb push` command to upload file.
    logging.info('Uploading %r to %r.', fname, path)
    response, _ = self._execute_command(['push', fname, path], timeout=timeout)
    # Delete it.
    os.remove(fname)

    return response

  def _pull(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Downloads file content from the device.

    Args:
      request: The request with the information on what to get from the device.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse with the contents of the specified file.
    """

    path = request.pull.path
    if not path:
      return adb_pb2.AdbResponse(
          status=adb_pb2.AdbResponse.Status.FAILED_PRECONDITION,
          error_message='Pull.path is empty.')

    # Issue `adb pull` command to copy it to a temporary file.
    with tempfile.NamedTemporaryFile(delete=False) as f:
      fname = f.name
      logging.info('Downloading %r to %r.', path, fname)
      response, _ = self._execute_command(['pull', path, fname],
                                          timeout=timeout)
    # Read the content of the file.
    with open(fname, 'rb') as f:
      response.pull.content = f.read()
    # Delete it.
    os.remove(fname)

    return response

  def _input_text(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Inserts text as keyboard events.

    Args:
      request: The external request.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse
    """

    text = request.input_text.text
    if not text:
      return adb_pb2.AdbResponse(
          status=adb_pb2.AdbResponse.Status.FAILED_PRECONDITION,
          error_message='InputText.text is empty.')

    response, _ = self._execute_command(['shell', 'input', 'text', text],
                                        timeout=timeout)
    return response

  def _tap(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Taps the device screen.

    Args:
      request: The request with information on where to tap the screen.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse
    """

    x = request.tap.x
    y = request.tap.y
    # Check for negative coordinates.
    # Notice that zero coordinates are valid coordinates (i.e. the first
    # column/row of the screen).
    if x < 0 or y < 0:
      return adb_pb2.AdbResponse(
          status=adb_pb2.AdbResponse.Status.FAILED_PRECONDITION,
          error_message=(
              f'Tap coordinates must be non-negative. Got: {request.tap}.'))

    response, _ = self._execute_command(
        ['shell', 'input', 'tap', str(x),
         str(y)], timeout=timeout)

    return response

  def _handle_settings(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Handles SettingsRequest messages.

    Args:
      request: The specification of what to do with settings.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse
    """

    request = request.settings
    response = adb_pb2.AdbResponse()
    # Every SettingsRequest should have a namespace.
    if request.name_space == adb_pb2.AdbRequest.SettingsRequest.Namespace.UNKNOWN:
      response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
      response.error_message = (
          f'Unknown SettingsRequest.name_space. Got: {request}.')
      return response

    namespace = adb_pb2.AdbRequest.SettingsRequest.Namespace.Name(
        request.name_space).lower()

    match request.WhichOneof('verb'):
      case 'get':
        get = request.get
        if not get.key:
          response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
          response.error_message = (
              f'Empty SettingsRequest.get.key. Got: {request}.'
          )
          return response
        response, command_output = self._execute_command(
            ['shell', 'settings', 'get', namespace, get.key], timeout=timeout
        )
        response.settings.output = command_output
      case 'put':
        put = request.put
        if not put.key or not put.value:
          response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
          response.error_message = (
              f'Empty SettingsRequest.put key or value. Got: {request}.'
          )
          return response
        response, command_output = self._execute_command(
            ['shell', 'settings', 'put', namespace, put.key, put.value],
            timeout=timeout,
        )
        response.settings.output = command_output
      case 'delete_key':
        delete = request.delete_key
        if not delete.key:
          response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
          response.error_message = (
              f'Empty SettingsRequest.delete_key.key. Got: {request}.'
          )
          return response
        response, command_output = self._execute_command(
            ['shell', 'settings', 'delete', namespace, delete.key],
            timeout=timeout,
        )
        response.settings.output = command_output
      case 'reset':
        reset = request.reset
        # At least one of `package_name` or `mode` should be given.
        if (
            not reset.package_name
            and reset.mode
            == adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.UNKNOWN
        ):
          response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
          response.error_message = (
              'At least one of SettingsRequest.reset package_name or mode'
              f' should be given. Got: {request}.'
          )
          return response

        mode = adb_pb2.AdbRequest.SettingsRequest.Reset.Mode.Name(
            reset.mode
        ).lower()
        arg = reset.package_name or mode
        response, command_output = self._execute_command(
            ['shell', 'settings', 'reset', namespace, arg], timeout=timeout
        )
        response.settings.output = command_output
      case 'list':
        response, command_output = self._execute_command(
            ['shell', 'settings', 'list', namespace], timeout=timeout
        )
        response.settings.output = command_output
      case _:
        response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
        response.error_message = (
            f'Unknown SettingsRequest.verb. Got: {request}.'
        )

    return response

  def _handle_generic(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Handles GenericRequest messages.

    Args:
      request: The request with the `.generic` field set indicating what `adb`
        shell command to issue
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse
    """

    response, command_output = self._execute_command(
        list(request.generic.args), timeout)
    response.generic.output = command_output
    return response

  def _handle_package_manager(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Handles PackageManagerRequest messages.

    Args:
      request: The request with the `.package_manager` field set containing the
        sub-commands to issue to `adb pm`.
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse.
    """

    request = request.package_manager
    response = adb_pb2.AdbResponse()

    match request.WhichOneof('verb'):
      case 'list':
        what = request.list.WhichOneof('what')
        response, output = self._execute_command(
            ['shell', 'pm', 'list', what], timeout=timeout
        )

        if output:
          items = output.decode('utf-8').split()
          # Remove prefix for each item.
          prefix = {
              'features': 'feature:',
              'libraries': 'library:',
              'packages': 'package:',
          }[what]
          items = [x[len(prefix) :] for x in items if x.startswith(prefix)]
          response.package_manager.list.items.extend(items)
        response.package_manager.output = output
      case 'clear':
        package_name = request.clear.package_name
        if not package_name:
          response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
          response.error_message = (
              f'Empty PackageManagerRequest.clear.package_name. Got: {request}.'
          )
          return response

        args = ['shell', 'pm', 'clear', package_name]
        if request.clear.user_id:
          args.insert(3, '-f')
          args.insert(4, request.clear.user_id)
        response, response.package_manager.output = self._execute_command(
            args, timeout=timeout
        )
      case 'grant':
        grant = request.grant
        if not grant.package_name:
          response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
          response.error_message = '`grant.package_name` cannot be empty.'
          return response

        if not grant.permissions:
          response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
          response.error_message = '`grant.permissions` cannot be empty.'
          return response

        for permission in grant.permissions:
          logging.info('Granting permission: %r', permission)
          response, response.package_manager.output = self._execute_command(
              ['shell', 'pm', 'grant', grant.package_name, permission],
              timeout=timeout,
          )

    return response

  def _handle_dumpsys(
      self, request: adb_pb2.AdbRequest, timeout: float | None = None
  ) -> adb_pb2.AdbResponse:
    """Handles DumpsysRequest messages.

    Args:
      request: The request with the `.dumpsys` field set containing
        sub-commands to `adb dumpsys` shell command..
      timeout: Optional time limit in seconds.

    Returns:
      An AdbResponse.
    """

    request = request.dumpsys
    cmd = ['shell', 'dumpsys']

    if request.timeout_sec < 0 or request.timeout_ms < 0:
      response = adb_pb2.AdbResponse()
      response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
      response.error_message = (
          'DumpsysRequest.timeout_{sec, ms} should be non-negative. '
          f'Got: {request}.')
      return response

    if request.list_only:
      # `-l` cannot be combined with the following options.
      if request.service or request.args or request.skip_services:
        response = adb_pb2.AdbResponse()
        response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
        response.error_message = (
            'DumpsysRequest.list_only cannot be combined with other options. '
            f'Got: {request}.')
        return response

      cmd.append('-l')

    if request.timeout_sec > 0:
      cmd.append('-t')
      cmd.append(str(request.timeout_sec))
    elif request.timeout_ms > 0:
      cmd.append('-T')
      cmd.append(str(request.timeout_ms))

    if request.priority != adb_pb2.AdbRequest.DumpsysRequest.PriorityLevel.UNSET:
      cmd.append('--priority')
      cmd.append(adb_pb2.AdbRequest.DumpsysRequest.PriorityLevel.Name(
          request.priority))

    if request.skip_services:
      if request.service:
        response = adb_pb2.AdbResponse()
        response.status = adb_pb2.AdbResponse.Status.FAILED_PRECONDITION
        response.error_message = (
            'DumpsysRequest.skip_services cannot be combined with `service`. '
            f'Got: {request}.')
        return response

      cmd.append('--skip')
      cmd.append(','.join(request.skip_services))

    if request.service:
      cmd.append(request.service)

    if request.args:
      cmd += list(request.args)

    if request.proto:
      cmd.append('--proto')

    response, response.dumpsys.output = self._execute_command(
        cmd, timeout=timeout)

    return response
