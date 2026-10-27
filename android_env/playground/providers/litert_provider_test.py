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

"""Unit tests for multi-model providers (LiteRT, Gemini, Ditto, Nano, Factory)."""

import subprocess
from unittest import mock

from absl.testing import absltest
from absl.testing import parameterized
from android_env.playground import providers
from android_env.playground.providers import base
from android_env.playground.providers import ditto_provider
from android_env.playground.providers import factory
from android_env.playground.providers import gemini_provider
from android_env.playground.providers import litert_provider
from android_env.playground.providers import nano_provider


class ProvidersTest(parameterized.TestCase):

  def test_package_reexports(self):
    self.assertIs(providers.BaseModelProvider, base.BaseModelProvider)
    self.assertIs(providers.BaseLLMProvider, base.BaseModelProvider)
    self.assertIs(providers.ModelResponse, base.ModelResponse)
    self.assertIs(providers.ToolCall, base.ToolCall)
    self.assertIs(providers.create_provider, factory.create_provider)
    self.assertIs(providers.GeminiProvider, gemini_provider.GeminiProvider)
    self.assertIs(providers.DittoProvider, ditto_provider.DittoProvider)
    self.assertIs(providers.NanoProvider, nano_provider.NanoProvider)
    self.assertIs(providers.LiteRTProvider, litert_provider.LiteRTProvider)
    self.assertIs(providers.LiteRtLmProvider, litert_provider.LiteRTProvider)

  def test_normalize_action_2048_and_floodit(self):
    swipe_plan = base.normalize_action({'direction': 'RIGHT'}, goal='2048')
    self.assertEqual(swipe_plan['tool'], 'swipe')
    self.assertIn('start_x', swipe_plan['args'])

    tap_plan = base.normalize_action(
        {'x': 0.5, 'y': 0.43}, goal='sgtpuzzles_flood_3x3_easy'
    )
    self.assertEqual(tap_plan['tool'], 'tap')
    self.assertEqual(tap_plan['args'], {'x': 0.5, 'y': 0.43})

    grid_plan = base.normalize_action(
        {'row': 0, 'col': 1}, goal='sgtpuzzles_flood_3x3_easy'
    )
    self.assertEqual(grid_plan['tool'], 'tap')
    self.assertIn('x', grid_plan['args'])

    invalid_flood = base.normalize_action(
        {'thought': 'No coordinates'}, goal='flood_3x3'
    )
    self.assertEqual(invalid_flood['tool'], 'invalid')

    invalid_2048 = base.normalize_action(
        {'thought': 'No direction'}, goal='2048'
    )
    self.assertEqual(invalid_2048['tool'], 'invalid')

  def test_extract_first_json_object_nested_braces(self):
    text = (
        'Here is my reasoning.\n'
        '{"tool": "tap", "args": {"x": 0.25, "y": 0.75},'
        ' "thought": "Tap the top-left tile"}\n'
        'Trailing text.'
    )
    parsed = litert_provider.extract_first_json_object(text)
    self.assertIsNotNone(parsed)
    self.assertEqual(parsed['tool'], 'tap')
    self.assertEqual(parsed['args'], {'x': 0.25, 'y': 0.75})
    self.assertEqual(parsed['thought'], 'Tap the top-left tile')

  def test_extract_first_json_object_markdown_block(self):
    text = (
        '<thought>Swipe right to merge tiles</thought>\n'
        '```json\n'
        '{"tool": "swipe", "args": {"start_x": 0.2, "start_y": 0.5,'
        ' "end_x": 0.8, "end_y": 0.5}}\n'
        '```'
    )
    parsed = litert_provider.extract_first_json_object(text)
    self.assertIsNotNone(parsed)
    self.assertEqual(parsed['tool'], 'swipe')
    self.assertEqual(parsed['args']['end_x'], 0.8)

  def test_extract_first_json_object_skips_invalid_or_nontool_braces(self):
    text = (
        'Malformed {not_json} and {"other": 1} then '
        '{"tool": "wait", "args": {"seconds": 1.0}}'
    )
    parsed = litert_provider.extract_first_json_object(text)
    self.assertIsNotNone(parsed)
    self.assertEqual(parsed['tool'], 'wait')
    self.assertEqual(parsed['args'], {'seconds': 1.0})

  def test_extract_first_json_object_returns_none_when_missing(self):
    self.assertIsNone(
        litert_provider.extract_first_json_object('```json\n{bad}\n``` no tool')
    )

  @parameterized.named_parameters(
      ('gemma4_e2b', 'gemma-4-e2b', litert_provider.LiteRTProvider),
      ('gemma4_e4b', 'gemma-4-e4b', litert_provider.LiteRTProvider),
      ('gemma3n_e2b', 'gemma-3n-e2b', litert_provider.LiteRTProvider),
      ('litert_prefix', 'litert-gemma-4-e2b', litert_provider.LiteRTProvider),
      ('nano', 'nano', nano_provider.NanoProvider),
      ('on_device', 'on-device-vision', nano_provider.NanoProvider),
      ('ditto_gpt', 'gpt-4o-2024-08-06', ditto_provider.DittoProvider),
      ('ditto_claude', 'claude-3-5-sonnet', ditto_provider.DittoProvider),
  )
  def test_factory_routes_models(self, model_name, expected_cls):
    provider = factory.create_provider(model_name)
    self.assertIsInstance(provider, expected_cls)
    provider.close()

  @mock.patch.object(gemini_provider.genai, 'Client', autospec=True)
  def test_factory_routes_gemini_model(self, mock_client_cls):
    provider = factory.create_provider('gemini-3-flash-preview', api_key='test')
    self.assertIsInstance(provider, gemini_provider.GeminiProvider)
    mock_client_cls.assert_called_once_with(api_key='test')

  @mock.patch.object(subprocess, 'run', autospec=True)
  def test_litert_provider_generate_host_parses_markers(self, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=['litert_lm_main'],
        returncode=0,
        stdout=(
            'I0000 00:00:00.000000 Creating engine\n'
            '===MODEL_OUTPUT_START===\n'
            '{"tool": "tap", "args": {"x": 0.5, "y": 0.5},'
            ' "thought": "Center tap"}\n'
            '===MODEL_OUTPUT_END===\n'
        ),
        stderr='',
    )
    provider = litert_provider.LiteRTProvider(
        model_name='gemma-4-e2b',
        model_path='/tmp/gemma-4-E2B-it.litertlm',
        binary_path='/tmp/litert_lm_main',
        execution_target='host',
        enable_vision=True,
    )
    resp = provider.generate(
        system_prompt='Play 2048',
        user_prompt='Current board state',
        screenshot_bytes=b'fake_png',
        tools_schema=[],
    )
    self.assertEqual(resp.provider_name, 'litert:gemma-4-e2b:host')
    self.assertEqual(resp.thoughts, ['Center tap'])
    self.assertLen(resp.tool_calls, 1)
    self.assertEqual(resp.tool_calls[0].name, 'tap')
    self.assertEqual(resp.tool_calls[0].args, {'x': 0.5, 'y': 0.5})
    mock_run.assert_called_once()

    plan = provider.generate_plan(
        goal='sgtpuzzles_flood_3x3_easy',
        ui_tree='tree',
        device_info='info',
        screenshot_b64='ZmFrZQ==',
    )
    self.assertEqual(plan['tool'], 'tap')
    self.assertEqual(plan['args'], {'x': 0.5, 'y': 0.5})

  @mock.patch.object(subprocess, 'run', autospec=True)
  def test_litert_provider_generate_device_and_fallback_output(self, mock_run):
    mock_run.side_effect = [
        subprocess.CompletedProcess(args=['adb', 'push'], returncode=0),
        subprocess.CompletedProcess(
            args=['adb', 'shell'],
            returncode=0,
            stdout=(
                'I0000 log line\n'
                'Creating engine\n'
                '<thought>Device thought</thought>\n'
                'Plain text answer without tool'
            ),
            stderr='',
        ),
    ]
    provider = litert_provider.LiteRTProvider(
        model_name='gemma-3n-e2b',
        execution_target='device',
        device_serial='emulator-5554',
        enable_vision=True,
    )
    resp = provider.generate(
        system_prompt='System',
        user_prompt="User's prompt",
        screenshot_bytes=b'png_bytes',
        tools_schema=[],
    )
    self.assertEqual(resp.provider_name, 'litert:gemma-3n-e2b:device')
    self.assertEqual(resp.thoughts, ['Device thought'])
    self.assertEqual(resp.text, ['Plain text answer without tool'])
    self.assertEmpty(resp.tool_calls)

  @mock.patch.object(subprocess, 'run', autospec=True)
  def test_litert_provider_handles_subprocess_error(self, mock_run):
    mock_run.side_effect = OSError('binary not found')
    provider = litert_provider.LiteRTProvider(model_name='gemma-4-e2b')
    resp = provider.generate(
        system_prompt='Sys',
        user_prompt='User',
        screenshot_bytes=None,
        tools_schema=[],
    )
    self.assertEmpty(resp.tool_calls)
    self.assertTrue(resp.text[0].startswith('Error:'))

  def test_ditto_provider_generate_and_close(self):
    fake_stub = mock.MagicMock()
    fake_resp = ditto_provider.GenerateContentResponse(
        candidates=[
            ditto_provider.Candidate(
                content=ditto_provider.Content(
                    parts=[
                        ditto_provider.Part(
                            text=(
                                '<thought>Pick red</thought>\n```json\n{"tool":'
                                ' "tap", "args": {"x": 0.1, "y": 0.2}}\n```'
                            )
                        )
                    ]
                )
            )
        ]
    )
    fake_stub.GenerateContent.return_value = fake_resp
    provider = ditto_provider.DittoProvider(
        model_name='gpt-4o-2024-08-06',
        stub=fake_stub,
    )
    provider._channel = mock.MagicMock()
    resp = provider.generate(
        system_prompt='Play game',
        user_prompt='Step 1',
        screenshot_bytes=b'png_data',
        tools_schema=[{'name': 'tap', 'description': 'Tap screen'}],
    )
    self.assertEqual(resp.provider_name, 'ditto:gpt-4o-2024-08-06')
    self.assertEqual(resp.thoughts, ['Pick red'])
    self.assertLen(resp.tool_calls, 1)
    self.assertEqual(resp.tool_calls[0].name, 'tap')
    self.assertEqual(resp.tool_calls[0].args, {'x': 0.1, 'y': 0.2})
    provider.close()
    self.assertIsNone(provider._channel)

  def test_ditto_provider_plain_text_and_inline_json(self):
    fake_stub = mock.MagicMock()
    fake_stub.GenerateContent.return_value = ditto_provider.GenerateContentResponse(
        candidates=[
            ditto_provider.Candidate(
                content=ditto_provider.Content(
                    parts=[
                        ditto_provider.Part(
                            text=(
                                'Inline {"tool": "done", "args": {"summary":'
                                ' "ok"}}'
                            )
                        )
                    ]
                )
            )
        ]
    )
    provider = ditto_provider.DittoProvider(
        model_name='claude-3-5-sonnet', stub=fake_stub
    )
    resp = provider.generate(
        system_prompt='Sys',
        user_prompt='User',
        screenshot_bytes=None,
        tools_schema=[],
    )
    self.assertLen(resp.tool_calls, 1)
    self.assertEqual(resp.tool_calls[0].name, 'done')

  def test_ditto_client_stub_adapter_openai_and_anthropic(self):
    fake_client = mock.MagicMock()
    fake_client.post.return_value = (
        '{"choices": [{"message": {"content": "{\\"tool\\": \\"wait\\"}"}}]}'
    )
    adapter = ditto_provider._DittoClientStubAdapter(fake_client, 'openai')
    req = ditto_provider.GenerateContentRequest(
        model='gpt-4o',
        contents=[
            ditto_provider.Content(
                parts=[
                    ditto_provider.Part(
                        text='hi',
                        inline_data=ditto_provider.Blob(data=b'img'),
                    )
                ]
            )
        ],
    )
    res = adapter.GenerateContent(req, timeout=30.0)
    self.assertIn('wait', res.candidates[0].content.parts[0].text)

    fake_client.post.return_value = (
        '{"content": [{"type": "text", "text": "{\\"tool\\": \\"tap\\"}"}]}'
    )
    anth_adapter = ditto_provider._DittoClientStubAdapter(
        fake_client, 'anthropic'
    )
    res_anth = anth_adapter.GenerateContent(req, timeout=30.0)
    self.assertIn('tap', res_anth.candidates[0].content.parts[0].text)

  @mock.patch.object(gemini_provider.genai, 'Client', autospec=True)
  def test_gemini_provider_generate_extracts_thoughts_and_tool_calls(
      self, mock_client_cls
  ):
    mock_client = mock_client_cls.return_value
    thought_part = mock.MagicMock()
    thought_part.thought = True
    thought_part.text = 'Thinking about board'
    thought_part.function_call = None

    fc_part = mock.MagicMock()
    fc_part.thought = False
    fc_part.text = 'Calling tap'
    fc_part.function_call.name = 'tap'
    fc_part.function_call.args = {'x': 0.3, 'y': 0.7}

    candidate = mock.MagicMock()
    candidate.content.parts = [thought_part, fc_part]
    mock_client.models.generate_content.return_value = mock.MagicMock(
        candidates=[candidate]
    )

    provider = gemini_provider.GeminiProvider(
        model_name='gemini-3-flash-preview', api_key='fake_key'
    )
    resp = provider.generate(
        system_prompt='System',
        user_prompt='User',
        screenshot_bytes=b'png',
        tools_schema=[{
            'name': 'tap',
            'description': 'Tap',
            'parameters': {'type': 'OBJECT'},
        }],
    )
    self.assertEqual(resp.provider_name, 'gemini:gemini-3-flash-preview')
    self.assertEqual(resp.thoughts, ['Thinking about board'])
    self.assertEqual(resp.text, ['Calling tap'])
    self.assertLen(resp.tool_calls, 1)
    self.assertEqual(resp.tool_calls[0].name, 'tap')
    self.assertEqual(resp.tool_calls[0].args, {'x': 0.3, 'y': 0.7})

  def test_nano_provider_apk_grpc_mode(self):
    mock_channel = mock.MagicMock()
    mock_rpc = mock.MagicMock(
        return_value=nano_provider.OnDeviceVisionResponse(
            action_json='{"tool": "tap", "args": {"x": 0.4, "y": 0.6}}',
            thought='Tapped target tile',
            backend_name='OnDeviceVisionRunner',
        )
    )
    mock_channel.unary_unary.return_value = mock_rpc

    mock_env = mock.MagicMock()
    mock_env._coordinator._simulator._device._channel = mock_channel

    provider = nano_provider.NanoProvider(model_name='on-device-vision')
    provider.set_env(mock_env)
    resp = provider.generate(
        system_prompt='Sys',
        user_prompt='User',
        screenshot_bytes=b'png',
        tools_schema=[],
    )
    self.assertEqual(resp.provider_name, 'on-device:OnDeviceVisionRunner')
    self.assertEqual(resp.thoughts, ['Tapped target tile'])
    self.assertLen(resp.tool_calls, 1)
    self.assertEqual(resp.tool_calls[0].name, 'tap')
    self.assertEqual(resp.tool_calls[0].args, {'x': 0.4, 'y': 0.6})

    req_proto = nano_provider.OnDeviceVisionRequest(prompt='test')
    raw_bytes = req_proto.serialize_to_string()
    self.assertIn(b'test', raw_bytes)
    parsed_resp = nano_provider.OnDeviceVisionResponse.from_string(
        b'{"action_json": "{}", "thought": "ok", "backend_name": "b"}'
    )
    self.assertEqual(parsed_resp.thought, 'ok')

  @mock.patch.object(subprocess, 'run', autospec=True)
  @mock.patch.object(nano_provider, 'invoke_aicore_bridge', autospec=True)
  def test_nano_provider_aicore_bridge_mode(self, mock_invoke, mock_run):
    mock_run.return_value = subprocess.CompletedProcess(
        args=['adb', 'push'], returncode=0
    )
    mock_invoke.return_value = (
        '<thought>Use swipe</thought>\n'
        '```json\n'
        '{"tool": "swipe", "args": {"start_x": 0.1, "start_y": 0.5,'
        ' "end_x": 0.9, "end_y": 0.5}}\n'
        '```'
    )
    provider = nano_provider.NanoProvider(
        model_name='nano', device_serial='pixel9'
    )
    resp = provider.generate(
        system_prompt='Sys',
        user_prompt='User',
        screenshot_bytes=b'png',
        tools_schema=[],
    )
    self.assertEqual(resp.provider_name, 'nano:nano')
    self.assertEqual(resp.thoughts, ['Use swipe'])
    self.assertLen(resp.tool_calls, 1)
    self.assertEqual(resp.tool_calls[0].name, 'swipe')

  def test_base_normalize_action_and_generate_plan_edge_cases(self):
    self.assertEqual(
        base.normalize_2048_action({'tool': 'UP'})['tool'], 'swipe'
    )
    self.assertEqual(
        base.normalize_2048_action({'args': {'direction': 'LEFT'}})['tool'],
        'swipe',
    )
    self.assertEqual(
        base.normalize_2048_action({'thought': 'I should move RIGHT'})['tool'],
        'swipe',
    )
    self.assertEqual(
        base.normalize_2048_action({'tool': 'swipe', 'args': {'start_x': 0.1}})[
            'tool'
        ],
        'swipe',
    )
    self.assertEqual(
        base.normalize_2048_action({'thought': 'nothing'})['tool'], 'invalid'
    )
    self.assertEqual(
        base.normalize_action({'tool': 'invalid'})['tool'], 'invalid'
    )
    self.assertEqual(
        base.normalize_action({'tool': 'tap', 'args': {'x': 0.2, 'y': 0.8}})[
            'tool'
        ],
        'tap',
    )
    self.assertEqual(base.normalize_action({'x': 0.3, 'y': 0.7})['tool'], 'tap')
    self.assertEqual(base.normalize_action({'row': 1, 'col': 2})['tool'], 'tap')
    self.assertEqual(
        base.normalize_action(
            {'thought': 'Let us tap(0.4, 0.6)'}, goal='Flood It'
        )['tool'],
        'tap',
    )
    self.assertEqual(
        base.normalize_action({'thought': 'hmm'}, goal='Flood It')['tool'],
        'invalid',
    )

  @mock.patch.object(nano_provider.urllib.request, 'urlopen', autospec=True)
  def test_nano_provider_proxy_and_plan(self, mock_urlopen):
    mock_resp = mock.MagicMock()
    mock_resp.__enter__.return_value.read.return_value = (
        b'{"choices": [{"message": {"content": "{\\"tool\\": \\"wait\\"}"}}]}'
    )
    mock_urlopen.return_value = mock_resp
    txt = nano_provider.invoke_aicore_bridge('prompt', screenshot_bytes=b'png')
    self.assertIn('wait', txt)

    provider = nano_provider.NanoProvider(
        model_name='nano',
        prompt_runner=lambda p: (
            '<thought>Swipe up</thought>'
            '{"tool": "swipe", "args": {"start_x": 0.5, "start_y": 0.7,'
            ' "end_x": 0.5, "end_y": 0.3}}'
        ),
    )
    plan = provider.generate_plan('play 2048', 'tree', 'info')
    self.assertEqual(plan['tool'], 'swipe')

    provider_text_only = nano_provider.NanoProvider(
        model_name='nano',
        prompt_runner=lambda p: 'I will move UP now',
    )
    plan2 = provider_text_only.generate_plan('play 2048', 'tree', 'info')
    self.assertEqual(plan2['tool'], 'swipe')


if __name__ == '__main__':
  absltest.main()
