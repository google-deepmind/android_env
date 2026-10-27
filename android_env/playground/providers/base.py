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

"""Base abstraction for multi-model LLM providers in AndroidEnv Playground."""

import abc
import base64
from collections.abc import Sequence
import dataclasses
import re
from typing import Any

SWIPE_COORDINATES: dict[str, dict[str, float]] = {
    'DOWN': {'start_x': 0.50, 'start_y': 0.48, 'end_x': 0.50, 'end_y': 0.68},
    'LEFT': {'start_x': 0.74, 'start_y': 0.58, 'end_x': 0.26, 'end_y': 0.58},
    'RIGHT': {'start_x': 0.26, 'start_y': 0.58, 'end_x': 0.74, 'end_y': 0.58},
    'UP': {'start_x': 0.50, 'start_y': 0.68, 'end_x': 0.50, 'end_y': 0.48},
}


def normalize_2048_action(plan: dict[str, Any]) -> dict[str, Any]:
  """Translates direction outputs ('UP', 'DOWN', 'LEFT', 'RIGHT') to swipes."""
  if not isinstance(plan, dict):
    plan = {'thought': str(plan), 'direction': 'DOWN'}

  direction_str = (
      plan.get('direction')
      or plan.get('move')
      or plan.get('action')
      or plan.get('swipe')
  )

  if not direction_str:
    tool_val = plan.get('tool', '')
    if isinstance(tool_val, str) and tool_val.upper() in SWIPE_COORDINATES:
      direction_str = tool_val.upper()
    elif isinstance(plan.get('args'), dict) and plan['args'].get('direction'):
      direction_str = plan['args']['direction']

  if not direction_str and 'thought' in plan:
    thought_text = str(plan['thought'])
    matches = re.findall(
        r'\b(UP|DOWN|LEFT|RIGHT)\b', thought_text, re.IGNORECASE
    )
    if matches:
      direction_str = matches[-1]

  if direction_str and isinstance(direction_str, str):
    dir_upper = direction_str.strip().upper()
    for d, coords in SWIPE_COORDINATES.items():
      if d in dir_upper:
        plan['tool'] = 'swipe'
        plan['args'] = dict(coords)
        plan['is_done'] = False
        return plan

  if plan.get('tool') == 'swipe' and isinstance(plan.get('args'), dict):
    plan.setdefault('is_done', False)
    return plan

  plan['tool'] = 'invalid'
  plan['args'] = {}
  plan.setdefault('is_done', False)
  return plan


def normalize_action(plan: dict[str, Any], goal: str = '') -> dict[str, Any]:
  """Translates model outputs to normalized MCP tool calls (`swipe`, `tap`)."""
  if not isinstance(plan, dict):
    plan = {'thought': str(plan)}

  if plan.get('tool') == 'invalid':
    plan.setdefault('is_done', False)
    return plan

  goal_lower = goal.lower()
  is_flood = any(k in goal_lower for k in ('flood', 'flooded', 'sgtpuzzles'))

  if plan.get('tool') == 'tap' and isinstance(plan.get('args'), dict):
    plan.setdefault('is_done', False)
    return plan

  args_dict = plan.get('args') if isinstance(plan.get('args'), dict) else {}
  x = plan.get('x') if plan.get('x') is not None else args_dict.get('x')
  y = plan.get('y') if plan.get('y') is not None else args_dict.get('y')
  if x is not None and y is not None:
    try:
      plan['tool'] = 'tap'
      plan['args'] = {'x': float(x), 'y': float(y)}
      plan.setdefault('is_done', False)
      return plan
    except (ValueError, TypeError):
      pass

  row = plan.get('row') if plan.get('row') is not None else args_dict.get('row')
  col = plan.get('col') if plan.get('col') is not None else args_dict.get('col')
  if row is not None and col is not None:
    try:
      r, c = int(row), int(col)
      grid_x = 0.24 + (c % 3) * 0.255
      grid_y = 0.43 + (r % 3) * 0.115
      plan['tool'] = 'tap'
      plan['args'] = {'x': round(grid_x, 3), 'y': round(grid_y, 3)}
      plan.setdefault('is_done', False)
      return plan
    except (ValueError, TypeError):
      pass

  if is_flood:
    thought_text = str(plan.get('thought', ''))
    tap_match = re.search(
        r'tap\s*\(\s*([0-9.]+)\s*,\s*([0-9.]+)\s*\)',
        thought_text,
        re.IGNORECASE,
    )
    if tap_match:
      plan['tool'] = 'tap'
      plan['args'] = {
          'x': float(tap_match.group(1)),
          'y': float(tap_match.group(2)),
      }
      plan.setdefault('is_done', False)
      return plan
    plan['tool'] = 'invalid'
    plan['args'] = {}
    plan.setdefault('is_done', False)
    return plan

  return normalize_2048_action(plan)


