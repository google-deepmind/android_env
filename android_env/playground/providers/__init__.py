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

"""Multi-model LLM provider abstractions and implementations for AndroidEnv."""

from android_env.playground.providers import base
from android_env.playground.providers import ditto_provider
from android_env.playground.providers import factory
from android_env.playground.providers import gemini_provider
from android_env.playground.providers import litert_provider
from android_env.playground.providers import nano_provider

BaseModelProvider = base.BaseModelProvider
BaseLLMProvider = base.BaseLLMProvider
ModelResponse = base.ModelResponse
ToolCall = base.ToolCall
normalize_action = base.normalize_action
normalize_2048_action = base.normalize_2048_action
create_provider = factory.create_provider
GeminiProvider = gemini_provider.GeminiProvider
DittoProvider = ditto_provider.DittoProvider
NanoProvider = nano_provider.NanoProvider
LiteRTProvider = litert_provider.LiteRTProvider
LiteRtLmProvider = litert_provider.LiteRTProvider

__all__ = [
    'BaseModelProvider',
    'BaseLLMProvider',
    'ModelResponse',
    'ToolCall',
    'normalize_action',
    'normalize_2048_action',
    'create_provider',
    'GeminiProvider',
    'DittoProvider',
    'NanoProvider',
    'LiteRTProvider',
    'LiteRtLmProvider',
]
