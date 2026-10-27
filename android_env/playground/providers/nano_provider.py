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

"""On-Device Android provider (AICore Gemini Nano & Direct APK Vision Runner).

Supports two on-device execution modes on physical Android devices or emulators:
1. `on-device-vision`: Invokes the built-in `OnDeviceVisionRunner` inside the
   AndroidEnv Core APK directly over the existing `DeviceEnvService` gRPC
   channel
   (`RunOnDeviceVision` RPC). Zero external APK dependencies, zero host-side
   cloud calls, and runs directly on the Android device's `Bitmap` buffer.
2. `nano-*`: Bridges to `com.google.android.apps.aicore.proxy` (AICoreProxy APK)
   via local HTTP endpoint (`http://127.0.0.1:8080/v1/chat/completions`) or an
   injected bridge client for devices provisioned with Google AICore / Gemini
   Nano weights.
"""

import base64
from collections.abc import Callable, Sequence
import dataclasses
import json
import os
import re
import subprocess
import tempfile
import time
from typing import Any
import urllib.request

from absl import logging
from android_env.playground.providers import base

_DEVICE_IMAGE_PATH = '/data/local/tmp/nano_screen.png'

_NANO_TOOL_PROMPT = """You are an Android agent. Output a brief <thought>...</thought> and a single JSON block:
{"tool": "<tap|swipe|press_key|wait|done>", "args": {...}}
"""


@dataclasses.dataclass(slots=True)
class OnDeviceVisionRequest:
  """Request payload for the `RunOnDeviceVision` APK gRPC method."""

  prompt: str = ''
  task_hint: str = 'auto'
  include_screenshot: bool = True

  def serialize_to_string(self) -> bytes:
    """Serializes request fields to UTF-8 JSON bytes."""
    return json.dumps({
        'prompt': self.prompt,
        'task_hint': self.task_hint,
        'include_screenshot': self.include_screenshot,
    }).encode('utf-8')


@dataclasses.dataclass(slots=True)
class OnDeviceVisionResponse:
  """Response payload from the `RunOnDeviceVision` APK gRPC method."""

  action_json: str = ''
  thought: str = ''
  backend_name: str = ''

  @classmethod
  def from_string(cls, raw: bytes) -> 'OnDeviceVisionResponse':
    """Deserializes UTF-8 JSON bytes into an OnDeviceVisionResponse."""
    data = json.loads(raw.decode('utf-8')) if raw else {}
    return cls(
        action_json=str(data.get('action_json', '')),
        thought=str(data.get('thought', '')),
        backend_name=str(data.get('backend_name', '')),
    )


def _parse_json_tool_call(raw_output: str) -> dict[str, Any] | None:
  """Parses a JSON tool dictionary from raw model text."""
  json_match = re.search(
      r'```(?:json)?\s*(\{.*?\})\s*```', raw_output, flags=re.DOTALL
  )
  if json_match:
    try:
      parsed = json.loads(json_match.group(1))
      if isinstance(parsed, dict) and 'tool' in parsed:
        return parsed
    except json.JSONDecodeError:
      pass

  decoder = json.JSONDecoder()
  for idx, ch in enumerate(raw_output):
    if ch == '{':
      try:
        parsed, _ = decoder.raw_decode(raw_output[idx:])
        if isinstance(parsed, dict) and 'tool' in parsed:
          return parsed
      except json.JSONDecodeError:
        continue
  return None


def invoke_aicore_bridge(
    prompt: str,
    endpoint_url: str = 'http://127.0.0.1:8080/v1/chat/completions',
    api_token: str = 'test-local-key',
    screenshot_bytes: bytes | None = None,
) -> str:
  """Sends a prompt to the on-device AICore proxy endpoint."""
  payload: dict[str, Any] = {
      'messages': [{'role': 'user', 'content': prompt}],
      'stream': False,
      'temperature': 0.2,
  }
  if screenshot_bytes:
    payload['image'] = base64.b64encode(screenshot_bytes).decode('ascii')

  req = urllib.request.Request(
      endpoint_url,
      data=json.dumps(payload).encode('utf-8'),
      headers={
          'Authorization': f'Bearer {api_token}',
          'Content-Type': 'application/json',
      },
      method='POST',
  )
  with urllib.request.urlopen(req, timeout=30) as resp:
    res_json = json.loads(resp.read().decode('utf-8'))
    choices = res_json.get('choices', [])
    if choices and 'message' in choices[0]:
      return str(choices[0]['message'].get('content', ''))
  return ''