@dataclasses.dataclass(slots=True)
class ToolCall:
  """Represents a normalized tool call requested by a model.

  Attributes:
    name: The name of the tool to invoke.
    args: Dictionary of arguments passed to the tool.
  """

  name: str
  args: dict[str, Any]


@dataclasses.dataclass(slots=True)
class ModelResponse:
  """Represents a normalized response from any LLM provider.

  Attributes:
    thoughts: Reasoning or chain-of-thought strings emitted by the model.
    text: Assistant text outputs emitted by the model.
    tool_calls: Normalized tool calls requested by the model.
    latency_ms: End-to-end model generation latency in milliseconds.
    provider_name: Identifier of the underlying model provider.
  """

  thoughts: list[str] = dataclasses.field(default_factory=list)
  text: list[str] = dataclasses.field(default_factory=list)
  tool_calls: list[ToolCall] = dataclasses.field(default_factory=list)
  latency_ms: float = 0.0
  provider_name: str = ''


class BaseModelProvider(abc.ABC):
  """Abstract base class for multi-model inference providers."""

  def __init__(self, model_name: str) -> None:
    """Initializes the base model provider.

    Args:
      model_name: Name or identifier of the target model.
    """
    self.model_name = model_name

  @abc.abstractmethod
  def generate(
      self,
      system_prompt: str,
      user_prompt: str,
      screenshot_bytes: bytes | None,
      tools_schema: Sequence[dict[str, Any]],
      history: Sequence[dict[str, Any]] | None = None,
      thinking_level: str = 'LOW',
  ) -> ModelResponse:
    """Generates the next response or tool call given multimodal context.

    Args:
      system_prompt: System instructions for the agent.
      user_prompt: Current step prompt including UI hierarchy and state.
      screenshot_bytes: Raw PNG bytes of the current screen, if available.
      tools_schema: List of JSON Schema tool declarations.
      history: Optional list of prior conversation turns.
      thinking_level: Reasoning budget hint (e.g., 'LOW', 'MEDIUM', 'HIGH').

    Returns:
      A normalized ModelResponse containing thoughts, text, and tool calls.
    """

  def generate_plan(
      self,
      goal: str,
      ui_tree: str,
      device_info: str,
      screenshot_b64: str | None = None,
  ) -> dict[str, Any]:
    """Generates a single-step action plan dictionary from goal and UI context.

    Args:
      goal: Natural language goal or task instruction.
      ui_tree: String representation of the accessibility hierarchy.
      device_info: String representation of device metadata.
      screenshot_b64: Optional base64-encoded PNG screenshot.

    Returns:
      Plan dictionary with keys `thought`, `tool`, `args`, `is_done`, and
      `llm_latency_ms`.
    """
    screenshot_bytes: bytes | None = None
    if screenshot_b64:
      try:
        screenshot_bytes = base64.b64decode(screenshot_b64)
      except (ValueError, TypeError):
        screenshot_bytes = None

    user_prompt = (
        f'GOAL: {goal}\nDEVICE INFO:\n{device_info}\n\nUI TREE:\n{ui_tree}'
    )
    resp = self.generate(
        system_prompt='You are an autonomous Android agent.',
        user_prompt=user_prompt,
        screenshot_bytes=screenshot_bytes,
        tools_schema=[],
    )
    thought = resp.thoughts[0] if resp.thoughts else ''
    if resp.tool_calls:
      tc = resp.tool_calls[0]
      return {
          'thought': thought,
          'tool': tc.name,
          'args': dict(tc.args),
          'is_done': tc.name in ('done', 'finish'),
          'llm_latency_ms': round(resp.latency_ms, 2),
          'model': self.model_name,
      }
    return normalize_action(
        {
            'thought': thought or (resp.text[0] if resp.text else ''),
            'llm_latency_ms': round(resp.latency_ms, 2),
            'model': self.model_name,
        },
        goal=goal,
    )

  def close(self) -> None:
    """Releases any underlying resources held by the provider."""


BaseLLMProvider = BaseModelProvider
