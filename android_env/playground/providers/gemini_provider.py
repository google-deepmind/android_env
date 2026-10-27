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

"""Gemini provider using the google-genai SDK (Gemini 3.x / 2.5)."""

from collections.abc import Sequence
import os
import time
from typing import Any

from android_env.playground.providers import base
from google import genai
from google.genai import types


class GeminiProvider(base.BaseModelProvider):
  """Provider for Gemini 3.1 Pro, 3 Flash, 3.1 Flash-Lite, and 2.5 models."""

  def __init__(self, model_name: str, api_key: str | None = None) -> None:
    """Initializes the Gemini provider.

    Args:
      model_name: Gemini model identifier.
      api_key: Optional Gemini API key. Falls back to environment variables if
        omitted.
    """
    super().__init__(model_name)
    resolved_key = (
        api_key
        or os.environ.get('GEMINI_API_KEY')
        or os.environ.get('GOOGLE_API_KEY')
    )
    self._client = (
        genai.Client(api_key=resolved_key) if resolved_key else genai.Client()
    )

  def generate(
      self,
      system_prompt: str,
      user_prompt: str,
      screenshot_bytes: bytes | None,
      tools_schema: Sequence[dict[str, Any]],
      history: Sequence[dict[str, Any]] | None = None,
      thinking_level: str = 'LOW',
  ) -> base.ModelResponse:
    """Generates a response from the Gemini API.

    Args:
      system_prompt: System instructions for the agent.
      user_prompt: Current step prompt.
      screenshot_bytes: Optional raw PNG screenshot bytes.
      tools_schema: Sequence of tool declaration dictionaries.
      history: Optional conversation history.
      thinking_level: Reasoning budget level ('LOW', 'MEDIUM', 'HIGH').

    Returns:
      Normalized ModelResponse instance.
    """
    del history  # Stateless single-turn dispatch.
    t0 = time.monotonic()

    parts: list[Any] = []
    if screenshot_bytes:
      parts.append(
          types.Part.from_bytes(data=screenshot_bytes, mime_type='image/png')
      )
    parts.append(types.Part.from_text(text=user_prompt))

    contents = [types.Content(role='user', parts=parts)]

    fn_decls = [
        types.FunctionDeclaration(
            name=t['name'],
            description=t.get('description', ''),
            parameters=t.get('parameters'),
        )
        for t in tools_schema
    ]
    tools = [types.Tool(function_declarations=fn_decls)] if fn_decls else None

    config_kwargs: dict[str, Any] = {
        'system_instruction': system_prompt,
        'temperature': 0.2,
    }
    if tools:
      config_kwargs['tools'] = tools

    if 'gemini-3' in self.model_name or 'gemini-2.5' in self.model_name:
      try:
        config_kwargs['thinking_config'] = types.ThinkingConfig(
            include_thoughts=True,
            thinking_level=thinking_level,
        )
      except (TypeError, ValueError, AttributeError):
        config_kwargs['thinking_config'] = types.ThinkingConfig(
            include_thoughts=True
        )

    config = types.GenerateContentConfig(**config_kwargs)
    response = self._client.models.generate_content(
        model=self.model_name,
        contents=contents,
        config=config,
    )
    latency_ms = (time.monotonic() - t0) * 1000.0

    result = base.ModelResponse(
        latency_ms=latency_ms,
        provider_name=f'gemini:{self.model_name}',
    )

    if response.candidates and response.candidates[0].content:
      for part in response.candidates[0].content.parts or []:
        if getattr(part, 'thought', False) and part.text:
          result.thoughts.append(part.text.strip())
        elif part.text:
          result.text.append(part.text.strip())
        fc = part.function_call
        if fc and fc.name is not None:
          args = dict(fc.args) if fc.args else {}
          result.tool_calls.append(base.ToolCall(name=fc.name, args=args))

    return result
