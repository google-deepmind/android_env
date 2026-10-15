# Migrating from Legacy AndroidEnv (v1) to AndroidDevice (v2)

## 1. Overview & Paradigm Shift

Legacy AndroidEnv (v1) was built around classical Reinforcement Learning (RL)
abstractions:

-   A rigid Markov Decision Process (MDP) loop (`step()` and `reset()`) using
    `dm_env.Environment`.
-   A heavy multi-threaded host orchestrator (`Coordinator`, `TaskManager`,
    `DeviceSettings`, `EmulatorSimulator`).
-   Mandatory task textprotos (`Task`) specifying rewards, terminations, and
    episode step limits.

For modern agent research, foundation model evaluations, and automated UI
testing, **these RL abstractions are unnecessary overhead**. Real-world agent
workflows do not compute MDP reward scalars—they need direct, low-latency
control over the device to:

1.  Capture screenshots.
2.  Read accessibility trees and UI hierarchies.
3.  Send touch gestures, keyboard input, and text.
4.  Execute ADB commands.

AndroidEnv v2 replaces the legacy coordinator stack with **`AndroidDevice`**: a
lightweight, first-class handle that communicates directly with the
high-performance on-device Core server (`com.google.androidenv.core`) over
WebSockets.

```
Legacy v1 Stack:
Agent -> dm_env -> Coordinator -> TaskManager -> EmulatorSimulator -> gRPC / ADB -> Device

v2 Architecture:
Agent -> AndroidDevice -> WebSocket (Protobuf) -> On-Device Core Server
```

> **Note for RL Users:** If you still require a standard `dm_env.Environment`
> interface with MDP rewards and episode resets, use
> `android_env.rl.environment.AndroidEnv`, which wraps `AndroidDevice` cleanly
> without the legacy `Coordinator` stack.

--------------------------------------------------------------------------------

## 2. API Contract Comparison

Capability | Legacy v1 (`dm_env`)        | AndroidEnv v2 (`AndroidDevice`)
---------- | --------------------------- | ----------------------------------
**Load**   | `loader.load(config)`       | `load_android_device(config)`
**Screen** | `env.step(action)`          | `device.get_state()`
**A11y**   | `A11yGrpcWrapper`           | `DEVICE_SIGNAL_ACCESSIBILITY_TREE`
**Action** | `dict` of `np.ndarray`      | `device.send_action(Action(...))`
**ADB**    | `env.execute_adb_call(req)` | `device.execute_adb_call(req)`
**Reset**  | `env.reset()`               | Explicit ADB / setup commands

--------------------------------------------------------------------------------

## 3. Migration Recipes

### 3.1. Initialization & Device Loading

Instead of building a nested `AndroidEnvConfig` with dummy `TaskConfig` and
`CoordinatorConfig`, configure `AndroidDeviceConfig` directly:

#### Connecting to an Existing Device or Emulator

```python
from android_env.components import android_device_loader
from android_env.components import config_classes

# Connect via ADB serial (e.g., local emulator, physical device, or remote device):
config = config_classes.AndroidDeviceConfig(
    serial='emulator-5554',
    adb_path='/path/to/adb',  # Optional; defaults to system adb
)
device = android_device_loader.load_android_device(config)
```

#### Launching a Managed Emulator Instance

```python
config = config_classes.AndroidDeviceConfig(
    emulator_launcher=config_classes.EmulatorLauncherConfig(
        avd_name='Pixel_8_API_34',
        android_sdk_root='~/Android/Sdk',
    )
)
device = android_device_loader.load_android_device(config)
```

`load_android_device` automatically handles:

-   Starting the emulator and waiting for `sys.boot_completed`.
-   Installing the `android_env_server` APK if not present.
-   Setting up ADB port forwarding (`adb forward tcp:PORT tcp:8000`).
-   Connecting the WebSocket transport to the on-device server.

--------------------------------------------------------------------------------

### 3.2. Capturing Screenshots

