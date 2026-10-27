# AndroidEnv FastMCP Server & Dual-Agent Runner

This package provides a [FastMCP](https://github.com/jlowin/fastmcp) server and
dual-agent evaluation runner for direct `AndroidDevice` interaction, battery
telemetry observation, and preloaded task lifecycle management.

## Overview

`android_env.mcp` connects directly to an `AndroidDevice` instance over
WebSockets and ADB, exposing device perception, touch/key actions, hardware
power telemetry, and task management tools over the Model Context Protocol
(MCP).

### Role-Scoped Tool Registration

For multi-agent benchmarking on physical or emulated Android devices,
`android_mcp_server` supports a `--role` flag (`all`, `worker`, or `manager`) to
isolate active UI interaction from ground-truth task evaluation:

| Role | Registered Tools | Purpose |
| :--- | :--- | :--- |
| `worker` | `get_screenshot`, `get_ui_elements`, `get_device_info`, `tap`, `swipe`, `press_key` | Active UI perception and gesture/key execution without access to ground-truth task rewards. |
| `manager` | `get_screenshot`, `get_ui_elements`, `get_device_info`, `get_battery_metrics`, `load_task`, `reset_task`, `get_task_info`, `get_task_metrics` | Passive task lifecycle orchestration, reward/score tracking, and battery power telemetry without emitting touch gestures. |
| `all` | All 11 tools (`worker` + `manager`) | Single-agent interactive inspection, task execution, and telemetry collection. |

## Files

*   `android_mcp_server.py`: Stdio FastMCP server binary entrypoint supporting
    `--serial`, `--host`, `--websocket_port`, `--role`, and `--task_path`.
*   `android_mcp_tools.py`: `AndroidMcpTools` implementation providing screen
    capture, accessibility tree formatting, touch/key actions, battery power
    telemetry (`get_battery_metrics`), and task lifecycle tools (`load_task`,
    `reset_task`, `get_task_info`, `get_task_metrics`).
*   `android_mcp_runner.py`: `AndroidMcpRunner` dual-agent evaluation harness
    coordinating Worker and Task Manager roles across benchmark trials.
*   `errors.py`: Exception hierarchy (`AndroidEnvMcpError`, `AdbError`,
    `DeviceConnectionError`).

## Usage

### Launching the FastMCP Server

```bash
python -m android_env.mcp.android_mcp_server \
  --serial=emulator-5554 \
  --role=worker
```

### Running a Dual-Agent Evaluation Trial

```bash
python -m android_env.mcp.android_mcp_runner \
  --task_path=/path/to/task.textproto \
  --worker_port=8000 \
  --manager_port=8001 \
  --max_steps=100
```
