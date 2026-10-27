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

"""LiteRT-LM provider for Gemma 4 (E2B / E4B) and Gemma 3n (E2B / E4B).

Executes `.litertlm` flatbuffer models (such as
`gemma-4-E2B-it.litertlm`, `gemma-4-E4B-it.litertlm`, and
`gemma-3n-E2B-it-int4.litertlm`) either:
1. Directly on the Linux workstation via the compiled
   `//third_party/odml/litert_lm/runtime/engine:litert_lm_main` C++ binary.
2. On a physical Android device via a persistent `adb shell` process running the
   Android arm64 `litert_lm_main` binary in interactive multi-turn mode or
   single-turn CLI mode.
"""

from collections.abc import Sequence
import json
import os
import re
import subprocess
import tempfile
import time
from typing import Any

from absl import logging
from android_env.playground.providers import base

_DEFAULT_HOST_MODEL_PATHS: dict[str, str] = {
    'gemma-4-e2b': '/tmp/litert_models/gemma-4-E2B-it.litertlm',
    'gemma-4-e4b': '/tmp/litert_models/gemma-4-E4B-it.litertlm',
    'gemma-3n-e2b': '/tmp/litert_models/gemma-3n-E2B-it-int4.litertlm',
    'gemma-3n-e4b': '/tmp/litert_models/gemma-3n-E4B-it-int4.litertlm',
    'litert-gemma-4-e2b': '/tmp/litert_models/gemma-4-E2B-it.litertlm',
    'litert-gemma-4-e4b': '/tmp/litert_models/gemma-4-E4B-it.litertlm',
    'litert-gemma-3n-e2b': '/tmp/litert_models/gemma-3n-E2B-it-int4.litertlm',
}

_DEFAULT_HOST_BINARY_CANDIDATES: tuple[str, ...] = (
    '/tmp/litert_lm_main_host',
    'bin/litert_lm_main',
)

_DEFAULT_DEVICE_DIR = '/data/local/tmp/litert'

_LITERT_JSON_SYSTEM_PROMPT = """You are an autonomous Android agent.
Analyze the current screen state and output ONLY a single JSON object selecting the next tool action:
{"tool": "<tap|swipe|press_key|wait|done>", "args": {...}, "thought": "<brief 1-sentence reason>"}
Do not output markdown blocks outside the JSON.
"""


def extract_first_json_object(text: str) -> dict[str, Any] | None:
  """Extracts the first valid JSON object containing a 'tool' key from text.

  Uses `json.JSONDecoder().raw_decode` scanning to handle nested braces
  (e.g., `{"tool": "tap", "args": {"x": 0.5, "y": 0.5}}`) without regex
  truncation.

  Args:
    text: Raw text output from the model.

  Returns:
    The parsed dictionary if a valid JSON object with a `'tool'` key is found,
    otherwise `None`.
  """
  code_match = re.search(
      r'```(?:json)?\s*(\{.*?\})\s*```', text, flags=re.DOTALL
  )
  if code_match:
    try:
      obj = json.loads(code_match.group(1))
      if isinstance(obj, dict) and 'tool' in obj:
        return obj
    except json.JSONDecodeError:
      pass

  decoder = json.JSONDecoder()
  idx = 0
  n = len(text)
  while idx < n:
    brace_pos = text.find('{', idx)
    if brace_pos == -1:
      break
    try:
      obj, _ = decoder.raw_decode(text, brace_pos)
      if isinstance(obj, dict) and 'tool' in obj:
        return obj
      idx = brace_pos + 1
    except json.JSONDecodeError:
      idx = brace_pos + 1
  return None


