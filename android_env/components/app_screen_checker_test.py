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

"""Tests for android_env.components.app_screen_checker."""

import re
import timeit
from unittest import mock

from absl import flags
from absl.testing import absltest
from android_env.components import adb_call_parser
from android_env.components import app_screen_checker
from android_env.components import errors
from android_env.proto import adb_pb2
from android_env.proto import task_pb2

# Benchmarks take ~2 minutes to run, so they are disabled by default.
# Run with --test_arg=--run_benchmarks to enable.
_RUN_BENCHMARKS = flags.DEFINE_bool(
    'run_benchmarks', False, 'Whether to run microbenchmarks.'
)


def _flatten_tree(
    tree: app_screen_checker._DumpsysNode, flat_tree: list[str], indent: int = 2
):
  """Appends a list of strings to `flat_tree` from `tree`."""
  flat_tree.append(' ' * indent + tree.data)
  for c in tree.children:
    _flatten_tree(c, flat_tree, indent + 2)


class AppScreenCheckerTest(absltest.TestCase):

  # Ensures that build_tree_from_dumpsys_output produces a node whose flat
  # representation matches our expectation from an arbitrary hierarchy.
  def test_build_tree_from_dumpsys_output(self):
    dumpsys_output = """
Queen Elizabeth II
  Charles
    William
      George
      Charlotte
      Louis
    Harry
      Archie
  Anne
    Peter
      Savannah
      Isla
    Zara
      Mia
      Lena
  Andrew
    Beatrice
    Eugenie
  Edward
    Louise
    James
"""
    tree = app_screen_checker.build_tree_from_dumpsys_output(dumpsys_output)
    flat_tree = []
    _flatten_tree(tree, flat_tree, indent=2)
    self.assertEqual(flat_tree, [
        '  ___root___',
        '    Queen Elizabeth II',
        '      Charles',
        '        William',
        '          George',
        '          Charlotte',
        '          Louis',
        '        Harry',
        '          Archie',
        '      Anne',
        '        Peter',
        '          Savannah',
        '          Isla',
        '        Zara',
        '          Mia',
        '          Lena',
        '      Andrew',
        '        Beatrice',
        '        Eugenie',
        '      Edward',
        '        Louise',
        '        James',
    ])

  # Ensures that build_tree_from_dumpsys_output produces a node whose flat
  # representation matches our expectation from an arbitrary hierarchy.
  def test_build_forest_from_dumpsys_output(self):
    dumpsys_output = """
Tree1
  Branch1
    Leaf1
    Leaf2
  Branch2
    Leaf3
    Leaf4
    Leaf5
Tree2
  Branch3
    Leaf6
    Leaf7
  Branch4
    Leaf8
    Leaf9
    Leaf10
  Leaf11
"""
    tree = app_screen_checker.build_tree_from_dumpsys_output(dumpsys_output)
    flat_tree = []
    _flatten_tree(tree, flat_tree, indent=2)
    self.assertEqual(flat_tree, [
        '  ___root___',
        '    Tree1',
        '      Branch1',
        '        Leaf1',
        '        Leaf2',
        '      Branch2',
        '        Leaf3',
        '        Leaf4',
        '        Leaf5',
        '    Tree2',
        '      Branch3',
        '        Leaf6',
        '        Leaf7',
        '      Branch4',
        '        Leaf8',
        '        Leaf9',
        '        Leaf10',
        '      Leaf11',
    ])

  def test_no_view_hierarchy_matches_path(self):
    dumpsys_output = """
TASK
  ACTIVITY
    Missing View Hierarchy
      A
        B
        C
      D
        E
          F
"""
    expected_path = ['^A$', 'B$']
    expected_view_hierarchy_path = [
        re.compile(regex) for regex in expected_path
    ]
    self.assertFalse(
        app_screen_checker.matches_path(dumpsys_output,
                                        expected_view_hierarchy_path))

  def test_matches_path(self):
    dumpsys_output = """
TASK
  ACTIVITY
    Some node we don't care
      Blah

    View Hierarchy
      Hirohito
        Akihito
          Naruhito
            Aiko
          Fumihito
            Mako
            Kako
            Hisahito
        Masahito
"""
    expected_path = ['^Hirohito$', 'Akihito$', 'Fumihito$', 'Kako$']
    expected_view_hierarchy_path = [
        re.compile(regex) for regex in expected_path
    ]
    self.assertTrue(
        app_screen_checker.matches_path(
            dumpsys_output, expected_view_hierarchy_path, max_levels=2))

    # Also check that the following path does not match anything in the tree.
    expected_path = ['^Hirohito$', 'Akihito$', 'Fumihito$', 'Kenji$']
    expected_view_hierarchy_path = [
        re.compile(regex) for regex in expected_path
    ]
    self.assertFalse(
        app_screen_checker.matches_path(dumpsys_output,
                                        expected_view_hierarchy_path))

  def test_matches_path_one_level_deep(self):
    dumpsys_output = """
TASK
  ACTIVITY
    Some node we don't care
      Blah

    Some intermediate node
      View Hierarchy
        Hirohito
          Akihito
            Naruhito
              Aiko
            Fumihito
              Mako
              Kako
              Hisahito
          Masahito
"""
    expected_path = ['^Hirohito$', 'Akihito$', 'Fumihito$', 'Kako$']
    expected_view_hierarchy_path = [
        re.compile(regex) for regex in expected_path
    ]
    self.assertTrue(
        app_screen_checker.matches_path(
            dumpsys_output, expected_view_hierarchy_path, max_levels=3))

    # Also check that the view hierarchy is not found when searching only grand
    # children of TASK.
    expected_path = ['^Hirohito$', 'Akihito$', 'Fumihito$', 'Kako$']
    expected_view_hierarchy_path = [
        re.compile(regex) for regex in expected_path
    ]
    self.assertFalse(
        app_screen_checker.matches_path(
            dumpsys_output, expected_view_hierarchy_path, max_levels=2))

  def test_wait_for_app_screen_zero_timeout(self):
    """Ensures that an exception is raised if the timeout is passed."""
    app_screen = task_pb2.AppScreen(activity='whatever.MyActivity')
    call_parser = mock.create_autospec(adb_call_parser.AdbCallParser)
    screen_checker = app_screen_checker.AppScreenChecker(
        adb_call_parser=call_parser,
        expected_app_screen=app_screen)
    # With a zero timeout, the method should never be able to wait for the
    # screen to pop up and an exception should be raised.
    self.assertRaises(
        errors.WaitForAppScreenError,
        screen_checker.wait_for_app_screen,
        timeout_sec=0.0)

  def test_wait_for_app_screen_successful(self):
    """Ensures that with the right conditions, the app screen should pop up."""
    app_screen = task_pb2.AppScreen(activity='my.favorite.AwesomeActivity')
    call_parser = mock.create_autospec(adb_call_parser.AdbCallParser)
    call_parser.parse.return_value = adb_pb2.AdbResponse(
        status=adb_pb2.AdbResponse.Status.OK,
        get_current_activity=adb_pb2.AdbResponse.GetCurrentActivityResponse(
            full_activity='my.favorite.AwesomeActivity'))

    screen_checker = app_screen_checker.AppScreenChecker(
        call_parser, app_screen)
    timeout = 1.0
    wait_time = screen_checker.wait_for_app_screen(timeout_sec=timeout)

    # The call should not generate an exception and the return value should be
    # less than the timeout given.
    self.assertLess(wait_time, timeout)


