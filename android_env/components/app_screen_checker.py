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

"""Determines if the current app screen matches an expected app screen."""

from collections.abc import Callable, Sequence
import enum
import re
import time
from typing import Self

from absl import logging
from android_env.components import adb_call_parser as adb_call_parser_lib
from android_env.components import errors
from android_env.proto import adb_pb2
from android_env.proto import task_pb2


class _DumpsysNode:
  """A node in a dumpsys tree."""

  def __init__(self, data: str):
    self._children = []
    self._data = data

  @property
  def data(self) -> str:
    return self._data

  @property
  def children(self) -> list[Self]:
    return self._children

  def find_child(
      self, predicate: Callable[[Self], bool], max_levels: int = 0
  ) -> Self | None:
    """Returns the first direct child that matches `predicate`, None otherwise.

    Args:
      predicate: Function-like that accepts a _DumpsysNode and returns boolean.
      max_levels: Maximum number of levels down the tree to search for a child.
        If non-positive, only direct children will be searched for.

    Returns:
      A _DumpsysNode or None.
    """
    if not self.children:
      return None

    try:
      return next(x for x in self.children if predicate(x))
    except StopIteration:
      logging.info('Failed to find child. max_levels: %i.', max_levels)
      # Search children.
      if max_levels:
        for child in self.children:
          child_result = child.find_child(predicate, max_levels - 1)
          if child_result is not None:
            return child_result

      return None

  def __repr__(self):
    return self._data

  def print_tree(self, indent: int = 2):
    """Prints this tree in logging.info()."""
    logging.info(' ' * indent + self.data)
    for c in self.children:
      c.print_tree(indent + 2)


