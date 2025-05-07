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

"""Wraps AndroidEnv to retrieve accessibility messages from gRPC."""

from concurrent import futures
import time
from typing import Any

import urllib

from absl import logging
from android_env import env_interface
from android_env.components import action_type as android_action_type_lib
from android_env.proto import adb_pb2
from android_env.proto.a11y import a11y_pb2_grpc
from android_env.wrappers import base_wrapper
from android_env.wrappers.a11y import a11y_events
from android_env.wrappers.a11y import a11y_forests
from android_env.wrappers.a11y import a11y_servicer
import dm_env
import grpc
import numpy as np
import portpicker


def _get_accessibility_forwarder_apk() -> bytes:
  logging.info('Downloading accessibility forwarder apk....')
  with urllib.request.urlopen(
      'https://storage.googleapis.com/android_env-tasks/2024.05.13-accessibility_forwarder.apk'
  ) as response:
    return response.read()


class EnableNetworkingError(ValueError):
  pass


class A11yGrpcWrapper(base_wrapper.BaseWrapper):
  """Wrapper which receives A11y events and forests over gRPC.

  A11y forest protobufs and event dicts are sent from the Android emulator via
  gRPC from the `AccessibilityForwarder` (for use in developing reward
  functions, etc). This wrapper constructs a server which receives these
  messages and channels them into `task_extras`.

  The downside of forwarding this information through gRPC is that no messages
  will be sent if networking is turned off (e.g., if the AVD is in airplane
  mode). To mitigate this problem, the `AccessibilityForwarder` logs an error
  message if it fails to contact the server. This wrapper monitors the logs for
  such error messages, and attempts (in another thread, to not block environment
  transitions) to reconnect the AVD to the network. If this fails to fix the
  problem, this wrapper ends the episode.

  This wrapper is implemented to be robust to multiple upstream callers of
  `task_extras`, and to ensure they each receive the same extras at every
  timestep. Thus, the logic is the following:
  * New a11y events/forests are fetched during `reset` and `step`, *not* during
    `task_extras()` calls.
  * If no one has called `task_extras()` since the last `step` or `reset`, the
    extras are accumulated (so that no extras are missed because someone called
    `step()` twice without calling `task_extras()`).
  * If someone *has* called `task_extras()` since last step, the newly fetched
    extras replace the old extras.
  """

  def __init__(
      self,
      env: env_interface.AndroidEnvInterface,
      disable_other_network_traffic: bool = False,
      install_a11y_forwarding: bool = False,
      start_a11y_service: bool = True,
      enable_a11y_tree_info: bool = False,
      add_latest_a11y_info_to_obs: bool = False,
      a11y_info_timeout: float | None = None,
      max_enable_networking_attempts: int = 10,
      latest_a11y_info_only: bool = False,
      grpc_server_ip: str = '10.0.2.2',
  ):
    """Initializes wrapper.

    Args:
      env: Environment to wrap.
      disable_other_network_traffic: When True, all network traffic, other than
        the connection to the servicer, is disabled. NOTE: This requires root
        access on the device (i.e. it uses the `su` command). An
        `AdbControllerError` exception will be raised if the underlying command
        fails.
      install_a11y_forwarding: If True, the wrapper handles the installation of
        all packages required for the servicer to collect a11y information.
      start_a11y_service: If True, starts the a11y forwarding services. NOTE:
        The packages must be installed beforehand, e.g., using the
        install_a11y_forwarding flag.
      enable_a11y_tree_info: When False, this wrapper collects only a11y events
        and not a11y tree.
      add_latest_a11y_info_to_obs: When True, the latest observed a11y forest is
        added to the observation.
      a11y_info_timeout: When larger than zero and add_latest_a11y_info_to_obs
        is set to True, the wrapper will wait the corresponding amount of time,
        measured in seconds, to collect the latest a11y forest.
      max_enable_networking_attempts: When the a11y gRPC service fails to
        provide a11y information, we attempt this many times to re-enable the
        networking. If all these attempts fail, fetching task_extras will raise
        an EnableNetworkingError.
      latest_a11y_info_only: When True, the a11y servicer is setup to save only
        the latest tree it has received from the Android app.
      grpc_server_ip: The IP address of the gRPC server which will be
        broadcasted to the AccessibilityForwarder app where it should log the
        a11y info. By default, this is set to the IP address of the AVD's host
        machine which is 10.0.2.2: See
        https://developer.android.com/studio/run/emulator-networking#networkaddresses.
    """
    self._env = env
    self._grpc_server_ip = grpc_server_ip
    if install_a11y_forwarding:
      self._install_a11y_forwarding_apk()
      time.sleep(10.0)
    if start_a11y_service:
      self._start_a11y_services()
      time.sleep(3.0)
    if enable_a11y_tree_info:
      self._enable_a11y_tree_logs()
    self._relaunch_count = 0
    self._server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    self._servicer = a11y_servicer.A11yServicer(
        latest_forest_only=latest_a11y_info_only
    )
    a11y_pb2_grpc.add_A11yServiceServicer_to_server(
        self._servicer, self._server
    )
    server_credentials = grpc.local_server_credentials()
    self._port = portpicker.pick_unused_port()
    logging.info('Using port %s', self._port)
    uri_address = f'[::]:{self._port}'
    self._server.add_secure_port(uri_address, server_credentials)
    logging.info('Starting server')
    self._server.start()
    logging.info('Server now running.')

    self._max_enable_networking_attempts = max_enable_networking_attempts
    self._reset_enable_networking_attempts()

    self._disable_other_network_traffic = disable_other_network_traffic
    self._should_accumulate = False
    self._accumulated_extras = None
    self._add_latest_a11y_info_to_obs = add_latest_a11y_info_to_obs
    self._a11y_info_timeout = a11y_info_timeout
    self._parent_action_spec = self._env.action_spec()
    if self._a11y_info_timeout is not None and self._a11y_info_timeout > 0.0:
      if 'action_type' not in self._parent_action_spec.keys():
        raise ValueError(
            'action_type not in the parent action spec: '
            f'{self._parent_action_spec}. This is a strong requirement when '
            f'a11y_info_timeout = {a11y_info_timeout} > 0'
        )

  def _start_a11y_services(self) -> None:
    """Starts the accessibility forwarder services.

    Raises:
      RuntimeError: If accessibility service is not started.
    """
    start_service_request = adb_pb2.AdbRequest(
        settings=adb_pb2.AdbRequest.SettingsRequest(
            name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.SECURE,
            put=adb_pb2.AdbRequest.SettingsRequest.Put(
                key='enabled_accessibility_services',
                value=(
                    'com.google.androidenv.accessibilityforwarder/com.google.'
                    'androidenv.accessibilityforwarder.AccessibilityForwarder'
                ),
            ),
        )
    )
    start_service_response = self._env.execute_adb_call(start_service_request)
    if start_service_response.status != adb_pb2.AdbResponse.Status.OK:
      raise RuntimeError(
          'Could not start accessibility forwarder '
          'service: '
          f'{start_service_response}.'
      )

  def _install_a11y_forwarding_apk(self) -> None:
    """Enables accessibility information forwarding."""
    a11y_fwd_apk = _get_accessibility_forwarder_apk()
    # Install and setup the Accesssibility Forwarder.
    install_request = adb_pb2.AdbRequest(
        install_apk=adb_pb2.AdbRequest.InstallApk(
            blob=adb_pb2.AdbRequest.InstallApk.Blob(contents=a11y_fwd_apk),
        )
    )
    install_response = self._env.execute_adb_call(install_request)
    if install_response.status != adb_pb2.AdbResponse.Status.OK:
      raise ValueError(
          f'Could not install accessibility_forwarder.apk: {install_response}.'
      )

  def _enable_a11y_tree_logs(self) -> None:
    enable_tree_logs_request = adb_pb2.AdbRequest(
        send_broadcast=adb_pb2.AdbRequest.SendBroadcast(
            action=(
                'accessibility_forwarder.intent.action.'
                'ENABLE_ACCESSIBILITY_TREE_LOGS'
            ),
            component=(
                'com.google.androidenv.accessibilityforwarder/com.google.androidenv.accessibilityforwarder.FlagsBroadcastReceiver'
            ),
        )
    )
    enable_tree_logs_response = self._env.execute_adb_call(
        enable_tree_logs_request
    )
    if enable_tree_logs_response.status != adb_pb2.AdbResponse.Status.OK:
      raise ValueError(
          'Could not enable accessibility tree logging: '
          f'{enable_tree_logs_response}.'
      )

  def _reset_enable_networking_attempts(self) -> None:
    self._enable_networking_attempts_left = self._max_enable_networking_attempts
    self._enabling_networking_future = None
    self._a11y_exception = None

  def get_port(self):
    return self._port

  def close(self):
    self._server.stop(None)
    logging.info('gRPC server stopped')
    self._env.close()

  def attempt_enable_networking(self) -> None:
    """Attempts to turn on networking within the Android device.

    Attempt to turn on the networking in the Android device, by:
    - turning off airplane mode;
    - turning on the wifi connection.
    """
    self.execute_adb_call(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='airplane_mode_on', value='0'
                ),
            )
        )
    )
    time.sleep(1.0)
    self.execute_adb_call(
        adb_pb2.AdbRequest(
            generic=adb_pb2.AdbRequest.GenericRequest(
                args=[
                    'shell',
                    'svc',
                    'wifi',
                    'enable',
                ]
            )
        )
    )
    time.sleep(1.0)

  def _configure_grpc(self) -> None:
    """Configure networking and set the gRPC ip and port on AVD or device."""

    if self._disable_other_network_traffic:
      self.execute_adb_call(
          adb_pb2.AdbRequest(
              generic=adb_pb2.AdbRequest.GenericRequest(
                  args=[
                      'shell',
                      'su',
                      '0',
                      'iptables',
                      '-A',
                      'OUTPUT',
                      '-p',
                      'tcp',
                      '-d',
                      self._grpc_server_ip,
                      '--dport',
                      str(self._port),
                      '-j',
                      'ACCEPT',
                  ]
              )
          )
      )
      time.sleep(3.0)
      self.execute_adb_call(
          adb_pb2.AdbRequest(
              generic=adb_pb2.AdbRequest.GenericRequest(
                  args=[
                      'shell',
                      'su',
                      '0',
                      'iptables',
                      '-A',
                      'OUTPUT',
                      '-j',
                      'DROP',
                  ]
              )
          )
      )
      time.sleep(3.0)

    self.execute_adb_call(
        adb_pb2.AdbRequest(
            settings=adb_pb2.AdbRequest.SettingsRequest(
                name_space=adb_pb2.AdbRequest.SettingsRequest.Namespace.GLOBAL,
                put=adb_pb2.AdbRequest.SettingsRequest.Put(
                    key='no_proxy', value=f'{self._grpc_server_ip}:{self._port}'
                ),
            )
        )
    )
    self.attempt_enable_networking()
    self.execute_adb_call(
        adb_pb2.AdbRequest(
            send_broadcast=adb_pb2.AdbRequest.SendBroadcast(
                action=(
                    'accessibility_forwarder.intent.action.SET_GRPC --ei'
                    f' "port" {self._port} --es "host" {self._grpc_server_ip}'
                ),
                component=(
                    'com.google.androidenv.accessibilityforwarder/com.google.androidenv.accessibilityforwarder.FlagsBroadcastReceiver'
                ),
            )
        )
    )

  def _accumulate_and_return_a11y_info(
      self, timer: float | None = None, get_env_observation: bool = True
  ) -> dict[str, Any]:
    """Accumulates and returns the latest a11y tree info and observation.

    Args:
      timer: If larger than 0, the system will wait this long for a11y info to
        accumulate before it returns a value.
      get_env_observation: If False, the corresponding observation is not
        introduced here.

    Returns:
      a dict with a11y forest under key 'a11y_forest'. All other fields will
      provide the observation, if requested.
    """
    timer = timer or 0.0
    if timer > 0.0:
      time.sleep(timer)

    if get_env_observation:
      # Fetch observation.
      new_ts = self._env.step({
          'action_type': np.array(
              android_action_type_lib.ActionType.REPEAT,
              dtype=self._parent_action_spec['action_type'].dtype,
          ),
      })
      observation = new_ts.observation
    else:
      observation = {}

    extras = self.accumulate_new_extras()
    forests = a11y_forests.extract_forests_from_task_extras(extras)
    if forests:
      observation['a11y_forest'] = forests[-1]
    else:
      observation['a11y_forest'] = None
    return observation

  def _fetch_task_extras_and_update_observation(
      self, observation: dict[str, Any], timeout: float = 0.0
  ) -> dict[str, Any]:
    if timeout > 0.0:
      observation = self._accumulate_and_return_a11y_info(
          timeout, get_env_observation=True
      )
      if not self._add_latest_a11y_info_to_obs:
        observation.pop('a11y_forest')
    else:
      new_obs = self._accumulate_and_return_a11y_info(get_env_observation=False)
      if self._add_latest_a11y_info_to_obs:
        observation.update(new_obs)
    return observation

  def reset(self) -> dm_env.TimeStep:
    self._reset_enable_networking_attempts()
    self._servicer.pause_and_clear()
    timestep = self._env.reset()
    self._servicer.resume()
    if self._env.stats()['relaunch_count'] > self._relaunch_count:
      self._configure_grpc()
      self._relaunch_count = self._env.stats()['relaunch_count']
    self._accumulated_extras = {}
    timeout = self._a11y_info_timeout or 0.0
    new_observation = self._fetch_task_extras_and_update_observation(
        timestep.observation, timeout
    )
    timestep = timestep._replace(observation=new_observation)
    return timestep

  def step(self, action: Any) -> dm_env.TimeStep:
    timeout = float(action.pop('wait_time', self._a11y_info_timeout or 0.0))
    timestep = self._env.step(action)
    new_observation = self._fetch_task_extras_and_update_observation(
        timestep.observation, timeout=timeout
    )
    timestep = timestep._replace(observation=new_observation)
    return timestep

  def accumulate_new_extras(self) -> dict[str, Any]:
    new_extras = self._fetch_task_extras()
    if self._should_accumulate:
      for key in new_extras:
        if key in self._accumulated_extras:
          self._accumulated_extras[key] = np.concatenate(
              (self._accumulated_extras[key], new_extras[key]), axis=0
          )
        else:
          self._accumulated_extras[key] = new_extras[key]
    else:
      self._accumulated_extras = new_extras
    self._should_accumulate = True
    return self._accumulated_extras

  def _fetch_task_extras(self) -> dict[str, Any]:
    """Fetches task_extras from the services.

    NOTE: If you want to access the latest a11y information, please use
    accumulate_and_return_a11y_info instead. This function has the side effect
    of clearing the content from the servicer, hence all the a11y info returned
    here won't be accumulated.

    Returns:
      A dict with the corresponding task_extras.

    Raises:
      EnableNetworkingError: after a fixed number of attempts to revive the a11y
        services by re-enabling the network connection.
    """
    base_extras = self._env.task_extras(latest_only=False).copy()
    # If the previous future is done, reset it to the initial state.
    if (
        self._enabling_networking_future is not None
        and self._enabling_networking_future.done()
    ):
      self._enabling_networking_future = None
      self._enable_networking_attempts_left -= 1
      logging.info('Finished enabling networking.')

    if (
        self._enabling_networking_future is None
        and 'exception' in base_extras
        and base_extras['exception'].shape[0]
    ):
      self._a11y_exception = base_extras['exception']
      logging.warning(
          'AccessibilityForwarder logged exceptions: %s', self._a11y_exception
      )
      if self._enable_networking_attempts_left > 0:
        logging.warning(
            'Attempting to enable networking. %s attempts left.',
            self._enable_networking_attempts_left - 1,
        )
        executor = futures.ThreadPoolExecutor(max_workers=1)
        self._enabling_networking_future = executor.submit(
            self.attempt_enable_networking
        )
      else:
        raise EnableNetworkingError(
            'A11y service failed multiple times with'
            f' exception.{self._a11y_exception}.'
        )

    forests = self._servicer.gather_forests()
    if forests:
      base_extras.update(a11y_forests.package_forests_to_task_extras(forests))
      self._reset_enable_networking_attempts()
    events = self._servicer.gather_events()
    if events:
      base_extras.update(a11y_events.package_events_to_task_extras(events))
      self._reset_enable_networking_attempts()
    return base_extras

  def task_extras(self, latest_only: bool = False) -> dict[str, Any]:
    if self._accumulated_extras is None:
      raise RuntimeError('You must call .reset() before calling .task_extras()')
    self._should_accumulate = False
    extras = self._accumulated_extras.copy()
    if latest_only:
      a11y_events.keep_latest_event_only(extras)
      a11y_forests.keep_latest_forest_only(extras)
    return extras
