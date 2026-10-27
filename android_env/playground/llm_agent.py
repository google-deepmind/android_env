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

"""Autonomous Multimodal LLM Agent for AndroidEnv Playground.

Connects to Gemini (`google-genai`), external frontier models via Ditto
(`gpt-4o`, `claude-3-5-sonnet`, `deepseek-r1`), on-device Gemini Nano via AICore
Bridge, or local/on-device LiteRT-LM (`gemma-4-e2b`, `gemma-4-e4b`,
`gemma-3n-e2b`) and drives the Android device using the MCP tool bridge
(`PlaygroundMcpBridge`), streaming its chain-of-thought, tool invocations, and
observations in real time.
"""

from collections.abc import Callable
import hashlib
import json
import threading
import time
from typing import Any

from absl import logging
from android_env.playground import mcp_bridge
from android_env.playground import providers
from android_env.playground import state

DEFAULT_MODEL = 'gemini-3-flash-preview'

_SYSTEM_PROMPT = """You are an autonomous Android Agent controlling a live Android device inside AndroidEnv Playground via Model Context Protocol (MCP) tools.

You receive on every turn:
1. The current screen image (RGB screenshot).
2. The accessibility UI tree (if available) and device metadata (screen resolution, orientation, step reward, cumulative reward).
3. The user's goal / instruction.

Coordinate System:
- All `tap(x, y)` and `swipe(start_x, start_y, end_x, end_y)` coordinates are NORMALIZED floats in `[0.0, 1.0]` where `(0.0, 0.0)` is top-left and `(1.0, 1.0)` is bottom-right.
- If an accessibility node shows pixel bounds `{left,top,right,bottom}` and the screen dimensions are `W x H`, its normalized center is `x = ((left + right) / 2) / W`, `y = ((top + bottom) / 2) / H`.

Game & Task Guidelines:
- For **2048**:
  - Use `swipe` to slide tiles across the board:
    - UP: `swipe(start_x=0.5, start_y=0.7, end_x=0.5, end_y=0.3)`
    - DOWN: `swipe(start_x=0.5, start_y=0.3, end_x=0.5, end_y=0.7)`
    - LEFT: `swipe(start_x=0.75, start_y=0.5, end_x=0.25, end_y=0.5)`
    - RIGHT: `swipe(start_x=0.25, start_y=0.5, end_x=0.75, end_y=0.5)`
  - Strategy: Keep your highest-value tile anchored in a corner (e.g., bottom-left or top-left) and alternate between two primary directions unless neither direction moves any tiles!
  - CRITICAL: Look closely at whether the board changed after your previous swipe. If a swipe direction did not move any tiles, immediately pick a different direction!
- For **Flood It** (Simon Tatham's Portable Puzzle Collection):
  - Goal: Flood-fill the entire grid with a single color in as few steps as possible, starting from the **top-left corner** `(0, 0)` connected component.
  - How to play: Tap directly on a square of the target color on the board (or in the adjacent region) to flood the top-left connected region with that color.
  - Board coordinates: The puzzle grid occupies roughly `x in [0.05, 0.95]` and `y in [0.18, 0.85]`. Tap the center of a square belonging to the color that maximizes the number of newly absorbed adjacent tiles.
- Always explain your reasoning briefly (1-2 sentences) before calling a tool.
- Call exactly ONE action tool (`tap`, `swipe`, `press_key`, `wait`, or `done`) per step so you can observe the updated screen after each action.
"""


