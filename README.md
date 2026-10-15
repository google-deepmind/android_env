
# AndroidEnv - The Android Interaction & Learning Platform

<img align="right" src="https://github.com/google-deepmind/android_env/raw/gh-pages/docs/images/device_control.gif" width="160" height="240">

[AndroidEnv](https://github.com/google-deepmind/android_env) is a Python and
Kotlin platform for interacting with [Android](https://www.android.com/) devices
(both virtualized emulators and physical hardware). Built for foundation model
UI agents, automated testing, and Reinforcement Learning (RL) research,
AndroidEnv provides low-latency device telemetry and control over any Android
application.

In **AndroidEnv v2**, device interaction is decoupled from Reinforcement
Learning task definitions:

*   **`AndroidDevice` (Direct Device Control & Telemetry)**: A task-free handle
    that connects to an on-device Kotlin Core server over WebSockets to stream
    screenshots, accessibility trees, system logs, and sensor data while
    injecting touch gestures, key events, text, and ADB commands.
*   **`AndroidEnv` & `TaskWrapper` (Reinforcement Learning)**: An optional
    [`dm_env`](https://github.com/google-deepmind/dm_env) layer on top of
    `AndroidDevice` that adds Markov Decision Process (MDP) semantics (`step()`,
    `reset()`, rewards, and episode terminations) via
    [task definitions](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/tasks_guide.md).
*   **AndroidEnv Playground**: A responsive web workbench for live screen
    interaction, accessibility tree inspection, and ADB command execution.

[![tests](https://github.com/google-deepmind/android_env/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/google-deepmind/android_env/actions/workflows/tests.yml)
[![PyPI version](https://badge.fury.io/py/android-env.svg)](https://badge.fury.io/py/android-env)
[![Downloads](https://pepy.tech/badge/android-env)](https://pepy.tech/project/android-env)

## Index

*   [Migrating from v1 to AndroidDevice (v2)](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/migrating_to_android_device.md)
*   [Architecture & environment details](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/environment.md)
*   [Running AndroidDevice, Playground, and RL agents](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/instructions.md)
*   [Setting up a virtual Android device](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/emulator_guide.md)
*   [Defining an RL task in AndroidEnv](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/tasks_guide.md)
*   [Example RL tasks available for download](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/example_tasks.md)

## Platform Features

*   **Real-World Android Ecosystem**: Agents interact with an unaltered Android
    OS—on Android Studio Emulators or physical devices—exposing the exact same
    apps, UI frameworks, and system services that billions of human users
    interact with daily.
*   **Rich, Subscription-Based Telemetry (`DeviceState`)**: Subscribe on demand
    to the signals your agent needs:
    *   **Screenshots**: High-speed, decoded RGB frame buffers (`width`,
        `height`, `raw_pixels`).
    *   **Accessibility Trees**: Full `AndroidAccessibilityForest` window and UI
        node hierarchies streamed directly from the on-device
        `AccessibilityService`.
    *   **System & Sensor Streams**: Foreground package/activity, logcat
        streams, device settings, GPS location, audio output, and IMU sensors
        (accelerometer, gyroscope, magnetometer, barometer, light, proximity).
*   **Expressive Action Interface (`Action`)**:
    *   **Touch & Multi-Touch Gestures**: Normalized `(x, y)` coordinates in
        `[0.0, 1.0]` with `TOUCH_DOWN`, `TOUCH_MOVE`, and `TOUCH_UP` across
        multiple `pointer_id` fingers for taps, swipes, scrolls, and pinches.
    *   **Hardware Keys & Native Text Entry**: Inject Android keycodes (`BACK`,
        `HOME`, `ENTER`), set text directly on focused UI nodes
        (`ACTION_TYPE_SET_TEXT`), or trigger clipboard actions (`CUT`, `COPY`,
        `PASTE`).
    *   **Direct ADB Execution**: Run structured or generic `AdbRequest`
        commands via `device.execute_adb_call()`.
*   **Composable RL Layer**: When training RL policies, wrap `AndroidDevice`
    with `android_env.rl.environment.AndroidEnv` and `TaskWrapper` to use custom
    `.textproto` tasks, reward parsers, and `dm_env` / Gymnasium wrappers.

## Getting Started

### Installation

Install AndroidEnv from PyPI:

```shell
$ python3 -m pip install android-env
```

Or clone the repository from `main` and build/test with Bazel:

```shell
$ git clone https://github.com/google-deepmind/android_env/
$ cd android_env
$ bazel test //...
```

To build the PyPI wheel locally using Bazel:

```shell
$ bazel build //:android_env_wheel
```

### 1. Set Up an Android Device

Connect a physical Android device via USB debugging (`adb devices`) or create an
Android Virtual Device (AVD) using Android Studio. See the
[Emulator guide](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/emulator_guide.md)
for step-by-step instructions.

### 2. Direct Control with `AndroidDevice`

For UI agents, foundation model evaluations, and automation scripts that do not
need RL episode loops:

```python
import numpy as np
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.proto import device_env_service_pb2

config = config_classes.AndroidDeviceConfig(serial='emulator-5554')
with android_device_loader.load_android_device(config) as device:
  # Subscribe to screenshots and accessibility trees:
  device.update_subscriptions({
      device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
      device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
  })

  # Read the latest device state:
  state = device.get_state()

  # Tap the center of the screen:
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
```

### 3. Launch the Interactive Web Playground

Explore the device screen, inspect live accessibility trees, and run ADB
commands from your browser:

```shell
$ bazel run //android_env/playground:launch -- \
    --config=android_env/configs/emulator_config.py
```

### 4. Reinforcement Learning (`dm_env`)

To define MDP tasks with rewards and episode resets, see the
[Tasks guide](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/tasks_guide.md),
[Example tasks](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/example_tasks.md),
and
[detailed instructions](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/instructions.md).

## About

This library is developed and maintained by
[Google DeepMind](https://deepmind.google/). You can find the original
[technical report](https://arxiv.org/abs/2105.13231) on arXiv, as well as the
introductory
[blog post](https://www.deepmind.com/publications/androidenv-the-android-learning-environment).

If you use AndroidEnv in your research, you can cite the paper using the
following BibTeX:

```
@article{ToyamaEtAl2021AndroidEnv,
  title     = "{AndroidEnv}: A Reinforcement Learning Platform for Android",
  author    = {Daniel Toyama and Philippe Hamel and Anita Gergely and
               Gheorghe Comanici and Amelia Glaese and Zafarali Ahmed and Tyler
               Jackson and Shibl Mourad and Doina Precup},
  year      = {2021},
  eprint    = {2105.13231},
  archivePrefix = {arXiv},
  primaryClass = {cs.LG},
  volume    = {abs/2105.13231},
  url       = {http://arxiv.org/abs/2105.13231},
}
```

Disclaimer: This is not an official Google product.
