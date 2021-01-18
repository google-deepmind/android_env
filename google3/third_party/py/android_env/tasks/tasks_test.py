# Lint as: python3
"""Tests for google3.learning.deepmind.rl.environments.android.tasks.tasks."""

import glob
import os
from typing import Callable, Optional

from absl import flags
from absl import logging
from android_env.proto import task_pb2

from google3.releasetools.common import mpmlib
from google3.testing.pybase import googletest

FLAGS = flags.FLAGS


def _run_check(check_fn: Callable[[task_pb2.Task], None]):
  task_dir = os.path.join(
      FLAGS.test_srcdir, 'google3',
      'learning/deepmind/rl/environments/android/tasks/*.binarypb')
  for fname in glob.glob(task_dir):
    logging.info('Checking %r...', fname)
    with open(fname, 'rb') as proto_file:
      task = task_pb2.Task()
      task.ParseFromString(proto_file.read())
      check_fn(task)
    logging.info('Done checking %r...', fname)


def _get_install_apk_cmd(
    setup_step: Optional[task_pb2.SetupStep]
) -> Optional[task_pb2.AdbCall.InstallApk]:
  if not setup_step:  # Ignore empty step commands.
    return None

  step_type = setup_step.WhichOneof('step')
  logging.info('step_type: %r', step_type)
  if step_type != 'adb_call':
    return None

  adb_call = setup_step.adb_call
  call_type = adb_call.WhichOneof('command')
  logging.info('call_type: %r', call_type)
  if call_type != 'install_apk':
    return None

  return adb_call.install_apk


def _get_mpm(task: task_pb2.Task) -> Optional[task_pb2.AdbCall.InstallApk.MPM]:
  """Returns the package name associated with this `Task`."""
  if not task.setup_steps:
    return None

  # Search for commands that install APKs.
  for step_cmd in task.setup_steps:
    install_apk = _get_install_apk_cmd(step_cmd)
    if not install_apk:
      return

    location = install_apk.WhichOneof('location')
    logging.info('location: %r', location)
    if location != 'mpm':
      return None

    return install_apk.mpm

  return None


def _get_mpm_package_name(task: task_pb2.Task) -> Optional[str]:
  mpm = _get_mpm(task)
  if mpm is not None:
    return mpm.package_name
  return None


def _get_mpm_label(task: task_pb2.Task) -> Optional[str]:
  mpm = _get_mpm(task)
  if mpm is not None:
    return mpm.label
  return None


class TasksTest(googletest.TestCase):

  def test_unique_ids(self):
    """Ensures that all task IDs are truly unique."""
    current_ids = set()

    def check_unique_ids(task: task_pb2.Task) -> None:
      self.assertNotIn(task.id, current_ids)
      current_ids.add(task.id)

    _run_check(check_unique_ids)

  def test_no_unspecified_apk_sources(self):
    """Ensures that all if tasks have InstallApks, they are not UNSPECIFIED."""

    def check_unspecified_task(task: task_pb2.Task) -> None:

      def check_setup_step(setup_step: task_pb2.SetupStep):
        install_apk = _get_install_apk_cmd(setup_step)
        if not install_apk:
          return

        self.assertNotEqual(
            install_apk.apk_source,
            task_pb2.AdbCall.InstallApk.ApkSource.UNSPECIFIED,
            msg=f'In task {task}, SetupStep {setup_step} has unspecified '
            'ApkSource.')

      for step in task.setup_steps:
        check_setup_step(step)
      for step in task.reset_steps:
        check_setup_step(step)

    _run_check(check_unspecified_task)

  def test_first_party_only_in_whitelist(self):
    # These are the mpm packages containing the APKs that we consider first
    # party.
    whitelist = [
        'learning/deepmind/research/xgames/android/apks/catch_the_ball',
        'learning/deepmind/research/xgames/android/apks/floodit',
        'learning/deepmind/research/xgames/android/apks/mdp',
        'learning/deepmind/research/xgames/android/apks/nostalgic_racer',
        'learning/deepmind/research/xgames/android/apks/perfection',
        'learning/deepmind/research/xgames/android/apks/shakespell',
        'learning/deepmind/research/xgames/android/apks/ui_test',
        'learning/deepmind/research/xgames/android/apks/android_world',
    ]

    def check_whitelist(task: task_pb2.Task) -> None:

      def check_setup_step(setup_step: task_pb2.SetupStep):
        install_apk = _get_install_apk_cmd(setup_step)
        if not install_apk:
          return

        if (install_apk.apk_source !=
            task_pb2.AdbCall.InstallApk.ApkSource.FIRST_PARTY):
          return

        mpm_package_name = _get_mpm_package_name(task)
        if mpm_package_name is not None:
          self.assertIn(mpm_package_name, whitelist)

      for step in task.setup_steps:
        check_setup_step(step)
      for step in task.reset_steps:
        check_setup_step(step)

    _run_check(check_whitelist)

  def test_first_party_and_built_internally_use_mpm(self):
    """Tasks that are first-party or built internally should come from MPM."""

    def check_mpm_location(task: task_pb2.Task) -> None:

      def check_setup_step(setup_step: task_pb2.SetupStep):
        install_apk = _get_install_apk_cmd(setup_step)
        if not install_apk:
          return

        if (install_apk.apk_source !=
            task_pb2.AdbCall.InstallApk.ApkSource.FIRST_PARTY or
            install_apk.apk_source !=
            task_pb2.AdbCall.InstallApk.ApkSource.BUILT_INTERNALLY):
          return

        self.assertIsNotNone(_get_mpm_package_name(task))

      for step in task.setup_steps:
        check_setup_step(step)
      for step in task.reset_steps:
        check_setup_step(step)

    _run_check(check_mpm_location)

  # TODO(b/172920540) Move to Guitar workflow.
  def test_label_exists(self):
    """Tasks that are first-party or built internally should come from MPM."""

    self.skipTest('This test is not hermetic, it uses data from production MPM')
    mpm_lib = mpmlib.MPMLib()

    def check_label_exists(task: task_pb2.Task) -> None:
      package_name = _get_mpm_package_name(task)
      if package_name is None:
        return
      label = _get_mpm_label(task)
      self.assertIsNotNone(label)
      version = mpm_lib.GetLabelVersion(pkgname=package_name, label=label)
      self.assertIsNotNone(version)

    _run_check(check_label_exists)


if __name__ == '__main__':
  googletest.main()
