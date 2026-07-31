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

"""APK resolution utilities for AndroidEnv components."""

import tempfile

from android_env.google.resource_utils import apk_utils as google_apk_utils
from android_env.proto import task_pb2

fetch_apk_for_request = google_apk_utils.fetch_apk_for_request


def fetch_apks_for_task(
    task: task_pb2.Task, task_tmp_dir: str | None = None
) -> task_pb2.Task:
  """Fetches APKs specified in task and returns updated task proto.

  Args:
    task: task_pb2.Task proto definition.
    task_tmp_dir: Optional local directory to store fetched APKs. If None, uses
      a default temporary directory.

  Returns:
    Updated task proto with resolved local filesystem APK paths.
  """
  if task_tmp_dir is None:
    task_tmp_dir = tempfile.gettempdir()
  return google_apk_utils.fetch_apks_for_task(task, task_tmp_dir)
