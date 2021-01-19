# Lint as: python3
"""Pseudo metadata server for Cloud Android.

TODO(b/149332385): Port this to use HTTPServer2 (go/httpserver2)
"""

import datetime
import hashlib
import json
import os
import re
import socket
import sys
import time

import six.moves.BaseHTTPServer
import six.moves.SimpleHTTPServer
import six.moves.socketserver
import six.moves.urllib.parse

SSH_KEY_PATH_1 = ['instance', 'attributes', 'sshKeys']
SSH_KEY_PATH_2 = ['project', 'attributes', 'sshKeys']


def ConvertToCamelCase(element):
  return re.sub(r'-[a-z]+', lambda m: m.group(0)[1:].capitalize(), element)


def ConvertFromCamelCase(element):
  if element == 'sshKeys':
    return 'sshKeys'
  return re.sub(r'[A-Z]', lambda m: '-' + m.group(0).lower(), element)


def SetValueForAttr(path, value, dest):
  it = dest
  for p in path[:-1]:
    key = ConvertToCamelCase(p)
    if key not in it:
      it[key] = {}
    it = it[key]
  it[path[-1]] = value


def GetValueForPath(path, values):
  """Find the first value that matches attr in the metadata file.

  Args:
    path: Array representing the split path to the attribute
    values: The nested dictionary of values
  Returns:
    The string value or None if not found.
  """
  rval = values
  for p in path:
    key = ConvertToCamelCase(p)
    if key not in rval:
      return None
    rval = rval[p]
  return rval


def GenerateTextValues(values, prefix=''):
  """Converts a nested dictionary to text format.

  Args:
    values: The object to convert
    prefix: A string that is added to each key for the recursive descent
  Returns:
    A string representing the text format
  """
  rval = ''
  if isinstance(values, list):
    for key in range(len(values)):
      rval += GenerateTextValues(values[key], '%s/%d' % (prefix, key))
  elif isinstance(values, dict):
    for key in values:
      rval += GenerateTextValues(values[key], '%s/%s' % (
          prefix, ConvertFromCamelCase(key)))
  else:
    rval = '%s %s\n' % (prefix[1:], str(values))
  return rval


class MetadataServer(six.moves.socketserver.ThreadingMixIn,
                     six.moves.BaseHTTPServer.HTTPServer):
  """Metadata HTTP server class."""
  address_family = socket.AF_INET6

  def __init__(self, metadata, public_key, addr, handler_class):
    self._metadata = json.loads(metadata)
    self.etag = ''
    self.daemon_threads = True
    self._public_key = public_key
    self._set_ssh_keys()
    self._set_metadata()
    six.moves.BaseHTTPServer.HTTPServer.__init__(self, addr, handler_class)

  def _set_ssh_keys(self):
    self._ssh_keys = ''
    kparts = self._public_key.rstrip().split(' ')
    self._ssh_keys += '%s:%s %s google-ssh %s@google.com\n' % (
        os.environ['USER'], kparts[0], kparts[1], os.environ['USER'])

  def _set_metadata(self):
    self.SetSshKeys(self._metadata)
    self._etag = hashlib.md5(json.dumps(
        self._metadata).encode('utf-8')).hexdigest()

  def SetSshKeys(self, dest):
    """Sets ssh keys in a dictionary.

    Args:
      dest: The dictionary to modify
    """
    SetValueForAttr(SSH_KEY_PATH_1, self._ssh_keys, dest)
    SetValueForAttr(SSH_KEY_PATH_2, self._ssh_keys, dest)

  def PollMetadataValues(self, etag, timeout_sec):
    """Gets the current state of the metadata values.

    A call to this function will block until said state is different than last
    time it was retrieved (as specified by the etag parameter) or timeout_sec
    seconds have passed.

    Args:
      etag: The ETag of the last version of the metadata obtained by the
          client.
      timeout_sec: The time the client is willing to wait for the metadata
          to change.
    Returns:
       The current state of the metadata values.
    """
    start_time = datetime.datetime.now()
    while True:
      (new_etag, values) = self.GetMetadataValues()
      time_diff = datetime.datetime.now() - start_time
      if etag == new_etag and timeout_sec > time_diff.total_seconds():
        time.sleep(1)
      else:
        return (new_etag, values)

  def GetMetadataValues(self):
    """Gets the current state of the metadata values."""
    self._set_metadata()
    return (self._etag, self._metadata)


class MetadataRequestHandler(six.moves.SimpleHTTPServer.SimpleHTTPRequestHandler
                            ):
  """HTTP server request handler."""

  protocol_version = 'HTTP/1.1'
  wbufsize = -1  # Turn off output buffering.

  def version_string(self):
    return 'Metadata Server for VM'

  def do_GET(self):  # WSGI name, so pylint: disable=g-bad-name
    """Process a GET request."""
    parts = six.moves.urllib.parse.urlparse(self.path)
    params = six.moves.urllib.parse.parse_qs(parts.query)
    timeout_sec = None
    alt = params.get('alt', ['json'])[0]
    last_etag = params.get('last_etag', [''])[0]

    if params.get('wait_for_change', ['false'])[0] == 'true':
      timeout_sec = float(params.get('timeout_sec', ['30'])[0])
      (etag, values) = self.server.PollMetadataValues(last_etag, timeout_sec)
    else:
      (etag, values) = self.server.GetMetadataValues()
    value = None
    if params.get('recursive', ['false'])[0] == 'true':
      if alt == 'json':
        value = json.dumps(values)
      else:
        value = GenerateTextValues(values)
    else:
      value = GetValueForPath(parts.path.split('/')[3:], values)
      if alt == 'json':
        value = json.dumps(value)
    if value:
      self.send_response(200)
      self.send_header('Metadata-Flavor', 'Google')
      self.send_header('Content-Type', 'application/%s' % alt)
      self.send_header('Content-Length', len(value))
      self.send_header('ETag', etag)
      self.send_header('X-XSS-Protection', '1; mode=block')
      self.send_header('X-Frame-Options', 'SAMEORIGIN')
      self.send_header('Connection', 'close')
      self.end_headers()
      self.wfile.write(value.encode('utf-8'))
    else:
      error_string = 'Attribute not found %s. Values: %s' % (
          parts.path.split('/')[3:], values)
      self.send_error(404, error_string)


def main():
  server_address = ('::1', int(sys.argv[1]))
  print('Metadata File %s' % sys.argv[2])
  with open(sys.argv[2], 'r') as f:
    metadata = f.read()
    print(metadata)

  print('Public key file %s' % sys.argv[3])
  with open(sys.argv[3], 'r') as kf:
    public_key = kf.read()
    print(public_key)

  httpd = MetadataServer(metadata, public_key, server_address,
                         MetadataRequestHandler)
  print(httpd.socket.getsockname())
  # print('Serving on :%r' % httpd.socket.getsockname())
  httpd.serve_forever()


if __name__ == '__main__':
  main()