class LiteRTProvider(base.BaseModelProvider):
  """Provider for local/on-device Gemma 4 and Gemma 3n `.litertlm` models."""

  def __init__(
      self,
      model_name: str = 'gemma-4-e2b',
      model_path: str | None = None,
      binary_path: str | None = None,
      backend: str = 'cpu',
      execution_target: str = 'host',
      device_serial: str | None = None,
      adb_path: str = 'adb',
      max_output_tokens: int = 192,
      num_cpu_threads: int = 8,
      enable_vision: bool = False,
      timeout_s: float = 180.0,
  ) -> None:
    """Initializes the LiteRT-LM provider.

    Args:
      model_name: Logical model name (`gemma-4-e2b`, `gemma-4-e4b`,
        `gemma-3n-e2b`, `gemma-3n-e4b`).
      model_path: Explicit path to the `.litertlm` file. If omitted, resolves
        from `_DEFAULT_HOST_MODEL_PATHS` or `LITERT_MODEL_PATH`.
      binary_path: Path to the `litert_lm_main` binary.
      backend: LiteRT-LM backend (`cpu` or `gpu`).
      execution_target: Either `'host'` (run on Linux workstation) or `'device'`
        (run on Android device via `adb shell`).
      device_serial: Android device serial when `execution_target == 'device'`.
      adb_path: Path to `adb` executable.
      max_output_tokens: Maximum number of generated tokens per turn.
      num_cpu_threads: Number of CPU threads for XNNPACK/YNNPACK execution.
      enable_vision: Whether to pass screenshot images to the vision encoder.
      timeout_s: Subprocess execution timeout in seconds.
    """
    super().__init__(model_name)
    norm_name = model_name.lower().strip()
    self._model_path = (
        model_path
        or os.environ.get('LITERT_MODEL_PATH')
        or _DEFAULT_HOST_MODEL_PATHS.get(
            norm_name, '/tmp/litert_models/gemma-4-E2B-it.litertlm'
        )
    )
    self._binary_path = binary_path or self._resolve_host_binary()
    self._backend = backend
    self._execution_target = execution_target
    self._device_serial = device_serial or os.environ.get('ANDROID_SERIAL')
    self._adb_path = adb_path
    self._max_output_tokens = max_output_tokens
    self._num_cpu_threads = num_cpu_threads
    self._enable_vision = enable_vision
    self._timeout_s = timeout_s

  def _resolve_host_binary(self) -> str:
    """Finds the compiled `litert_lm_main` binary on the host."""
    env_bin = os.environ.get('LITERT_LM_MAIN_BIN')
    if env_bin and os.path.exists(env_bin):
      return env_bin
    for candidate in _DEFAULT_HOST_BINARY_CANDIDATES:
      if os.path.exists(candidate):
        return candidate
    return _DEFAULT_HOST_BINARY_CANDIDATES[0]

  def _adb_cmd(self, *args: str) -> list[str]:
    """Builds an ADB command list with optional device serial."""
    cmd = [self._adb_path]
    if self._device_serial:
      cmd.extend(['-s', self._device_serial])
    cmd.extend(args)
    return cmd

  def _run_on_host(
      self, prompt: str, screenshot_bytes: bytes | None
  ) -> tuple[str, float]:
    """Runs `litert_lm_main` on the host machine and returns output + latency."""
    image_file = None
    try:
      cmd = [
          self._binary_path,
          f'--model_path={self._model_path}',
          f'--backend={self._backend}',
          f'--input_prompt={prompt}',
          f'--max_output_tokens={self._max_output_tokens}',
          f'--num_cpu_threads={self._num_cpu_threads}',
          '--temperature=0.2',
      ]
      if self._enable_vision and screenshot_bytes:
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
          f.write(screenshot_bytes)
          image_file = f.name
        cmd.extend([
            f'--image_path={image_file}',
            f'--vision_backend={self._backend}',
        ])

      t0 = time.monotonic()
      proc = subprocess.run(
          cmd,
          capture_output=True,
          text=True,
          timeout=self._timeout_s,
          check=False,
      )
      latency_ms = (time.monotonic() - t0) * 1000.0
      combined = (proc.stdout or '') + '\n' + (proc.stderr or '')
      return combined, latency_ms
    finally:
      if image_file and os.path.exists(image_file):
        os.unlink(image_file)

  def _run_on_device(
      self, prompt: str, screenshot_bytes: bytes | None
  ) -> tuple[str, float]:
    """Runs `litert_lm_main` on the physical Android device via `adb shell`."""
    device_model = f'{_DEFAULT_DEVICE_DIR}/{os.path.basename(self._model_path)}'
    device_bin = f'{_DEFAULT_DEVICE_DIR}/litert_lm_main'
    device_img = f'{_DEFAULT_DEVICE_DIR}/screen.png'

    if self._enable_vision and screenshot_bytes:
      with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as f:
        f.write(screenshot_bytes)
        host_img = f.name
      try:
        subprocess.run(
            self._adb_cmd('push', host_img, device_img),
            capture_output=True,
            timeout=10,
            check=False,
        )
      finally:
        if os.path.exists(host_img):
          os.unlink(host_img)

    escaped_prompt = prompt.replace("'", "'\\''")
    remote_cmd = (
        f'LD_LIBRARY_PATH={_DEFAULT_DEVICE_DIR} {device_bin} '
        f'--model_path={device_model} '
        f'--backend={self._backend} '
        f'--max_output_tokens={self._max_output_tokens} '
        f'--num_cpu_threads={self._num_cpu_threads} '
        f"--input_prompt='{escaped_prompt}'"
    )
    if self._enable_vision and screenshot_bytes:
      remote_cmd += (
          f' --image_path={device_img} --vision_backend={self._backend}'
      )

    t0 = time.monotonic()
    proc = subprocess.run(
        self._adb_cmd('shell', remote_cmd),
        capture_output=True,
        text=True,
        timeout=self._timeout_s,
        check=False,
    )
    latency_ms = (time.monotonic() - t0) * 1000.0
    combined = (proc.stdout or '') + '\n' + (proc.stderr or '')
    return combined, latency_ms

  def _extract_model_output(self, raw_stdout: str) -> str:
    """Extracts the generated text between `===MODEL_OUTPUT_START===` markers."""
    marker_match = re.search(
        r'===MODEL_OUTPUT_START===\s*(.*?)\s*===MODEL_OUTPUT_END===',
        raw_stdout,
        flags=re.DOTALL,
    )
    if marker_match:
      return marker_match.group(1).strip()

    lines = []
    for line in raw_stdout.splitlines():
      if line.startswith(('I0', 'W0', 'E0', 'F0', 'WARNING:', 'INFO:')):
        continue
      if 'Creating engine' in line or 'The input_prompt is:' in line:
        continue
      lines.append(line)
    return '\n'.join(lines).strip()

  def generate(
      self,
      system_prompt: str,
      user_prompt: str,
      screenshot_bytes: bytes | None,
      tools_schema: Sequence[dict[str, Any]],
      history: Sequence[dict[str, Any]] | None = None,
      thinking_level: str = 'LOW',
  ) -> base.ModelResponse:
    """Generates a response from the LiteRT-LM engine.

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

    compact_prompt = (
        f'{_LITERT_JSON_SYSTEM_PROMPT}\n{system_prompt}\n{user_prompt}'
    )

    try:
      if self._execution_target == 'device':
        raw_stdout, latency_ms = self._run_on_device(
            compact_prompt, screenshot_bytes
        )
      else:
        raw_stdout, latency_ms = self._run_on_host(
            compact_prompt, screenshot_bytes
        )
    except (subprocess.SubprocessError, OSError) as e:
      logging.error('LiteRTProvider execution failed: %s', e)
      return base.ModelResponse(
          latency_ms=0.0,
          provider_name=f'litert:{self.model_name}',
          text=[f'Error: {e}'],
      )

    model_text = self._extract_model_output(raw_stdout)
    result = base.ModelResponse(
        latency_ms=latency_ms,
        provider_name=f'litert:{self.model_name}:{self._execution_target}',
    )

    if not model_text:
      return result

    thought_matches = re.findall(
        r'<thought>(.*?)</thought>', model_text, flags=re.DOTALL
    )
    for tm in thought_matches:
      if tm.strip():
        result.thoughts.append(tm.strip())

    cleaned = re.sub(
        r'<thought>.*?</thought>', '', model_text, flags=re.DOTALL
    ).strip()

    parsed = extract_first_json_object(cleaned)
    if parsed is not None:
      if parsed.get('thought') and not result.thoughts:
        result.thoughts.append(str(parsed['thought']))
      result.tool_calls.append(
          base.ToolCall(
              name=str(parsed['tool']),
              args=dict(parsed.get('args') or {}),
          )
      )
    elif cleaned:
      result.text.append(cleaned)

    return result


LiteRtLmProvider = LiteRTProvider
