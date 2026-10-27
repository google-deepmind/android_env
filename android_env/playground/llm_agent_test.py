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

"""Unit tests for LlmAgent."""

import time
from typing import Any, cast

from absl.testing import absltest
from android_env.playground import llm_agent
from android_env.playground import mcp_bridge
from android_env.playground import providers
from android_env.playground import state
import dm_env
import numpy as np


class FakeProvider(providers.BaseModelProvider):
  """Deterministic fake provider for testing LlmAgent."""

  def __init__(
      self,
      model_name: str,
      responses: list[providers.ModelResponse],
      raise_on_generate: bool = False,
  ) -> None:
    super().__init__(model_name)
    self._responses = list(responses)
    self._raise_on_generate = raise_on_generate
    self.calls = 0

  def generate(
      self,
      system_prompt: str,
      user_prompt: str,
      screenshot_bytes: bytes | None,
      tools_schema: Any,
      history: Any = None,
      thinking_level: str = 'LOW',
  ) -> providers.ModelResponse:
    del system_prompt, user_prompt, screenshot_bytes, tools_schema, history
    del thinking_level
    if self._raise_on_generate:
      raise RuntimeError('Synthetic provider error')
    idx = min(self.calls, len(self._responses) - 1)
    self.calls += 1
    return self._responses[idx]