In v1, getting a new frame required stepping the environment with a dummy
`REPEAT` action. In v2, read `get_state()` on demand:

```python
import numpy as np
from android_env.proto import device_env_service_pb2

state = device.get_state()
for signal in state.signals:
  if signal.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT:
    # AndroidDevice automatically decodes JPEG/PNG bytes into raw RGB pixels:
    decoded = signal.screenshot.decoded
    frame = np.frombuffer(decoded.raw_pixels, dtype=np.uint8).reshape(
        (decoded.height, decoded.width, 3)
    )
    break
```

--------------------------------------------------------------------------------

### 3.3. Accessibility Tree & View Hierarchy

In v1, clients wrapped the environment in `a11y_grpc_wrapper.A11yGrpcWrapper`
and polled `accumulate_new_extras()`. In v2, the accessibility tree is a native
telemetry signal streamed directly from the on-device AccessibilityService.

#### Step 1: Update Signal Subscriptions

By default, the server streams screenshots. Update subscriptions once after
connecting:

```python
device.update_subscriptions({
    device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
    device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
})
```

#### Step 2: Read the Accessibility Forest

```python
state = device.get_state()
for signal in state.signals:
  if signal.type == device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE:
    forest = signal.accessibility_forest  # android_accessibility_forest_pb2.AndroidAccessibilityForest
    for window in forest.windows:
      print(f'Window ID: {window.id}, title: {window.title}')
```

--------------------------------------------------------------------------------

### 3.4. Sending Actions

Actions are explicitly typed protobuf messages sent via `device.send_action()`.

#### Touch Down, Move, Up

Coordinates are normalized floats between `0.0` (top-left) and `1.0`
(bottom-right):

```python
from android_env.proto import device_env_service_pb2

# Touch down at (x=0.5, y=0.8):
device.send_action(
    device_env_service_pb2.Action(
        action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN,
        touch_position=device_env_service_pb2.Point(x=0.5, y=0.8),
        pointer_id=0,
    )
)

# Lift finger:
device.send_action(
    device_env_service_pb2.Action(
        action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_UP,
        pointer_id=0,
    )
)
```

#### Hardware Key Events

```python
# Press BACK button (Android KeyEvent keycode 4):
device.send_action(
    device_env_service_pb2.Action(
        action_type=device_env_service_pb2.ACTION_TYPE_KEY_EVENT,
        keycode=4,
    )
)

# Press HOME button (Android KeyEvent keycode 3):
device.send_action(
    device_env_service_pb2.Action(
        action_type=device_env_service_pb2.ACTION_TYPE_KEY_EVENT,
        keycode=3,
    )
)
```

#### Native Accessibility Text Insertion

```python
# Set text in currently focused input field via AccessibilityNodeInfo:
device.send_action(
    device_env_service_pb2.Action(
        action_type=device_env_service_pb2.ACTION_TYPE_SET_TEXT,
        text='search query',
    )
)
```

--------------------------------------------------------------------------------

### 3.5. Executing ADB Calls

`AndroidDevice.execute_adb_call()` provides **1:1 drop-in parity** with
`AndroidEnvInterface.execute_adb_call()`:

```python
from android_env.proto import adb_pb2

request = adb_pb2.AdbRequest(
    generic=adb_pb2.AdbRequest.GenericRequest(
        args=['shell', 'pm', 'clear', 'com.example.app']
    )
)
response = device.execute_adb_call(request)
output = response.generic.output.decode('utf-8')
```

Any existing utility function accepting `env: env_interface.AndroidEnvInterface`
for ADB calls can be updated to accept `device: android_device.AndroidDevice`
without altering internal logic.

--------------------------------------------------------------------------------

### 3.6. Clean Resource Teardown

`AndroidDevice` supports the context manager protocol to clean up WebSocket
connections, background processes, and emulator instances:

```python
with android_device_loader.load_android_device(config) as device:
  # Perform interactions...
  state = device.get_state()
# Automatically calls device.close() and terminates emulator if launched
```
