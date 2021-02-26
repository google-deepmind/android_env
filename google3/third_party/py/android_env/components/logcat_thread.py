"""A class the launches a thread to read Android logcat outputs."""

import ast
import json
import re
import subprocess
import threading
from typing import List

from absl import logging
from android_env.components import thread_function
from android_env.proto import task_pb2

import numpy as np


class LogcatThread(thread_function.ThreadFunction):
  """Reads ADB logcat entries in a separate thread."""

  def __init__(
      self,
      adb_command_prefix: List[str],
      log_parsing_config: task_pb2.LogParsingConfig,
      print_all_lines: bool = False,
      block_input: bool = True,
      block_output: bool = False,
      name: str = 'logcat',
  ):
    """Initializes this LogcatThread with optional filters.

    Please see https://developer.android.com/studio/command-line/logcat for more
    info on `logcat`.

    Args:
      adb_command_prefix: Command for connecting to a particular ADB.
      log_parsing_config: Determines the types of messages we want logcat to
        match. Contains `filters`, `log_prefix` and `log_regexps`.
      print_all_lines: Whether to print all lines we observe in the logcat
        stream. This is useful to debug problems in Android itself.
      block_input: Whether to block this thread when reading its input queue.
      block_output: Whether to block this thread when writing to its output
        queue.
      name: Name of the thread.
    """

    self._print_all_lines = print_all_lines
    self._lock = threading.Lock()
    self._latest_score = 0.0
    self._latest_reward = 0.0
    self._latest_extras = {}
    self._message_regexp = None
    self._message_received = False
    self._episode_ended = False
    self._max_buffer_size = 100

    self._log_prefix = log_parsing_config.log_prefix
    self._regexps = log_parsing_config.log_regexps

    filters = list(log_parsing_config.filters) + ['*:S']
    cmd = adb_command_prefix + ['logcat', '-v', 'epoch'] + filters
    logging.info('Logcat command: %s', ' '.join(cmd))

    self._proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        bufsize=1,
        universal_newlines=True)
    self._stdout = self._proc.stdout

    super().__init__(
        block_input=block_input, block_output=block_output, name=name)

  def reset_counters(self) -> None:
    with self._lock:
      self._latest_score = 0.0
      self._latest_reward = 0.0
      self._latest_extras = {}
      self._episode_ended = False
      self._message_received = False

  def kill(self):
    self._proc.kill()
    super().kill()

  def listen_for_message(self, message: str):
    with self._lock:
      self._message_regexp = re.compile(r'^%s$' % message)
      self._message_received = False

  def has_received_message(self) -> bool:
    return self._message_received

  def get_and_reset_reward(self) -> float:
    with self._lock:
      r = self._latest_reward
      self._latest_reward = 0.0
      return r

  def get_and_reset_episode_end(self) -> bool:
    with self._lock:
      end = self._episode_ended
      self._episode_ended = False
      return end

  def get_and_reset_extras(self):
    with self._lock:
      extras = {}
      for extra_name, extra_values in self._latest_extras.items():
        extras[extra_name] = np.stack(extra_values)
      self._latest_extras = {}
      return extras

  def _process_extra(self, extra_name, extra):
    extra = np.array(extra)
    with self._lock:
      if extra_name in self._latest_extras:
        # If latest extra is not flushed, append.
        if len(self._latest_extras[extra_name]) >= self._max_buffer_size:
          self._latest_extras[extra_name].pop(0)
        self._latest_extras[extra_name].append(extra)
      else:
        self._latest_extras[extra_name] = [extra]

  def main(self) -> None:
    # pylint: disable=g-line-too-long
    # Format is: "TIME_SEC PID TID PRIORITY TAG: MESSAGE"
    #
    # Example:
    #  '         1553110400.424  5583  5658 D NostalgicRacer: com.google.example.games.nostalgicracer.views.renderers.OpenGLRenderDriver@912fb8.onSurfaceChanged 480x320'    #
    #
    # If a log_prefix is given, then the format becomes:
    # "TIME_SEC PID TID PRIORITY TAG: LOG_PREFIX MESSAGE"
    # pylint: enable=g-line-too-long

    regexp = r"""
      ^                                   # Beginning of the line.
      [ ]+(?P<timestamp>[0-9]+\.[0-9]+)   # Spaces and a float.
      [ ]+(?P<pid>[0-9]+)                 # Spaces and an int.
      [ ]+(?P<tid>[0-9]+)                 # Spaces and an int.
      [ ]+(?P<priority>.)                 # Spaces and any single character.
      [ ]+(?P<tag>[^:]*):                 # Spaces and any char that's not ':'.
    """
    if self._log_prefix:
      regexp += f'[ ]+{self._log_prefix}'

    regexp += r"""[ ](?P<message>.*)$"""
    logline_re = re.compile(regexp, re.VERBOSE)

    # Defaults to 'a^' since that regex matches no string by definition.
    score_regexp = re.compile(self._regexps.score or 'a^')
    reward_regexp = re.compile(self._regexps.reward or 'a^')
    episode_end_regexp = re.compile(self._regexps.episode_end or 'a^')
    extra_regexp = re.compile(self._regexps.extra or 'a^')
    json_extra_regexp = re.compile(self._regexps.json_extra or 'a^')

    for line in self._stdout:
      # We never hand back control to ThreadFunction._run() so we need to
      # explicitly check for self._should_run here.
      if not self._should_run:
        break

      if self._print_all_lines:
        logging.info('line: %r', line)

      if not line:  # Skip empty lines.
        continue

      # We're currently only consuming `message`, but we may use the other
      # fields in the future.
      matches = logline_re.match(line)
      if not matches or len(matches.groups()) != 6:
        continue

      if self._message_regexp is not None and not self._message_received:
        message_matches = self._message_regexp.match(matches.group('message'))
        if message_matches:
          with self._lock:
            self._message_received = True

      # Search for rewards and scores in the log message.
      # The way this works is that each application would typically only use one
      # of these.
      # Score is more convenient for games. In this case the reward is computed
      # to be the current score - the previous score.
      # If the app directly specifies the reward, then the score will be
      # ignored.

      # Match rewards.
      reward_matches = reward_regexp.match(matches.group('message'))
      if reward_matches:
        reward = float(reward_matches.group(1))
        with self._lock:
          self._latest_reward += reward
        continue

      # Match scores.
      score_matches = score_regexp.match(matches.group('message'))
      if score_matches:
        current_score = float(score_matches.group(1))
        with self._lock:
          current_reward = current_score - self._latest_score
          self._latest_score = current_score
          self._latest_reward += current_reward
        continue

      # Match episode ends.
      episode_end_matches = episode_end_regexp.match(matches.group('message'))
      if episode_end_matches:
        with self._lock:
          self._episode_ended = True
        continue

      # Match extras.
      extra_matches = extra_regexp.match(matches.group('message'))
      if extra_matches:
        extra_name = extra_matches.group('name')
        extra = extra_matches.group('extra')
        if extra:
          try:
            extra = ast.literal_eval(extra)
          # Except all to avoid unnecessary crashes, only log error.
          except Exception:  # pylint: disable=broad-except
            logging.exception('Could not parse extra: %s', extra)
            continue
        else:
          # No extra value provided for boolean extra. Setting value to True.
          extra = 1
        self._process_extra(extra_name, extra)
        continue

      # Match JSON extras.
      json_extra_matches = json_extra_regexp.match(matches.group('message'))
      if json_extra_matches:
        extra_data = json_extra_matches.group('json_extra')
        try:
          extra = dict(json.loads(extra_data))
        except ValueError:
          logging.error('JSON string could not be parsed to a dictionary: %s',
                        extra_data)
          continue
        for extra_name, extra_value in extra.items():
          self._process_extra(extra_name, extra_value)
        continue
