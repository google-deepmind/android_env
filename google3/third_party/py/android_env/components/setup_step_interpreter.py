"""A component that parses and processes SetupSteps."""

import copy
import random
import re
import time
from typing import Any, Dict, Optional, Sequence

from absl import logging
from android_env.components import adb_controller as adb_control
from android_env.components import app_screen_checker
from android_env.components import errors
from android_env.components import logcat_thread
from android_env.proto import task_pb2


class SetupStepInterpreter():
  """An interpreter for SetupSteps."""

  def __init__(self,
               adb_controller: adb_control.AdbController,
               logcat: logcat_thread.LogcatThread):
    """Initializes this interpreter.

    Args:
      adb_controller: An object to communicate with Android via ADB.
      logcat: A LogcatThread instance connected to the same Android simulator
        as AdbController.
    """
    self._adb_controller = adb_controller
    self._logcat_thread = logcat
    self._last_activity = ''
    self._log_dict = {
        'error_count_adb_call': 0,
        'error_count_wait_for_app_screen': 0,
        'error_count_check_install': 0,
        'error_count_wait_for_message': 0,
        'total_time_waiting_for_app_screen': 0
    }

  def log_dict(self) -> Dict[str, Any]:
    return copy.deepcopy(self._log_dict)

  def interpret(self, setup_steps: Sequence[task_pb2.SetupStep]) -> None:
    """Returns True if parsing and processing `setup_steps` is successful."""
    if setup_steps:
      logging.info('Executing setup steps: %s', setup_steps)
      for step in setup_steps:
        self._process_step_command(step)
      logging.info('Done executing setup steps.')

  def _process_step_command(self, step_cmd: task_pb2.SetupStep) -> None:
    """Processes a single step command from a reset or extra setup."""

    if not step_cmd:
      logging.info('Empty step_cmd')
      return

    logging.info('Executing step_cmd: %r', step_cmd)
    step_type = step_cmd.WhichOneof('step')
    success_condition = step_cmd.success_condition
    success_check = success_condition.WhichOneof('check')
    assert step_type or success_check, (
        'At least one of step and success_condition must be defined.')

    num_tries = 0
    max_retries = max(success_condition.num_retries, 3)
    while num_tries < max_retries:

      num_tries += 1

      try:
        self._execute_step_cmd(step_cmd, step_type)
        time.sleep(0.5)
        self._check_success(success_check, success_condition)
        return

      except NotImplementedError:
        logging.exception('Not implemented error! Skipping this step command.')
        return

      except errors.AdbControllerError:
        self._log_dict['error_count_adb_call'] += 1
        logging.warning('ADB call [%r] has failed. Try %d of %d.',
                        step_cmd.adb_call, num_tries, max_retries)

      except errors.WaitForAppScreenError:
        self._log_dict['error_count_wait_for_app_screen'] += 1
        logging.warning('Failed to wait for app screen. Try %d of %d.',
                        num_tries, max_retries)

      except errors.WaitForMessageError:
        self._log_dict['error_count_wait_for_message'] += 1
        logging.warning('Failed to wait for message. Try %d of %d.', num_tries,
                        max_retries)

      except errors.CheckInstallError:
        self._log_dict['error_count_check_install'] += 1
        logging.warning('Package [%r] not installed. Try %d of %d.',
                        success_condition.check_install.package_name, num_tries,
                        max_retries)

    raise errors.StepCommandError('Step failed: [%r]' % step_cmd)

  def _execute_step_cmd(self,
                        step_cmd: task_pb2.SetupStep,
                        step_type: Optional[str]) -> None:
    """Executes a step command of given type."""

    if not step_type:
      return

    if step_type == 'sleep':
      time.sleep(step_cmd.sleep.time_sec)
    elif step_type == 'adb_call':
      self._parse_adb_call(step_cmd.adb_call)
    else:
      raise NotImplementedError('No step command of type [%s].' % step_type)

  def _check_success(self, success_check: Optional[str],
                     success_condition: task_pb2.SuccessCondition) -> None:
    """Checks whether the given success condition was met."""

    if not success_check:
      return

    if success_check == 'wait_for_app_screen':
      self._wait_for_app_screen(success_condition.wait_for_app_screen)
    elif success_check == 'check_install':
      self._check_install(success_condition.check_install)
    elif success_check == 'wait_for_message':
      self._wait_for_message(success_condition.wait_for_message)
    else:
      raise NotImplementedError('No success check called [%s].' % success_check)

  def _parse_adb_call(self, adb_cmd: task_pb2.AdbCall) -> None:
    """Parses an adb command into set of allowed calls."""

    call_type = adb_cmd.WhichOneof('command')
    logging.info('Parsing ADB call of type: %s', call_type)

    if call_type == 'tap':
      tap = adb_cmd.tap
      self._adb_controller.input_tap(tap.x, tap.y)

    elif call_type == 'rotate':
      self._adb_controller.rotate_device(adb_cmd.rotate.orientation)

    elif call_type == 'press_button':
      if (adb_cmd.press_button.button ==
          task_pb2.AdbCall.PressButton.Button.HOME):
        self._adb_controller.input_key('KEYCODE_HOME')
      elif (adb_cmd.press_button.button ==
            task_pb2.AdbCall.PressButton.Button.BACK):
        self._adb_controller.input_key('KEYCODE_BACK')

    elif call_type == 'start_random_activity':
      self._last_activity = random.choice(
          list(adb_cmd.start_random_activity.activity_list))
      logging.info('Random activity: %s', self._last_activity)
      self._adb_controller.start_activity(
          self._last_activity, list(adb_cmd.start_random_activity.extra_args))
      wait_proto = task_pb2.WaitForAppScreen()
      wait_proto.app_screen.activity = self._last_activity
      wait_proto.timeout_sec = adb_cmd.start_random_activity.timeout_sec
      self._wait_for_app_screen(wait_proto)

    elif call_type == 'start_activity':
      self._adb_controller.start_activity(
          adb_cmd.start_activity.full_activity,
          list(adb_cmd.start_activity.extra_args))

    elif call_type == 'start_intent':
      self._adb_controller.start_intent(
          action=adb_cmd.start_intent.action,
          data_uri=adb_cmd.start_intent.data_uri,
          package_name=adb_cmd.start_intent.package_name)

    elif call_type == 'force_stop':
      self._adb_controller.force_stop(adb_cmd.force_stop.package_name)

    elif call_type == 'force_stop_random_activity':
      if self._last_activity:
        package_name = self._last_activity.split('/')[0]
        logging.info('Force stop package (%s)', package_name)
        self._adb_controller.force_stop(package_name)

    elif call_type == 'clear_cache':
      self._adb_controller.clear_cache(adb_cmd.clear_cache.package_name)

    elif call_type == 'clear_cache_random_activity':
      if self._last_activity:
        package_name = self._last_activity.split('/')[0]
        logging.info('Clear cache package (%s)', package_name)
        self._adb_controller.force_stop(package_name)

    elif call_type == 'grant_permissions':
      self._adb_controller.grant_permissions(
          adb_cmd.grant_permissions.package_name,
          adb_cmd.grant_permissions.permissions)

    elif call_type == 'install_apk':
      install_apk_cmd = adb_cmd.install_apk
      location_type = install_apk_cmd.WhichOneof('location')
      logging.info('location_type: %s', location_type)
      if location_type == 'filesystem':
        self._adb_controller.install_apk(install_apk_cmd.filesystem.path)
      else:
        logging.error('Unsupported location type: %r', install_apk_cmd)

    elif call_type == 'start_accessibility_service':
      self._adb_controller.start_accessibility_service(
          adb_cmd.start_accessibility_service.full_service)

    elif call_type == 'start_screen_pinning':
      self._adb_controller.start_screen_pinning(
          adb_cmd.start_screen_pinning.full_activity)

    elif call_type == 'disable_animations':
      self._adb_controller.disable_animations()

    else:
      raise NotImplementedError('No ADB call type [%s].' % call_type)

  def _wait_for_app_screen(
      self, wait_for_app_screen: task_pb2.WaitForAppScreen) -> None:
    """Waits for a given `app_screen` to be the current screen."""

    logging.info('Waiting for app screen...')
    app_screen = wait_for_app_screen.app_screen
    screen_checker = app_screen_checker.AppScreenChecker(
        self._adb_controller, app_screen)

    start_time = time.time()
    while time.time() - start_time < wait_for_app_screen.timeout_sec:
      if (screen_checker.matches_current_app_screen() ==
          app_screen_checker.AppScreenChecker.Outcome.SUCCESS):
        wait_time = time.time() - start_time
        self._log_dict['total_time_waiting_for_app_screen'] += wait_time
        logging.info('Successfully waited for app screen in %r seconds: [%r]',
                     wait_time, app_screen)
        return
      time.sleep(0.1)

    wait_time = time.time() - start_time
    self._log_dict['total_time_waiting_for_app_screen'] += wait_time
    logging.error('Failed to wait for app screen in %r seconds: [%r].',
                  wait_time, app_screen)

    raise errors.WaitForAppScreenError()

  def _wait_for_message(self,
                        wait_for_message: task_pb2.WaitForMessage) -> None:
    """Waits for a given message in logcat."""

    message = wait_for_message.message
    logging.info('Waiting for message: %s...', message)
    event = re.compile(r'^{message}$')
    got_message = False

    def f(ev, match):
      del ev, match
      nonlocal got_message
      got_message = True

    self._logcat_thread.add_event_listener(event=event, fn=f)
    self._logcat_thread.wait(
        event=event, timeout_sec=wait_for_message.timeout_sec)
    self._logcat_thread.remove_event_listener(event=event, fn=f)
    if got_message:
      logging.info('Message received: [%r]', message)
    else:
      logging.error('Failed to wait for message: [%r].', message)
      raise errors.WaitForMessageError()

  def _check_install(self, check_install: task_pb2.CheckInstall) -> None:
    """Checks that the given package is installed."""

    package = check_install.package_name
    logging.info('Checking if package is installed: [%r]', package)

    start_time = time.time()
    while time.time() - start_time < check_install.timeout_sec:
      if self._adb_controller.is_package_installed(package):
        logging.info('Done confirming that package is installed.')
        return
      time.sleep(0.1)

    logging.error('Package not found.')
    raise errors.CheckInstallError()
