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

"""Tests for playground server."""

import http.server
import os
import socket
import socketserver
from unittest import mock
from absl.testing import absltest
from android_env.playground import server
from android_env.playground import state as state_lib
from android_env.playground import websocket as websocket_lib


class ServerTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.mock_request = mock.create_autospec(socket.socket, instance=True)
    self.mock_client_address = ('127.0.0.1', 12345)
    self.mock_state = mock.create_autospec(
        state_lib.PlaygroundState, instance=True
    )
    self.mock_server = mock.create_autospec(
        server.PlaygroundServer, instance=True
    )
    self.mock_server.playground_state = self.mock_state
    self.mock_server.static_dir = '/my/static/dir'

  @mock.patch.object(
      socketserver.ThreadingTCPServer, '__init__', return_value=None
  )
  def test_server_init(self, mock_super_init):
    server_inst = server.PlaygroundServer(
        ('127.0.0.1', 8080),
        server.StreamHandler,
        self.mock_state,
        '/my/static/dir',
    )
    self.assertEqual(server_inst.playground_state, self.mock_state)
    self.assertEqual(server_inst.static_dir, '/my/static/dir')
    mock_super_init.assert_called_once_with(
        ('127.0.0.1', 8080), server.StreamHandler
    )

  @mock.patch.object(
      http.server.SimpleHTTPRequestHandler, '__init__', return_value=None
  )
  def test_handler_init(self, mock_super_init):
    # Verify that handler init sets directory and calls super init
    handler = server.StreamHandler(
        self.mock_request, self.mock_client_address, self.mock_server
    )
    self.assertEqual(handler.directory, '/my/static/dir')
    mock_super_init.assert_called_once_with(
        self.mock_request,
        self.mock_client_address,
        self.mock_server,
        directory='/my/static/dir',
    )

  @mock.patch.object(
      http.server.SimpleHTTPRequestHandler, '__init__', return_value=None
  )
  @mock.patch.object(
      http.server.SimpleHTTPRequestHandler, 'do_GET', autospec=True
  )
  def test_do_get_fallback_to_static(
      self, mock_super_do_get, unused_mock_super_init
  ):
    handler = server.StreamHandler(
        self.mock_request, self.mock_client_address, self.mock_server
    )
    handler.server = self.mock_server
    handler.path = '/index.html'

    handler.do_GET()

    mock_super_do_get.assert_called_once_with(handler)

  @mock.patch.object(
      http.server.SimpleHTTPRequestHandler, '__init__', return_value=None
  )
  @mock.patch.object(websocket_lib, 'handle_websocket', autospec=True)
  @mock.patch.object(
      http.server.SimpleHTTPRequestHandler, 'do_GET', autospec=True
  )
  def test_do_get_ws(
      self, mock_super_do_get, mock_handle_ws, unused_mock_super_init
  ):
    handler = server.StreamHandler(
        self.mock_request, self.mock_client_address, self.mock_server
    )
    handler.server = self.mock_server
    handler.path = '/ws'

    handler.do_GET()

    mock_handle_ws.assert_called_once_with(handler, self.mock_state)
    mock_super_do_get.assert_not_called()

  @mock.patch.object(
      http.server.SimpleHTTPRequestHandler, '__init__', return_value=None
  )
  def test_do_get_invalid_server_type(self, unused_mock_super_init):
    handler = server.StreamHandler(
        self.mock_request, self.mock_client_address, self.mock_server
    )
    # Set server to a mock that is NOT PlaygroundServer
    handler.server = mock.create_autospec(http.server.HTTPServer, instance=True)
    handler.send_error = mock.create_autospec(handler.send_error)

    handler.do_GET()

    handler.send_error.assert_called_once_with(500, 'Unexpected server type')

  def test_get_default_static_dir_returns_existing_dir(self):
    static_dir = server.get_default_static_dir()
    self.assertIsNotNone(static_dir)

  @mock.patch.object(os.path, 'exists', autospec=True)
  def test_get_default_static_dir_resource_path(self, mock_exists):
    mock_exists.return_value = True
    with mock.patch.object(
        server,
        '_get_resource_filename',
        return_value='/fake/resource/dir/index.html',
    ):
      static_dir = server.get_default_static_dir()
      self.assertEqual(static_dir, '/fake/resource/dir')

  @mock.patch.object(os.path, 'exists', autospec=True)
  def test_get_default_static_dir_resource_path_does_not_exist(
      self, mock_exists
  ):
    expected_dir = os.path.join(os.path.dirname(server.__file__), 'frontend')

    def side_effect(path):
      return path == os.path.join(expected_dir, 'index.html')

    mock_exists.side_effect = side_effect
    with (
        mock.patch.object(
            server,
            '_get_resource_filename',
            return_value='/nonexistent/resource/index.html',
        ),
        mock.patch.dict(os.environ, {}, clear=True),
    ):
      static_dir = server.get_default_static_dir()
      self.assertEqual(static_dir, expected_dir)

  @mock.patch.object(os.path, 'exists', autospec=True)
  def test_get_default_static_dir_fallback_to_runfiles_dir(self, mock_exists):
    def side_effect(path):
      return path == '/fake/runfiles/android_env/playground/frontend/index.html'

    mock_exists.side_effect = side_effect
    with (
        mock.patch.object(server, '_get_resource_filename', return_value=''),
        mock.patch.dict(
            os.environ, {'RUNFILES_DIR': '/fake/runfiles'}, clear=True
        ),
    ):
      static_dir = server.get_default_static_dir()
      self.assertEqual(
          static_dir, '/fake/runfiles/android_env/playground/frontend'
      )

  @mock.patch.object(os.path, 'exists', autospec=True)
  def test_get_default_static_dir_fallback_to_python_runfiles(
      self, mock_exists
  ):
    def side_effect(path):
      return (
          path == '/fake/py_runfiles/android_env/playground/frontend/index.html'
      )

    mock_exists.side_effect = side_effect
    with (
        mock.patch.object(server, '_get_resource_filename', return_value=''),
        mock.patch.dict(
            os.environ, {'PYTHON_RUNFILES': '/fake/py_runfiles'}, clear=True
        ),
    ):
      static_dir = server.get_default_static_dir()
      self.assertEqual(
          static_dir, '/fake/py_runfiles/android_env/playground/frontend'
      )

  @mock.patch.object(os.path, 'exists', autospec=True)
  def test_get_default_static_dir_fallback_to_package_dir(self, mock_exists):
    expected_dir = os.path.join(os.path.dirname(server.__file__), 'frontend')

    def side_effect(path):
      return path == os.path.join(expected_dir, 'index.html')

    mock_exists.side_effect = side_effect
    with (
        mock.patch.object(server, '_get_resource_filename', return_value=''),
        mock.patch.dict(os.environ, {}, clear=True),
    ):
      static_dir = server.get_default_static_dir()
      self.assertEqual(static_dir, expected_dir)

  @mock.patch.object(os.path, 'exists', return_value=False, autospec=True)
  def test_get_default_static_dir_raises_file_not_found(self, mock_exists):
    del mock_exists
    with (
        mock.patch.object(server, '_get_resource_filename', return_value=''),
        mock.patch.dict(os.environ, {}, clear=True),
    ):
      with self.assertRaises(FileNotFoundError):
        server.get_default_static_dir()


if __name__ == '__main__':
  absltest.main()