class NanoProvider(base.BaseModelProvider):
  """Provider for On-Device inference via Core APK gRPC or AICore Bridge."""

  def __init__(
      self,
      model_name: str = 'nano',
      device_serial: str | None = None,
      adb_path: str = 'adb',
      feature_id: int = -1,
      env: Any = None,
      endpoint_url: str = 'http://127.0.0.1:8080/v1/chat/completions',
      api_token: str = 'test-local-key',
      bridge: Any | None = None,
      prompt_runner: Callable[[str], str] | None = None,
  ) -> None:
    """Initializes the NanoProvider.

    Args:
      model_name: Target on-device model identifier ('on-device-vision' or
        'nano').
      device_serial: Optional Android device serial for ADB commands.
      adb_path: Path to the ADB binary.
      feature_id: AICore feature ID when using AICoreProxy mode.
      env: Optional AndroidEnv instance for direct gRPC vision execution.
      endpoint_url: Local AICore HTTP proxy endpoint URL.
      api_token: API token for the local AICore proxy.
      bridge: Optional PlaygroundMcpBridge instance.
      prompt_runner: Optional custom callable `(prompt) -> str` for testing.
    """
    super().__init__(model_name)
    self._device_serial = device_serial or os.environ.get('ANDROID_SERIAL')
    self._adb_path = adb_path
    self._feature_id = feature_id
    self._env = env
    self._endpoint_url = os.environ.get('GEMINI_NANO_ENDPOINT', endpoint_url)
    self._api_token = os.environ.get('GEMINI_NANO_API_KEY', api_token)
    self._bridge = bridge
    self._prompt_runner = prompt_runner

  def set_env(self, env: Any) -> None:
    """Binds the active AndroidEnv instance for direct gRPC execution."""
    self._env = env

  def _adb_cmd(self, *args: str) -> list[str]:
    """Builds an ADB command list with optional device serial."""
    cmd = [self._adb_path]
    if self._device_serial:
      cmd.extend(['-s', self._device_serial])
    cmd.extend(args)
    return cmd

  def _push_screenshot_to_device(self, screenshot_bytes: bytes) -> str:
    """Writes screenshot bytes to a temp file and pushes to Android device."""
    with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
      f.write(screenshot_bytes)
      host_path = f.name
    try:
      subprocess.run(
          self._adb_cmd('push', host_path, _DEVICE_IMAGE_PATH),
          check=True,
          capture_output=True,
          timeout=10,
      )
    finally:
      if os.path.exists(host_path):
        os.unlink(host_path)
    return _DEVICE_IMAGE_PATH

  def _find_grpc_channel(self) -> Any | None:
    """Finds the underlying gRPC channel to the AndroidEnv Core APK."""
    if self._env is None:
      return None
    try:
      coordinator = getattr(self._env, '_coordinator', None)
      simulator = getattr(coordinator, '_simulator', None)
      device = getattr(simulator, '_device', None)
      if device is not None and hasattr(device, '_channel'):
        return getattr(device, '_channel', None)
    except AttributeError:
      pass
    return None

  def _generate_via_apk_grpc(
      self,
      user_prompt: str,
      task_hint: str = 'auto',
  ) -> base.ModelResponse | None:
    """Invokes RunOnDeviceVision RPC directly on the Android device APK."""
    grpc_channel = self._find_grpc_channel()
    if grpc_channel is None:
      return None

    t0 = time.monotonic()
    req = OnDeviceVisionRequest(
        prompt=user_prompt,
        task_hint=task_hint,
        include_screenshot=True,
    )
    rpc_call = grpc_channel.unary_unary(
        '/android_env.DeviceEnvService/RunOnDeviceVision',
        request_serializer=OnDeviceVisionRequest.serialize_to_string,
        response_deserializer=OnDeviceVisionResponse.from_string,
    )
    resp = rpc_call(req, timeout=15.0)
    round_trip_ms = (time.monotonic() - t0) * 1000.0

    result = base.ModelResponse(
        latency_ms=round_trip_ms,
        provider_name=f'on-device:{resp.backend_name or self.model_name}',
    )
    if resp.thought:
      result.thoughts.append(resp.thought.strip())

    parsed = _parse_json_tool_call(resp.action_json or '')
    if parsed is not None:
      result.tool_calls.append(
          base.ToolCall(
              name=str(parsed['tool']),
              args=dict(parsed.get('args') or {}),
          )
      )
    elif resp.action_json:
      result.text.append(resp.action_json)
    return result

  def generate(
      self,
      system_prompt: str,
      user_prompt: str,
      screenshot_bytes: bytes | None,
      tools_schema: Sequence[dict[str, Any]],
      history: Sequence[dict[str, Any]] | None = None,
      thinking_level: str = 'LOW',
  ) -> base.ModelResponse:
    """Generates a response via on-device APK gRPC or AICore bridge.

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
    del tools_schema, history, thinking_level

    if self.model_name in ('on-device-vision', 'on-device', 'nano-apk'):
      try:
        apk_resp = self._generate_via_apk_grpc(user_prompt)
        if apk_resp is not None:
          return apk_resp
      except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning('Direct APK on-device vision RPC failed: %s', e)

    t0 = time.monotonic()

    device_img = None
    if screenshot_bytes:
      try:
        device_img = self._push_screenshot_to_device(screenshot_bytes)
      except (subprocess.SubprocessError, OSError) as e:
        logging.warning('Failed to push screenshot for Nano: %s', e)

    compact_prompt = f'{_NANO_TOOL_PROMPT}\n{system_prompt}\n{user_prompt}'
    if device_img:
      compact_prompt = f'[Image: {device_img}]\n' + compact_prompt

    if self._prompt_runner is not None:
      raw_output = self._prompt_runner(compact_prompt)
    else:
      raw_output = invoke_aicore_bridge(
          prompt=compact_prompt,
          endpoint_url=self._endpoint_url,
          api_token=self._api_token,
          screenshot_bytes=screenshot_bytes,
      )
    latency_ms = (time.monotonic() - t0) * 1000.0

    result = base.ModelResponse(
        latency_ms=latency_ms,
        provider_name=f'nano:{self.model_name}',
    )

    if not raw_output:
      return result

    thought_matches = re.findall(
        r'<thought>(.*?)</thought>', raw_output, flags=re.DOTALL
    )
    for tm in thought_matches:
      if tm.strip():
        result.thoughts.append(tm.strip())

    cleaned = re.sub(
        r'<thought>.*?</thought>', '', raw_output, flags=re.DOTALL
    ).strip()

    parsed = _parse_json_tool_call(cleaned)
    if parsed and 'tool' in parsed:
      result.tool_calls.append(
          base.ToolCall(
              name=str(parsed['tool']),
              args=dict(parsed.get('args') or {}),
          )
      )
    elif cleaned:
      result.text.append(cleaned)

    return result