class AppScreenCheckerBenchmark(absltest.TestCase):

  def setUp(self):
    super().setUp()
    if not _RUN_BENCHMARKS.value:
      self.skipTest('Benchmark disabled. Run with --test_arg=--run_benchmarks')

  def test_build_tree_from_dumpsys_output(self):
    # A larger synthetic dumpsys output to simulate real-world scenario.
    # We repeat the tree structure to make it larger.
    single_tree = """
    View Hierarchy
      Node_0
        Node_0_0
          Node_0_0_0
            Node_0_0_0_0
          Node_0_0_1
            Node_0_0_1_0
            Node_0_0_1_1
            Node_0_0_1_2
        Node_0_1
          Node_0_1_0
          Node_0_1_1
      Node_1
        Node_1_0
        Node_1_1
    """
    # Let's repeat it to make it ~1000 lines.
    dumpsys_output = 'TASK\n  ACTIVITY\n'
    for i in range(50):
      dumpsys_output += f'    View Hierarchy {i}\n'
      for line in single_tree.strip().split('\n'):
        if line.strip():
          dumpsys_output += '      ' + line + '\n'

    setup = (
        'from android_env.components import app_screen_checker; '
        f'dumpsys_output = """{dumpsys_output}"""'
    )
    stmt = 'app_screen_checker.build_tree_from_dumpsys_output(dumpsys_output)'
    t = timeit.Timer(stmt, setup=setup)
    number = 100
    res = t.timeit(number=number)
    print(
        '\nbuild_tree_from_dumpsys_output (~1000 lines):'
        f' {res / number * 1e3:.3f} ms per loop'
    )

  def test_matches_path(self):
    # Use a large dumpsys output and match a path.
    single_tree = """
    View Hierarchy
      Node_0
        Node_0_0
          Node_0_0_0
            Node_0_0_0_0
          Node_0_0_1
            Node_0_0_1_0
            Node_0_0_1_1
            Node_0_0_1_2
        Node_0_1
          Node_0_1_0
          Node_0_1_1
      Node_1
        Node_1_0
        Node_1_1
    """
    dumpsys_output = 'TASK\n  ACTIVITY\n'
    for i in range(50):
      dumpsys_output += f'    View Hierarchy_{i}\n'
      for line in single_tree.strip().split('\n'):
        if line.strip():
          dumpsys_output += '      ' + line + '\n'
    # Add target view hierarchy at the end
    dumpsys_output += """
    View Hierarchy
      Hirohito
        Akihito
          Naruhito
            Aiko
          Fumihito
            Mako
            Kako
            Hisahito
        Masahito
    """

    expected_path = ['^Hirohito$', 'Akihito$', 'Fumihito$', 'Kako$']
    setup = (
        'from android_env.components import app_screen_checker; import re;'
        f' dumpsys_output = """{dumpsys_output}"""; expected_path ='
        f' {expected_path}; expected_view_hierarchy_path = [re.compile(regex)'
        ' for regex in expected_path]'
    )
    stmt = (
        'app_screen_checker.matches_path(dumpsys_output,'
        ' expected_view_hierarchy_path, max_levels=100)'
    )
    t = timeit.Timer(stmt, setup=setup)
    number = 100
    res = t.timeit(number=number)
    print(f'\nmatches_path (~1000 lines): {res / number * 1e3:.3f} ms per loop')


if __name__ == '__main__':
  absltest.main()
