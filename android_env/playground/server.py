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

"""HTTP and WebSocket server for AndroidEnv Playground."""

import http.server
import os
import socketserver
import urllib.parse

from absl import logging
from android_env.playground import state as state_lib
from android_env.playground import websocket as websocket_lib

_FRONTEND_INDEX_RESOURCE = 'android_env/playground/frontend/index.html'


def _get_resource_filename(path: str) -> str:
  """Resolves a resource filename from the runfiles, if available."""
  return ''


def get_default_static_dir() -> str:
  """Resolves the default frontend static files directory from runfiles."""
  resource_path = _get_resource_filename(_FRONTEND_INDEX_RESOURCE)
  if resource_path and os.path.exists(resource_path):
    return os.path.dirname(resource_path)

  for env_var in ('RUNFILES_DIR', 'PYTHON_RUNFILES'):
    runfiles_dir = os.environ.get(env_var)
    if runfiles_dir:
      for rel_path in (
          '_main/android_env/playground/frontend',
          'android_env/playground/frontend',
      ):
        candidate = os.path.join(runfiles_dir, rel_path)
        if os.path.exists(os.path.join(candidate, 'index.html')):
          return candidate

  # Fallback to package-relative directory for standard pip/wheel installs.
  pkg_candidate = os.path.join(os.path.dirname(__file__), 'frontend')
  if os.path.exists(os.path.join(pkg_candidate, 'index.html')):
    return pkg_candidate

  raise FileNotFoundError(
      'Could not resolve static files directory from runfiles or package.'
  )


class PlaygroundServer(socketserver.ThreadingTCPServer):

  """Threading TCP Server that holds playground state."""

  def __init__(
      self,
      server_address,
      RequestHandlerClass,
      playground_state: state_lib.PlaygroundState,
      static_dir: str,
  ):
    super().__init__(server_address, RequestHandlerClass)
    self.playground_state = playground_state
    self.static_dir = static_dir


class StreamHandler(http.server.SimpleHTTPRequestHandler):
  """HTTP handler for remote view and WebSockets."""

  protocol_version = 'HTTP/1.1'

  def __init__(self, request, client_address, server_inst):
    # Set the directory before calling super().__init__ because it calls do_GET
    self.directory = server_inst.static_dir
    super().__init__(
        request, client_address, server_inst, directory=server_inst.static_dir
    )

  def do_GET(self):  # pylint: disable=invalid-name
    """Handles GET requests for HTML and WebSocket handshake."""
    server_inst = self.server
    if not isinstance(server_inst, PlaygroundServer):
      self.send_error(500, 'Unexpected server type')
      return
    state = server_inst.playground_state
    parsed_url = urllib.parse.urlparse(self.path)
    if parsed_url.path == '/ws':
      websocket_lib.handle_websocket(self, state)
    else:
      # Fallback to SimpleHTTPRequestHandler to serve static files
      super().do_GET()
