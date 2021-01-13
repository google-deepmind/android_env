"""The different kinds of actions that AndroidEnv supports."""

import enum


class ActionType(enum.IntEnum):
  """Integer values to describe each supported action in AndroidEnv."""
  TOUCH = 0
  LIFT = 1
  REPEAT = 2