class LlmAgentTest(absltest.TestCase):

  def setUp(self):
    super().setUp()
    self.state = cast(Any, state.PlaygroundState())
    with self.state.frame_lock:
      self.state.current_frame = b'fake_png_frame_1'
    ts = dm_env.TimeStep(
        step_type=dm_env.StepType.FIRST,
        reward=0.0,
        discount=1.0,
        observation={'pixels': np.zeros((100, 100, 3), dtype=np.uint8)},
    )
    self.state.set_last_timestep(ts)
    self.bridge = mcp_bridge.PlaygroundMcpBridge(self.state)
    self.events: list[dict[str, Any]] = []

  def test_agent_executes_tool_calls_and_completes_on_done(self):
    fake_responses = [
        providers.ModelResponse(
            thoughts=['No tool call yet'],
            text=['Inspecting board'],
            tool_calls=[],
            latency_ms=10.0,
            provider_name='fake:test',
        ),
        providers.ModelResponse(
            thoughts=['Let us swipe right first.'],
            tool_calls=[
                providers.ToolCall(
                    name='swipe',
                    args={
                        'start_x': 0.2,
                        'start_y': 0.5,
                        'end_x': 0.8,
                        'end_y': 0.5,
                        'steps': 2,
                    },
                )
            ],
            latency_ms=42.0,
            provider_name='fake:test',
        ),
        providers.ModelResponse(
            thoughts=['Goal achieved.'],
            tool_calls=[
                providers.ToolCall(
                    name='done',
                    args={'summary': 'Finished test episode'},
                )
            ],
            latency_ms=35.0,
            provider_name='fake:test',
        ),
    ]
    fake_provider = FakeProvider('fake-model', fake_responses)

    agent = llm_agent.LlmAgent(
        self.state,
        self.bridge,
        event_callback=self.events.append,
        api_key='test-key',
        provider_factory=lambda model_name, **kw: fake_provider,
    )

    started = agent.start(goal='Play 2048', model='fake-model', max_steps=5)
    self.assertTrue(started)

    deadline = time.time() + 10.0
    while agent.is_running() and time.time() < deadline:
      while not self.state.action_queue.empty():
        self.state.action_queue.get_nowait()
      self.state.set_last_timestep(
          dm_env.TimeStep(
              step_type=dm_env.StepType.MID,
              reward=4.0,
              discount=1.0,
              observation={'pixels': np.zeros((100, 100, 3), dtype=np.uint8)},
          )
      )
      time.sleep(0.05)

    self.assertFalse(agent.is_running())
    self.assertEqual(fake_provider.calls, 3)
    event_types = [e['event'] for e in self.events]
    self.assertIn('started', event_types)
    self.assertIn('thought', event_types)
    self.assertIn('message', event_types)
    self.assertIn('tool_call', event_types)
    self.assertIn('tool_result', event_types)
    self.assertIn('completed', event_types)

  def test_reload_abort_while_loading(self):
    self.state.set_reload_status('error', 'Failed to load APK')
    fake_provider = FakeProvider('fake-model', [])
    agent = llm_agent.LlmAgent(
        self.state,
        self.bridge,
        event_callback=self.events.append,
        provider_factory=lambda model_name, **kw: fake_provider,
    )
    agent.start(goal='Play Flood It', model='fake-model', max_steps=3)
    deadline = time.time() + 5.0
    while agent.is_running() and time.time() < deadline:
      time.sleep(0.05)
    event_types = [e['event'] for e in self.events]
    self.assertIn('error', event_types)

  def test_provider_init_failure_and_generate_error(self):
    def _failing_factory(model_name: str, **kwargs: Any):
      del model_name, kwargs
      raise ValueError('Bad provider')

    agent = llm_agent.LlmAgent(
        self.state,
        self.bridge,
        event_callback=self.events.append,
        provider_factory=_failing_factory,
    )
    agent.start(goal='Goal', model='bad', max_steps=2)
    deadline = time.time() + 5.0
    while agent.is_running() and time.time() < deadline:
      time.sleep(0.02)
    self.assertIn('error', [e['event'] for e in self.events])

    self.events.clear()
    err_provider = FakeProvider('err', [], raise_on_generate=True)
    agent2 = llm_agent.LlmAgent(
        self.state,
        self.bridge,
        event_callback=self.events.append,
        provider_factory=lambda m, **kw: err_provider,
    )
    agent2.start(goal='Goal', model='err', max_steps=2)
    deadline = time.time() + 5.0
    while agent2.is_running() and time.time() < deadline:
      time.sleep(0.02)
    self.assertIn('error', [e['event'] for e in self.events])

  def test_max_steps_unchanged_frame_and_stop(self):
    wait_responses = [
        providers.ModelResponse(
            thoughts=['Wait a bit'],
            tool_calls=[
                providers.ToolCall(name='wait', args={'seconds': 0.01})
            ],
            latency_ms=5.0,
            provider_name='fake:test',
        )
    ]
    fake_provider = FakeProvider('fake-model', wait_responses)
    agent = llm_agent.LlmAgent(
        self.state,
        self.bridge,
        event_callback=self.events.append,
        provider_factory=lambda m, **kw: fake_provider,
    )
    self.assertTrue(agent.start(goal='Loop', model='fake-model', max_steps=2))
    self.assertFalse(agent.start(goal='Duplicate', model='fake-model'))
    deadline = time.time() + 5.0
    while agent.is_running() and time.time() < deadline:
      time.sleep(0.02)
    self.assertTrue(
        any(
            e['event'] == 'completed' and 'Reached max steps' in e['text']
            for e in self.events
        )
    )
    agent.stop()

  def test_run_step_and_async_callbacks(self):
    fake_responses = [
        providers.ModelResponse(
            thoughts=['Tap center'],
            tool_calls=[
                providers.ToolCall(name='tap', args={'x': 0.5, 'y': 0.5})
            ],
            latency_ms=12.0,
            provider_name='fake:test',
        ),
        providers.ModelResponse(
            thoughts=['All done'],
            tool_calls=[
                providers.ToolCall(name='done', args={'summary': 'Won'})
            ],
            latency_ms=8.0,
            provider_name='fake:test',
        ),
    ]
    fake_provider = FakeProvider('fake-model', fake_responses)
    agent = llm_agent.LlmAgent(
        self.state,
        self.bridge,
        api_key='k',
        provider_factory=lambda m, **kw: fake_provider,
    )
    step1 = agent.run_step('Flood It')
    self.assertTrue(step1['success'])
    self.assertEqual(step1['tool'], 'tap')
    step2 = agent.run_step('Flood It')
    self.assertTrue(step2['is_done'])

    finished: list[dict[str, Any]] = []
    agent.start_batch_async(
        tasks=['Flood It'],
        max_steps=1,
        models=['fake-model'],
        finish_callback=finished.append,
    )
    deadline = time.time() + 5.0
    while agent.is_running() and time.time() < deadline:
      time.sleep(0.02)
    self.assertNotEmpty(finished)


if __name__ == '__main__':
  absltest.main()
