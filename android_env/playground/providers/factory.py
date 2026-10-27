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

"""Factory for routing model names to the appropriate provider backend."""

from typing import Any

from android_env.playground.providers import base
from android_env.playground.providers import ditto_provider
from android_env.playground.providers import gemini_provider
from android_env.playground.providers import litert_provider
from android_env.playground.providers import nano_provider

_DITTO_PREFIXES = (
    'ditto:',
    'gpt-',
    'o1-',
    'o3-',
    'claude-',
    'deepseek-',
    'qwen-',
)

_LITERT_PREFIXES = (
    'litert-',
    'gemma-4',
    'gemma4',
    'gemma-3n',
    'gemma3n',
)


def create_provider(model_name: str, **kwargs: Any) -> base.BaseModelProvider:
  """Creates the appropriate model provider based on the model name string.

  Args:
    model_name: Identifier of the target model (e.g.,
      `'gemini-3-flash-preview'`, `'gpt-4o-2024-08-06'`,
      `'claude-3-5-sonnet-v2@20241022'`, `'nano'`, `'gemma-4-e2b'`,
      `'gemma-4-e4b'`, `'gemma-3n-e2b'`).
    **kwargs: Provider-specific configuration options.

  Returns:
    An initialized `BaseModelProvider` instance.
  """
  normalized = model_name.strip().lower()

  if normalized.startswith(_LITERT_PREFIXES):
    return litert_provider.LiteRTProvider(model_name=model_name, **kwargs)

  if normalized.startswith(('nano', 'gemini-nano', 'aicore', 'on-device')):
    return nano_provider.NanoProvider(model_name=model_name, **kwargs)

  if normalized.startswith(_DITTO_PREFIXES):
    return ditto_provider.DittoProvider(model_name=model_name, **kwargs)

  return gemini_provider.GeminiProvider(model_name=model_name, **kwargs)