class LlmAgent:
  """Background autonomous agent loop using MCP tools and multi-model providers."""

  def __init__(
      self,
      playground_state: state.PlaygroundState,
      bridge: mcp_bridge.PlaygroundMcpBridge | None = None,
      event_callback: Callable[[dict[str, Any]], None] | None = None,
      api_key: str | None = None,
      provider_factory: Callable[..., providers.BaseModelProvider] = (
          providers.create_provider
      ),
      model_name: str = DEFAULT_MODEL,
  ) -> None:
    """Initializes the autonomous LLM agent.

    Args:
      playground_state: Shared PlaygroundState instance.
      bridge: Optional PlaygroundMcpBridge instance exposing MCP tools.
      event_callback: Optional callback invoked on each agent event.
      api_key: Optional API key passed to GeminiProvider.
      provider_factory: Factory callable returning a BaseModelProvider.
      model_name: Default model identifier.
    """
    self._state: Any = playground_state
    self._bridge = bridge or mcp_bridge.PlaygroundMcpBridge(playground_state)
    self._event_cb = event_callback
    self._api_key = api_key
    self._provider_factory = provider_factory

    self._lock = threading.Lock()
    self._running = False
    self._stop_event = threading.Event()
    self._thread: threading.Thread | None = None
    self._goal = ''
    self._model = model_name or DEFAULT_MODEL
    self._max_steps = 30
    self._current_step = 0

  def is_running(self) -> bool:
    """Returns True if the background agent loop is currently active."""
    with self._lock:
      return self._running

  def _emit(self, event_type: str, **payload: Any) -> None:
    """Emits a structured agent event to the callback and Playground logs."""
    msg = {
        'type': 'agent_event',
        'event': event_type,
        'step': self._current_step,
        'max_steps': self._max_steps,
        'timestamp': time.time(),
        **payload,
    }
    if 'text' in payload and payload['text']:
      self._state.add_log(f'[Agent:{event_type}] {payload["text"]}')
    if self._event_cb is not None:
      try:
        self._event_cb(msg)
      except Exception as e:  # pylint: disable=broad-exception-caught
        logging.warning('Failed to emit agent event: %s', e)

  def start(
      self,
      goal: str,
      model: str = DEFAULT_MODEL,
      max_steps: int = 30,
  ) -> bool:
    """Starts the autonomous agent loop in a background thread.

    Args:
      goal: Natural-language task goal for the agent.
      model: Model identifier to route through `provider_factory`.
      max_steps: Maximum number of steps before stopping.

    Returns:
      True if started, False if already running.
    """
    with self._lock:
      if self._running:
        return False
      self._running = True
      self._stop_event.clear()
      self._goal = goal.strip() or 'Play and win the current task on screen.'
      self._model = model.strip() or DEFAULT_MODEL
      self._max_steps = max(1, min(int(max_steps), 200))
      self._current_step = 0

    self._thread = threading.Thread(target=self._run_loop, daemon=True)
    self._thread.start()
    return True

  def stop(self) -> None:
    """Requests the running agent loop to stop."""
    self._stop_event.set()

  def run_step(
      self, goal: str, model_override: str | None = None
  ) -> dict[str, Any]:
    """Executes a single reasoning and action step toward `goal`."""
    active_model = model_override or self._model
    kwargs: dict[str, Any] = {}
    if self._api_key:
      kwargs['api_key'] = self._api_key
    provider = self._provider_factory(active_model, **kwargs)
    try:
      ui_tree = self._bridge.get_ui_elements('tree')
      device_info = self._bridge.get_device_info()
      try:
        screenshot_b64 = self._bridge.get_screenshot()
      except RuntimeError:
        screenshot_b64 = None
      step_plan = provider.generate_plan(
          goal, ui_tree, device_info, screenshot_b64=screenshot_b64
      )
    finally:
      provider.close()

    tool_name = step_plan.get('tool', 'get_ui_elements')
    args = step_plan.get('args', {})
    thought = step_plan.get('thought', '')
    is_done = bool(step_plan.get('is_done', False)) or tool_name in (
        'done',
        'finish',
    )
    if tool_name in ('done', 'finish'):
      return {
          'thought': thought,
          'tool': tool_name,
          'args': args,
          'result': (
              args.get('summary') or args.get('message', 'Goal completed.')
          ),
          'is_done': True,
          'success': True,
          'llm_latency_ms': step_plan.get('llm_latency_ms', 0.0),
          'model': step_plan.get('model', active_model),
          'raw_response': step_plan.get('raw_response', ''),
          'screenshot_b64': screenshot_b64,
      }
    tool_res = self._bridge.call_tool(tool_name, args)
    return {
        'thought': thought,
        'tool': tool_name,
        'args': args,
        'result': tool_res.get('result') or tool_res.get('error', ''),
        'is_done': is_done,
        'success': bool(tool_res.get('success', False)),
        'llm_latency_ms': step_plan.get('llm_latency_ms', 0.0),
        'model': step_plan.get('model', active_model),
        'raw_response': step_plan.get('raw_response', ''),
        'screenshot_b64': screenshot_b64,
    }

  def start_loop_async(
      self,
      goal: str,
      max_steps: int = 10,
      until_done: bool = False,
      step_callback: Callable[[dict[str, Any]], None] | None = None,
      finish_callback: Callable[[dict[str, Any]], None] | None = None,
  ) -> None:
    """Starts the autonomous agent loop with step/finish WebSocket callbacks."""
    effective_steps = (
        max_steps if max_steps > 0 else (200 if until_done else 25)
    )

    def _on_event(ev: dict[str, Any]) -> None:
      ev_type = ev.get('event')
      if ev_type == 'tool_result' and step_callback is not None:
        step_callback(ev)
      elif ev_type in ('completed', 'error', 'stopped'):
        if finish_callback is not None:
          finish_callback({
              'success': ev_type == 'completed',
              'message': ev.get('text', ''),
              'steps': ev.get('step', 0),
          })

    self._event_cb = _on_event
    self.start(goal=goal, model=self._model, max_steps=effective_steps)

  def start_batch_async(
      self,
      tasks: list[str],
      runs_per_task: int = 1,
      reload_each_run: bool = True,
      max_steps: int = 25,
      until_done: bool = False,
      target_score: float = 0.0,
      models: list[str] | None = None,
      progress_callback: Callable[[dict[str, Any]], None] | None = None,
      run_complete_callback: Callable[[dict[str, Any]], None] | None = None,
      finish_callback: Callable[[dict[str, Any]], None] | None = None,
  ) -> None:
    """Starts a batch evaluation over `tasks` and `models`."""
    del runs_per_task, reload_each_run, target_score, run_complete_callback
    first_task = tasks[0] if tasks else 'Play current task'
    if models:
      self._model = models[0]
    self.start_loop_async(
        goal=first_task,
        max_steps=max_steps,
        until_done=until_done,
        step_callback=progress_callback,
        finish_callback=finish_callback,
    )

  def _wait_for_environment_ready(self, timeout_s: float = 90.0) -> bool:
    """Waits if the environment is currently reloading a task."""
    deadline = time.time() + timeout_s
    while time.time() < deadline and not self._stop_event.is_set():
      reload_info = self._state.get_reload_status()
      if reload_info['status'] == 'loading':
        self._emit('status', text='Waiting for task reload to complete...')
        time.sleep(1.0)
        continue
      if reload_info['status'] == 'error':
        self._emit(
            'error',
            text=f'Task reload failed: {reload_info["error"]}',
        )
        return False
      if self._bridge.get_screenshot_bytes() is not None:
        return True
      time.sleep(0.3)
    return self._bridge.get_screenshot_bytes() is not None

  def _wait_for_next_timestep(
      self, prev_seq: int, timeout_s: float = 3.0
  ) -> None:
    """Waits until the environment executes the queued actions and advances."""
    deadline = time.time() + timeout_s
    while time.time() < deadline and not self._stop_event.is_set():
      _, seq = self._state.get_last_timestep_with_seq()
      if seq > prev_seq and self._state.action_queue.empty():
        time.sleep(0.25)
        return
      time.sleep(0.08)

  def _run_loop(self) -> None:
    """Main sense-think-act loop."""
    self._emit(
        'started',
        text=(
            f'Started autonomous agent ({self._model}) with goal: {self._goal}'
        ),
        goal=self._goal,
        model=self._model,
    )

    try:
      kwargs: dict[str, Any] = {}
      if self._api_key:
        kwargs['api_key'] = self._api_key
      provider = self._provider_factory(self._model, **kwargs)
    except Exception as e:  # pylint: disable=broad-exception-caught
      self._emit('error', text=f'Failed to initialize provider: {e}')
      with self._lock:
        self._running = False
      return

    tools_schema = self._bridge.list_tools()
    history_summary: list[str] = []
    prev_frame_hash: str | None = None
    unchanged_count = 0

    try:
      if not self._wait_for_environment_ready():
        self._emit('error', text='Environment or screenshot not ready.')
        return

      for step in range(1, self._max_steps + 1):
        if self._stop_event.is_set():
          self._emit('stopped', text='Agent stopped by user.')
          break

        reload_info = self._state.get_reload_status()
        if reload_info['status'] == 'loading':
          if not self._wait_for_environment_ready():
            break

        self._current_step = step
        screenshot_bytes = self._bridge.get_screenshot_bytes()
        if screenshot_bytes is None:
          self._emit('status', text='Waiting for screen frame...')
          time.sleep(0.5)
          continue

        frame_hash = hashlib.md5(screenshot_bytes).hexdigest()[:10]
        if prev_frame_hash is not None and frame_hash == prev_frame_hash:
          unchanged_count += 1
        else:
          unchanged_count = 0
        prev_frame_hash = frame_hash

        ui_tree = self._bridge.get_ui_elements('tree')
        if len(ui_tree) > 3500:
          ui_tree = ui_tree[:3500] + '\n... (truncated)'
        dev_info = self._bridge.get_device_info()

        recent_history = (
            '\n'.join(history_summary[-6:]) if history_summary else 'None yet.'
        )
        unchanged_warning = ''
        if unchanged_count >= 1:
          unchanged_warning = (
              '\n⚠️ WARNING: The screen did NOT change after your last '
              f'{unchanged_count} action(s) (frame_hash={frame_hash}). '
              'Your previous swipe direction or tap location had NO effect! '
              'You MUST choose a DIFFERENT swipe direction or tap coordinate '
              'on this turn!'
          )

        user_prompt = (
            f'GOAL: {self._goal}\n'
            f'STEP: {step} / {self._max_steps}\n'
            f'DEVICE INFO:\n{dev_info}\n\n'
            f'UI ELEMENTS:\n{ui_tree}\n\n'
            f'RECENT ACTION HISTORY:\n{recent_history}'
            f'{unchanged_warning}\n\n'
            'Inspect the attached screenshot carefully and invoke your next '
            'MCP tool call.'
        )

        self._emit('thinking', text=f'Step {step}: Querying {self._model}...')
        try:
          model_resp = provider.generate(
              system_prompt=_SYSTEM_PROMPT,
              user_prompt=user_prompt,
              screenshot_bytes=screenshot_bytes,
              tools_schema=tools_schema,
              thinking_level='LOW',
          )
        except Exception as e:  # pylint: disable=broad-exception-caught
          self._emit('error', text=f'Model API error on step {step}: {e}')
          break

        for thought in model_resp.thoughts:
          self._emit(
              'thought',
              text=thought,
              latency_ms=round(model_resp.latency_ms, 1),
          )
        for txt in model_resp.text:
          self._emit(
              'message',
              text=txt,
              latency_ms=round(model_resp.latency_ms, 1),
          )

        if not model_resp.tool_calls:
          history_summary.append(
              f'Step {step}: Model returned text without a tool call '
              '(prompting for tool call next turn).'
          )
          continue

        tc = model_resp.tool_calls[0]
        self._emit(
            'tool_call',
            tool=tc.name,
            args=tc.args,
            latency_ms=round(model_resp.latency_ms, 1),
            text=(
                f'{tc.name}({json.dumps(tc.args)}) '
                f'[{model_resp.latency_ms:.0f}ms]'
            ),
        )

        _, prev_seq = self._state.get_last_timestep_with_seq()
        result = self._bridge.execute_tool(tc.name, tc.args)
        self._emit(
            'tool_result',
            tool=tc.name,
            status=result['status'],
            text=result['output'],
        )

        if result['status'] == 'done':
          self._emit('completed', text=f'Goal completed: {result["output"]}')
          break

        if tc.name in ('tap', 'swipe', 'press_key'):
          self._wait_for_next_timestep(prev_seq, timeout_s=3.0)

        new_info = json.loads(self._bridge.get_device_info())
        history_summary.append(
            f'Step {step}: {tc.name}({json.dumps(tc.args)}) -> '
            f'{result["output"]} | reward={new_info.get("reward", 0.0)}, '
            f'cumulative_reward={new_info.get("cumulative_reward", 0.0)}'
        )
      else:
        self._emit(
            'completed',
            text=f'Reached max steps ({self._max_steps}).',
        )
    except Exception as e:  # pylint: disable=broad-exception-caught
      logging.exception('Unhandled error in LlmAgent loop')
      self._emit('error', text=f'Unhandled agent error: {e}')
    finally:
      provider.close()
      with self._lock:
        self._running = False
