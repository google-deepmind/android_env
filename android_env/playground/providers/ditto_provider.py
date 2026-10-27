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

"""Ditto provider for external frontier models (OpenAI GPT-4o, Claude, etc.).

Uses Google DeepMind's internal Ditto proxy service via either an injected stub
or dynamically loaded Ditto client/gRPC transport. Since Ditto standardizes
external models onto a unified multimodal message format, tool calls are
prompted as structured JSON blocks and parsed into normalized `ToolCall` objects
so all external models work uniformly regardless of native function-calling
quirks.
"""

import base64
from collections.abc import Sequence
import dataclasses
import importlib
import json
import re
import time
from typing import Any

from android_env.playground.providers import base

_DITTO_BNS_ADDRESS = ''

_JSON_TOOL_SYSTEM_ADDENDUM = """

IMPORTANT OUTPUT FORMAT:
You must output your reasoning inside <thought>...</thought> tags, followed by a single JSON object inside ```json ... ``` specifying the tool to call:
```json
{
  "tool": "<tool_name>",
  "args": { ... }
}
```
Available tools and their parameters:
"""


@dataclasses.dataclass(slots=True)
class Blob:
  """Binary payload for multimodal inline image data."""

  mime_type: str = 'image/png'
  data: bytes = b''


@dataclasses.dataclass(slots=True)
class Part:
  """Single message part holding text or inline binary data."""

  text: str = ''
  inline_data: Blob | None = None


@dataclasses.dataclass(slots=True)
class Content:
  """Role-tagged multimodal message content."""

  role: str = 'user'
  parts: list[Part] = dataclasses.field(default_factory=list)


@dataclasses.dataclass(slots=True)
class Candidate:
  """Single generation candidate returned by Ditto."""

  content: Content = dataclasses.field(default_factory=Content)


@dataclasses.dataclass(slots=True)
class GenerationConfig:
  """Generation hyperparameters for Ditto requests."""

  temperature: float = 0.2
  max_output_tokens: int = 1024


@dataclasses.dataclass(slots=True)
class GenerateContentRequest:
  """Structured request passed to Ditto frontend stubs."""

  model: str = ''
  contents: list[Content] = dataclasses.field(default_factory=list)
  generation_config: GenerationConfig = dataclasses.field(
      default_factory=GenerationConfig
  )


@dataclasses.dataclass(slots=True)
class GenerateContentResponse:
  """Structured response returned by Ditto frontend stubs."""

  candidates: list[Candidate] = dataclasses.field(default_factory=list)


def _extract_tool_json(raw_text: str) -> dict[str, Any] | None:
  """Extracts a JSON object containing a 'tool' key from raw model text.

  Args:
    raw_text: Model output string to parse.

  Returns:
    Parsed dictionary containing 'tool' if found, otherwise None.
  """
  code_match = re.search(
      r'```(?:json)?\s*(\{.*?\})\s*```', raw_text, flags=re.DOTALL
  )
  if code_match:
    try:
      parsed = json.loads(code_match.group(1))
      if isinstance(parsed, dict) and 'tool' in parsed:
        return parsed
    except json.JSONDecodeError:
      pass

  decoder = json.JSONDecoder()
  for idx, ch in enumerate(raw_text):
    if ch == '{':
      try:
        parsed, _ = decoder.raw_decode(raw_text[idx:])
        if isinstance(parsed, dict) and 'tool' in parsed:
          return parsed
      except json.JSONDecodeError:
        continue
  return None


class _DittoClientStubAdapter:
  """Adapts `ditto.DittoClient` HTTP-style `.post()` to `GenerateContent`."""

  def __init__(self, ditto_client: Any, provider_family: str) -> None:
    self._client = ditto_client
    self._provider_family = provider_family

  def GenerateContent(  # pylint: disable=invalid-name
      self, request: GenerateContentRequest, timeout: float = 120.0
  ) -> GenerateContentResponse:
    """Translates a `GenerateContentRequest` into a Ditto REST post call."""
    user_content: list[dict[str, Any]] = []
    for content in request.contents:
      for part in content.parts:
        if part.inline_data and part.inline_data.data:
          b64 = base64.b64encode(part.inline_data.data).decode('ascii')
          mime = part.inline_data.mime_type or 'image/png'
          if self._provider_family == 'anthropic':
            user_content.append({
                'type': 'image',
                'source': {
                    'type': 'base64',
                    'media_type': mime,
                    'data': b64,
                },
            })
          else:
            user_content.append({
                'type': 'image_url',
                'image_url': {
                    'url': f'data:{mime};base64,{b64}',
                    'detail': 'high',
                },
            })
        if part.text:
          user_content.append({'type': 'text', 'text': part.text})

    if self._provider_family == 'anthropic':
      url = 'https://api.anthropic.com/v1/messages'
      payload = {
          'model': request.model,
          'messages': [{'role': 'user', 'content': user_content}],
          'max_tokens': request.generation_config.max_output_tokens,
          'temperature': request.generation_config.temperature,
      }
      raw_res = self._client.post(
          url=url,
          body=json.dumps(payload),
          headers=[('anthropic-version', '2023-06-01')],
          deadline_secs=int(timeout),
      )
    else:
      url = 'https://api.openai.com/v1/chat/completions'
      payload = {
          'model': request.model,
          'messages': [{'role': 'user', 'content': user_content}],
          'temperature': request.generation_config.temperature,
      }
      raw_res = self._client.post(
          url=url,
          body=json.dumps(payload),
          deadline_secs=int(timeout),
      )

    res_dict = json.loads(raw_res) if isinstance(raw_res, str) else raw_res
    text_out = ''
    if isinstance(res_dict, dict):
      choices = res_dict.get('choices', [])
      if choices and isinstance(choices[0], dict):
        text_out = str(choices[0].get('message', {}).get('content', ''))
      elif 'content' in res_dict and isinstance(res_dict['content'], list):
        for item in res_dict['content']:
          if isinstance(item, dict) and item.get('type') == 'text':
            text_out += str(item.get('text', ''))

    return GenerateContentResponse(
        candidates=[
            Candidate(
                content=Content(role='model', parts=[Part(text=text_out)])
            )
        ]
    )


