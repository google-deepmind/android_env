# Copyright 2023 DeepMind Technologies Limited.
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

"""Simple package definition for using with `pip`."""

from distutils import cmd
import os

import pkg_resources
from setuptools import find_packages
from setuptools import setup
from setuptools.command.build_ext import build_ext
from setuptools.command.build_py import build_py

_ROOT_DIR = os.path.dirname(os.path.abspath(__file__))

# Tuple of proto message definitions to build Python bindings for. Paths must
# be relative to root directory.
_ANDROID_ENV_PROTOS = (
    'android_env/proto/adb.proto',
    'android_env/proto/emulator_controller.proto',
    'android_env/proto/snapshot.proto',
    'android_env/proto/snapshot_service.proto',
    'android_env/proto/state.proto',
    'android_env/proto/task.proto',
)

testing_requirements = [
    'attrs==20.3.0',  # temporary pin to fix pytype issue.
    'pillow',
    'pytype',
    'pytest-xdist',
    'gym',
]


class _GenerateProtoFiles(cmd.Command):
  """Command to generate protobuf bindings for AndroidEnv protos."""

  descriptions = 'Generates Python protobuf bindings for AndroidEnv protos.'
  user_options = []

  def initialize_options(self):
    pass

  def finalize_options(self):
    pass

  def run(self):
    # Import grpc_tools here, after setuptools has installed setup_requires
    # dependencies.
    from grpc_tools import protoc  # pylint: disable=g-import-not-at-top

    grpc_protos_include = pkg_resources.resource_filename(
        'grpc_tools', '_proto')

    for proto_path in _ANDROID_ENV_PROTOS:
      proto_args = [
          'grpc_tools.protoc',
          '--proto_path={}'.format(grpc_protos_include),
          '--proto_path={}'.format(_ROOT_DIR),
          '--python_out={}'.format(_ROOT_DIR),
          '--grpc_python_out={}'.format(_ROOT_DIR),
          os.path.join(_ROOT_DIR, proto_path),
      ]
      if protoc.main(proto_args) != 0:
        raise RuntimeError('ERROR: {}'.format(proto_args))


class _BuildExt(build_ext):
  """Generate protobuf bindings in build_ext stage."""

  def run(self):
    self.run_command('generate_protos')
    build_ext.run(self)


class _BuildPy(build_py):
  """Generate protobuf bindings in build_py stage."""

  def run(self):
    self.run_command('generate_protos')
    build_py.run(self)

setup(
    packages=find_packages(exclude=['examples']),
    package_data={'': ['proto/*.proto']},  # Copy protobuf files.
    include_package_data=True,
    setup_requires=['grpcio-tools'],
    cmdclass={
        'build_ext': _BuildExt,
        'build_py': _BuildPy,
        'generate_protos': _GenerateProtoFiles,
    },
)
