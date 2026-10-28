# AndroidEnv - Running AndroidDevice, Playground, and RL Agents

This guide covers how to set up an Android device, interact with it directly
using `AndroidDevice`, launch the interactive web **Playground**, and run
Reinforcement Learning (RL) tasks.

> Upgrading from AndroidEnv v1? See the
> [AndroidDevice (v2) Migration Guide](migrating_to_android_device.md).

--------------------------------------------------------------------------------

## 1. Set Up an Android Device

AndroidEnv works identically with **Android Studio Virtual Devices (AVDs)** and
**physical Android hardware**.

*   **Android Studio Emulator**: Follow the step-by-step
    [Emulator setup guide](emulator_guide.md) to install the Android SDK and
    create an AVD.
*   **Physical Device**: Enable **Developer Options** and **USB Debugging** on
    your Android device, connect it via USB, and verify that `adb devices` lists
    its serial number.

--------------------------------------------------------------------------------

## 2. Direct Control with `AndroidDevice`

For UI agents, foundation model evaluations, and automation workflows that do
not need MDP rewards or episode resets, use
`android_device_loader.load_android_device()`.

### Connect to an Existing Device or Running Emulator

If your emulator or physical device is already running and visible in `adb
devices`:

```python
from android_env.components import android_device_loader
from android_env.components import config_classes

config = config_classes.AndroidDeviceConfig(
    serial='emulator-5554',
    adb_path='~/Android/Sdk/platform-tools/adb',
)
device = android_device_loader.load_android_device(config)
```

### Launch a Managed Emulator Instance

To have AndroidEnv automatically start and manage an AVD process:

```python
from android_env.components import android_device_loader
from android_env.components import config_classes

config = config_classes.AndroidDeviceConfig(
    emulator_launcher=config_classes.EmulatorLauncherConfig(
        avd_name='my_avd',
        android_avd_home='~/.android/avd',
        android_sdk_root='~/Android/Sdk',
        emulator_path='~/Android/Sdk/emulator/emulator',
    ),
    adb_path='~/Android/Sdk/platform-tools/adb',
)
device = android_device_loader.load_android_device(config)
```

### Observe Telemetry & Send Actions

```python
import numpy as np
from android_env.proto import adb_pb2
from android_env.proto import device_env_service_pb2

with android_device_loader.load_android_device(config) as device:
  # 1. Subscribe to screenshots and accessibility trees:
  device.update_subscriptions({
      device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
      device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
  })

  # 2. Fetch the current state snapshot:
  state = device.get_state()
  for signal in state.signals:
    if signal.type == device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT:
      decoded = signal.screenshot.decoded
      pixels = np.frombuffer(decoded.raw_pixels, dtype=np.uint8).reshape(
          (decoded.height, decoded.width, 3)
      )
    elif signal.type == device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE:
      forest = signal.accessibility_forest

  # 3. Inject a touch tap at the center of the screen:
  device.send_action(
      device_env_service_pb2.Action(
          action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_DOWN,
          touch_position=device_env_service_pb2.Point(x=0.5, y=0.5),
      )
  )
  device.send_action(
      device_env_service_pb2.Action(
          action_type=device_env_service_pb2.ACTION_TYPE_TOUCH_UP,
      )
  )

  # 4. Run an ADB command directly:
  device.execute_adb_call(
      adb_pb2.AdbRequest(
          generic=adb_pb2.AdbRequest.GenericRequest(
              args=['shell', 'input', 'keyevent', 'KEYCODE_HOME']
          )
      )
  )
```

--------------------------------------------------------------------------------

## 3. Launch the Interactive Web Playground

AndroidEnv includes a web-based workbench (`android_env.playground`) that
connects directly to `AndroidDevice`. It provides:

*   Real-time interactive device display with mouse/touch input, hardware
    navigation buttons (`Back`, `Home`, `App Switch`), and text injection.
*   Live Accessibility Tree explorer with bidirectional node highlighting on the
    screen canvas.
*   Built-in ADB console for running shell commands and resetting tasks.

Run the Playground using Bazel:

```shell
bazel run //android_env/playground:playground -- \
    --config=android_env/playground/configs/emulator_config.py:my_avd
```

Or if installed via `pip` (`pip install "android-env[playground]"`):

```shell
# Connect to an already-running emulator or physical device:
android-env-playground --serial=emulator-5554

# Or launch a local AVD by name:
android-env-playground --avd_name=my_avd
```

You can also pass a custom `ml_collections` config file via
`python3 -m android_env.playground.playground --config=path/to/config.py`.

Open `http://localhost:8080` in your browser to interact with the device.

--------------------------------------------------------------------------------

## 4. Running Reinforcement Learning Tasks (`dm_env`)

To train RL agents with Markov Decision Process (MDP) rewards, episode step
limits, and automated reset steps, wrap `AndroidDevice` with
`android_env.rl.environment.AndroidEnv` and `TaskWrapper`:

*   For ready-made RL tasks (Vokram, Pong, DroidFish, Blockinger, 2048, and
    more), see [Available tasks](example_tasks.md).
*   To author your own `.textproto` task definitions, see the
    [Tasks guide](tasks_guide.md).

```python
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.proto import task_pb2
from android_env.rl import environment
from android_env.wrappers import task_wrapper
from google.protobuf import text_format

device = android_device_loader.load_android_device(device_config)
base_env = environment.AndroidEnv(device)

with open('path/to/my_task.textproto', 'r') as f:
  task_proto = text_format.Parse(f.read(), task_pb2.Task())

with task_wrapper.TaskWrapper(base_env, task=task_proto) as env:
  timestep = env.reset()
  while not timestep.last():
    action = select_action(timestep.observation)
    timestep = env.step(action)
```

### Example RL Agent Scripts

The `examples/` directory contains starter scripts for RL agents:

*   [`run_random_agent.py`](https://github.com/google-deepmind/android_env/blob/main/examples/run_random_agent.py):
    Runs a loop performing randomly sampled actions in an RL task.
*   [`run_acme_agent.py`](https://github.com/google-deepmind/android_env/blob/main/examples/run_acme_agent.py):
    Trains an [Acme](https://github.com/google-deepmind/acme) DQN agent on an
    AndroidEnv RL task.