def build_tree_from_dumpsys_output(dumpsys_output: str) -> _DumpsysNode:
  """Constructs a tree from a dumpsys string output.

  Args:
    dumpsys_output: string Verbatim output from adb dumpsys. The expected format
      is a list where each line is a node and the indentation marks the
      relationship with its parent or sibling.

  Returns:
    _DumpsysNode The root of the tree.
  """
  lines = dumpsys_output.split('\n')  # Split by lines.
  lines = [x.rstrip(' \r') for x in lines]
  lines = [x for x in lines if len(x)]  # Remove empty lines.

  root = _DumpsysNode('___root___')  # The root of all nodes.
  parents_stack = [root]
  for line in lines:
    stripped_line = line.lstrip(' ')
    indent = len(line) - len(stripped_line)  # Number of indent spaces.
    new_node = _DumpsysNode(stripped_line)  # Create a node without indentation.

    parent = parents_stack.pop()
    if parent.data == '___root___':  # The root is an exception for indentation.
      parent_indent = -2
    else:
      parent_indent = (len(parents_stack) - 1) * 2

    if indent == parent_indent:  # `new_node` is a sibiling.
      parent = parents_stack.pop()
    elif indent < parent_indent:  # Indentation reduced (i.e. a block finished)
      num_levels = (indent // 2) + 1
      parents_stack = parents_stack[:num_levels]
      parent = parents_stack.pop()
    elif indent > parent_indent:  # `new_node` is a child.
      pass  # No need to change the current parent.

    parent.children.append(new_node)
    parents_stack.append(parent)
    parents_stack.append(new_node)

  return root


def matches_path(
    dumpsys_activity_output: str,
    expected_view_hierarchy_path: Sequence[re.Pattern[str]],
    max_levels: int = 0,
) -> bool:
  """Returns True if the current dumpsys output matches the expected path.

  Args:
    dumpsys_activity_output: The output of running `dumpsys activity ...`.
    expected_view_hierarchy_path: [regex] A list of regular expressions to be
      tested at each level of the tree.
    max_levels: How many levels to search from root for View Hierarchy.

  Returns:
    True if the dumpsys tree contains one path that matches all regexes.
  """
  root = build_tree_from_dumpsys_output(dumpsys_activity_output)

  # Find the View Hierarchy.
  view_hierarchy = root.find_child(
      lambda x: x.data.startswith('View Hierarchy'), max_levels)
  if view_hierarchy is None:
    logging.error(
        'view_hierarchy is None. Dumpsys activity output: %s. tree: %r',
        str(dumpsys_activity_output), root.print_tree())
    logging.error('Tree root: %s', str(root))
    return False

  current_node = view_hierarchy
  for i, regex in enumerate(expected_view_hierarchy_path):

    def regex_predicate(node, expr=regex):
      matches = expr.match(node.data)
      return matches is not None

    child = current_node.find_child(regex_predicate)
    if child is None:
      logging.error('Mismatched regex (%i, %s). current_node: %s', i,
                    regex.pattern, current_node)
      logging.error('Dumpsys activity output: %s', str(dumpsys_activity_output))
      logging.error('Tree root: %s', str(root))
      return False
    else:
      current_node = child
  return True


class AppScreenChecker:
  """Checks that the current app screen matches an expected screen."""

  class Outcome(enum.IntEnum):
    """Possible return vales from checking the current app screen."""
    # The current app screen matches the expected app screen.
    SUCCESS = 0
    # There's no activity to check.
    EMPTY_EXPECTED_ACTIVITY = 1
    # We were unable to determine the current activity.
    FAILED_ACTIVITY_EXTRACTION = 2
    # The current activity does not match the expected activity.
    UNEXPECTED_ACTIVITY = 3
    # The current view hierarchy does not match the expected view hierarchy.
    UNEXPECTED_VIEW_HIERARCHY = 4

  def __init__(self, adb_call_parser: adb_call_parser_lib.AdbCallParser,
               expected_app_screen: task_pb2.AppScreen):
    self._adb_call_parser = adb_call_parser
    self._expected_app_screen = expected_app_screen
    self._expected_activity = expected_app_screen.activity
    self._expected_view_hierarchy_path = [
        re.compile(regex) for regex in expected_app_screen.view_hierarchy_path
    ]

  # Return type is AppScreenChecker.Outcome, but pytype doesn't understand that.
  def matches_current_app_screen(self) -> enum.IntEnum:
    """Determines whether the current app screen matches `expected_app_screen`."""
    if not self._expected_activity:
      return AppScreenChecker.Outcome.EMPTY_EXPECTED_ACTIVITY

    # Check if we are still on the expected Activity.
    response = self._adb_call_parser.parse(
        adb_pb2.AdbRequest(
            get_current_activity=adb_pb2.AdbRequest.GetCurrentActivity()))
    if response.status != adb_pb2.AdbResponse.OK:
      return AppScreenChecker.Outcome.FAILED_ACTIVITY_EXTRACTION

    current_activity = response.get_current_activity.full_activity
    if current_activity != self._expected_activity:
      logging.error('current_activity: %s,  expected_activity: %s',
                    current_activity, self._expected_activity)
      return AppScreenChecker.Outcome.UNEXPECTED_ACTIVITY

    # Extract just the package name from the full activity name.
    package_name = self._expected_activity.split('/')[0]

    # Check if we are in the expected view hierarchy path.
    if self._expected_view_hierarchy_path:
      dumpsys_response = self._adb_call_parser.parse(
          adb_pb2.AdbRequest(
              dumpsys=adb_pb2.AdbRequest.DumpsysRequest(
                  service='activity', args=[package_name, package_name])))
      if dumpsys_response.status != adb_pb2.AdbResponse.OK:
        return AppScreenChecker.Outcome.FAILED_ACTIVITY_EXTRACTION

      if dumpsys_response.dumpsys.output:
        if not matches_path(
            dumpsys_response.dumpsys.output.decode('utf-8'),
            self._expected_view_hierarchy_path,
            max_levels=3):
          return AppScreenChecker.Outcome.UNEXPECTED_VIEW_HIERARCHY

    return AppScreenChecker.Outcome.SUCCESS

  def wait_for_app_screen(self, timeout_sec: float) -> float:
    """Waits for `self._expected_app_screen` to be the current screen.

    Args:
      timeout_sec: Maximum total time to wait for the screen to pop up.

    Returns:
      The total amount of time in seconds spent waiting for the screen to pop
      up.
    Raises:
      errors.WaitForAppScreenError if the screen does not pop up within
      `timeout_sec`.
    """

    logging.info('Waiting for app screen...')
    start_time = time.time()
    while time.time() - start_time < timeout_sec:
      if self.matches_current_app_screen() == AppScreenChecker.Outcome.SUCCESS:
        wait_time = time.time() - start_time
        logging.info('Successfully waited for app screen in %r seconds: [%r]',
                     wait_time, self._expected_app_screen)
        return wait_time
      time.sleep(0.1)

    wait_time = time.time() - start_time
    logging.error('Failed to wait for app screen in %r seconds: [%r].',
                  wait_time, self._expected_app_screen)

    raise errors.WaitForAppScreenError()
