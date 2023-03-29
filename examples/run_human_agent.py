# coding=utf-8
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

"""Loads an interactive session where a human acts on behalf of an agent."""

import time
from typing import Any, Dict

from absl import app
from absl import flags
from absl import logging
from android_env import loader
from android_env.components import action_type
from android_env.components import utils
import dm_env
import numpy as np
import pygame

# Simulator args.
flags.DEFINE_string('avd_name', None, 'Name of AVD to use.')
flags.DEFINE_string('android_avd_home', '~/.android/avd', 'Path to AVD.')
flags.DEFINE_string('android_sdk_root', '~/Android/Sdk', 'Path to SDK.')
flags.DEFINE_string('emulator_path',
                    '~/Android/Sdk/emulator/emulator', 'Path to emulator.')
flags.DEFINE_string('adb_path',
                    '~/Android/Sdk/platform-tools/adb', 'Path to ADB.')
flags.DEFINE_boolean('run_headless', True, 'Optionally turn off display.')

# Environment args.
flags.DEFINE_string('task_path', None, 'Path to task textproto file.')

# Pygame args.
flags.DEFINE_list('screen_size', '480,720', 'Screen width, height in pixels.')
flags.DEFINE_float('frame_rate', 1.0/30.0, 'Frame rate in seconds.')

FLAGS = flags.FLAGS


def _get_action_from_event(event: pygame.event.Event, screen: pygame.Surface,
                           orientation: int) -> Dict[str, Any]:
  """Returns the current action by reading data from a pygame Event object."""

  act_type = action_type.ActionType.LIFT
  if event.type == pygame.MOUSEBUTTONDOWN:
    act_type = action_type.ActionType.TOUCH

  return {
      'action_type':
          np.array(act_type, dtype=np.int32),
      'touch_position':
          _scale_position(event.pos, screen, orientation),
  }


def _get_action_from_mouse(screen: pygame.Surface,
                           orientation: int) -> Dict[str, Any]:
  """Returns the current action by reading data from the mouse."""

  act_type = action_type.ActionType.LIFT
  if pygame.mouse.get_pressed()[0]:
    act_type = action_type.ActionType.TOUCH

  return {
      'action_type':
          np.array(act_type, dtype=np.int32),
      'touch_position':
          _scale_position(pygame.mouse.get_pos(), screen, orientation),
  }


def _scale_position(position: np.ndarray, screen: pygame.Surface,
                    orientation: int) -> np.ndarray:
  """AndroidEnv accepts mouse inputs as floats so we need to scale it."""

  scaled_pos = np.divide(position, screen.get_size(), dtype=np.float32)
  if orientation == 1:  # LANDSCAPE_90
    scaled_pos = scaled_pos[::-1]
    scaled_pos[0] = 1 - scaled_pos[0]
  return scaled_pos


def _accumulate_reward(
    timestep: dm_env.TimeStep,
    episode_return: float) -> float:
  """Accumulates rewards collected over the course of an episode."""

  if timestep.reward and timestep.reward != 0:
    logging.info('Reward: %s', timestep.reward)
    episode_return += timestep.reward

  if timestep.first():
    episode_return = 0
  elif timestep.last():
    logging.info('Episode return: %s', episode_return)

  return episode_return


def _render_pygame_frame(surface: pygame.Surface, screen: pygame.Surface,
                         orientation: int, timestep: dm_env.TimeStep) -> None:
  """Displays latest observation on pygame surface."""

  frame = timestep.observation['pixels'][:, :, :3]  # (H x W x C) (RGB)
  frame = utils.transpose_pixels(frame)  # (W x H x C)
  frame = utils.orient_pixels(frame, orientation)

  pygame.surfarray.blit_array(surface, frame)
  pygame.transform.smoothscale(surface, screen.get_size(), screen)

  pygame.display.flip()


def main(_):

  pygame.init()
  pygame.display.set_caption('android_human_agent')

  with loader.load(
      emulator_path=FLAGS.emulator_path,
      android_sdk_root=FLAGS.android_sdk_root,
      android_avd_home=FLAGS.android_avd_home,
      avd_name=FLAGS.avd_name,
      adb_path=FLAGS.adb_path,
      task_path=FLAGS.task_path,
      run_headless=FLAGS.run_headless) as env:

    # Reset environment.
    first_timestep = env.reset()
    orientation = np.argmax(first_timestep.observation['orientation'])

    # Create pygame canvas.
    screen_size = list(map(int, FLAGS.screen_size))  # (W x H)
    obs_shape = env.observation_spec()['pixels'].shape[:2]  # (H x W)

    if (orientation == 1 or orientation == 3):  # LANDSCAPE_90 | LANDSCAPE_270
      screen_size = screen_size[::-1]
      obs_shape = obs_shape[::-1]

    screen = pygame.display.set_mode(screen_size)  # takes (W x H)
    surface = pygame.Surface(obs_shape[::-1])  # takes (W x H)

    # Start game loop.
    prev_frame = time.time()
    episode_return = 0

    while True:
      if pygame.key.get_pressed()[pygame.K_ESCAPE]:
        return

      all_events = pygame.event.get()
      for event in all_events:
        if event.type == pygame.QUIT:
          return

      # Filter event queue for mouse click events.
      mouse_click_events = [
          event for event in all_events
          if event.type in [pygame.MOUSEBUTTONDOWN, pygame.MOUSEBUTTONUP]
      ]

      # Process all mouse click events.
      for event in mouse_click_events:
        action = _get_action_from_event(event, screen, orientation)
        timestep = env.step(action)
        episode_return = _accumulate_reward(timestep, episode_return)
        _render_pygame_frame(surface, screen, orientation, timestep)

      # Sample the current position of the mouse either way.
      action = _get_action_from_mouse(screen, orientation)
      timestep = env.step(action)
      episode_return = _accumulate_reward(timestep, episode_return)
      _render_pygame_frame(surface, screen, orientation, timestep)

      # Limit framerate.
      now = time.time()
      frame_time = now - prev_frame
      if frame_time < FLAGS.frame_rate:
        time.sleep(FLAGS.frame_rate - frame_time)
      prev_frame = now


if __name__ == '__main__':
  logging.set_verbosity('info')
  logging.set_stderrthreshold('info')
  flags.mark_flags_as_required(['avd_name', 'task_path'])
  app.run(main)