class DittoProvider(base.BaseModelProvider):
  """Provider for OpenAI, Anthropic, and DeepSeek models via Ditto."""

  def __init__(
      self,
      model_name: str,
      server_address: str = _DITTO_BNS_ADDRESS,
      rpc_timeout_s: float = 120.0,
      stub: Any | None = None,
  ) -> None:
    """Initializes the Ditto provider.

    Args:
      model_name: Target model name (e.g., 'gpt-4o-2024-08-06' or
        'ditto:openai:gpt-4o').
      server_address: BNS address of the Ditto GenAI frontend server.
      rpc_timeout_s: RPC timeout in seconds.
      stub: Optional pre-constructed stub for testing.
    """
    super().__init__(model_name)
    self._server_address = server_address
    self._rpc_timeout_s = rpc_timeout_s
    self._channel: Any | None = None
    self._stub: Any | None = stub

  def _get_stub(self) -> Any:
    """Lazily initializes and returns the Ditto client stub."""
    if self._stub is not None:
      return self._stub

    raise RuntimeError(
        'Ditto provider is only available in Google-internal environments.'
    )
    norm = self.model_name.lower()
    provider_family = 'anthropic' if 'claude' in norm else 'openai'
    cfg = f'gemini_evals_{provider_family}_tier3'
    client = ditto_mod.DittoClient(cfg, use_cache=False)
    self._stub = _DittoClientStubAdapter(client, provider_family)
    return self._stub

  def generate(
      self,
      system_prompt: str,
      user_prompt: str,
      screenshot_bytes: bytes | None,
      tools_schema: Sequence[dict[str, Any]],
      history: Sequence[dict[str, Any]] | None = None,
      thinking_level: str = 'LOW',
  ) -> base.ModelResponse:
    """Generates a response from Ditto.

    Args:
      system_prompt: System instructions for the agent.
      user_prompt: Current step prompt.
      screenshot_bytes: Optional raw PNG screenshot bytes.
      tools_schema: Sequence of tool declaration dictionaries.
      history: Optional conversation history.
      thinking_level: Reasoning budget level.

    Returns:
      Normalized ModelResponse instance.
    """
    del history, thinking_level
    t0 = time.monotonic()

    tools_desc = json.dumps(list(tools_schema), indent=2)
    full_system = system_prompt + _JSON_TOOL_SYSTEM_ADDENDUM + tools_desc

    parts: list[Part] = [Part(text=full_system + '\n\n' + user_prompt)]
    if screenshot_bytes:
      parts.append(
          Part(
              inline_data=Blob(
                  mime_type='image/png',
                  data=screenshot_bytes,
              )
          )
      )

    request = GenerateContentRequest(
        model=self.model_name,
        contents=[Content(role='user', parts=parts)],
        generation_config=GenerationConfig(
            temperature=0.2,
            max_output_tokens=1024,
        ),
    )

    response = self._get_stub().GenerateContent(
        request, timeout=self._rpc_timeout_s
    )
    latency_ms = (time.monotonic() - t0) * 1000.0

    result = base.ModelResponse(
        latency_ms=latency_ms,
        provider_name=f'ditto:{self.model_name}',
    )

    raw_text = ''
    if response.candidates and response.candidates[0].content:
      for part in response.candidates[0].content.parts:
        if part.text:
          raw_text += part.text

    thought_matches = re.findall(
        r'<thought>(.*?)</thought>', raw_text, flags=re.DOTALL
    )
    for tm in thought_matches:
      if tm.strip():
        result.thoughts.append(tm.strip())

    cleaned_text = re.sub(
        r'<thought>.*?</thought>', '', raw_text, flags=re.DOTALL
    ).strip()

    parsed = _extract_tool_json(cleaned_text)
    if parsed and 'tool' in parsed:
      result.tool_calls.append(
          base.ToolCall(
              name=str(parsed['tool']),
              args=dict(parsed.get('args') or {}),
          )
      )
    elif cleaned_text:
      result.text.append(cleaned_text)

    return result

  def close(self) -> None:
    """Closes the underlying gRPC channel if open."""
    if self._channel is not None:
      try:
        self._channel.close()
      except (RuntimeError, ValueError, OSError):
        pass
      self._channel = None
