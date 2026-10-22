# AndroidEnv - Android 智能体交互与学习平台

<p align="center">
  <a href="README.md">English</a> · <b>简体中文</b>
</p>

<img align="right" src="https://github.com/google-deepmind/android_env/raw/gh-pages/docs/images/device_control.gif" width="160" height="240">

[AndroidEnv](https://github.com/google-deepmind/android_env) 是一个基于 Python 和 Kotlin 构建的开源平台，用于与 [Android](https://www.android.com/) 设备（包括虚拟模拟器和物理真机）进行交互。专为基座模型（Foundation Model）UI 智能体、自动化测试以及强化学习（RL）研究而设计，AndroidEnv 能够对任意 Android 应用程序提供超低延迟的设备遥测与控制能力。

在 **AndroidEnv v2** 中，设备交互与强化学习任务定义实现了解耦：

*   **`AndroidDevice`（直接设备控制与遥测）**：一个免任务（task-free）轻量句柄，通过 WebSockets 连接到设备端的 Kotlin Core 守护服务，在注入触摸手势、按键事件、文本输入和 ADB 命令的同时，流式传输屏幕截图、无障碍树（Accessibility Trees）、系统日志与传感器数据。
*   **`AndroidEnv` 与 `TaskWrapper`（强化学习层）**：构建在 `AndroidDevice` 之上的可选 [`dm_env`](https://github.com/google-deepmind/dm_env) 封装层，通过[任务定义文件](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/tasks_guide.md)引入马尔可夫决策过程（MDP）语义（包括 `step()`、`reset()`、奖励函数与回合终止判定）。
*   **AndroidEnv Playground**：一个基于 Web 的高响应度交互式工作台，支持实时屏幕交互、无障碍树检查以及 ADB 命令执行。

[![tests](https://github.com/google-deepmind/android_env/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/google-deepmind/android_env/actions/workflows/tests.yml)
[![PyPI version](https://badge.fury.io/py/android-env.svg)](https://badge.fury.io/py/android-env)
[![Downloads](https://pepy.tech/badge/android-env)](https://pepy.tech/project/android-env)

## 目录导航 (Index)

*   [从 v1 迁移至 AndroidDevice (v2)](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/migrating_to_android_device.md)
*   [系统架构与环境细节](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/environment.md)
*   [运行 AndroidDevice、Playground 与强化学习智能体](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/instructions.md)
*   [配置 Android 虚拟设备 (AVD)](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/emulator_guide.md)
*   [在 AndroidEnv 中定义强化学习任务](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/tasks_guide.md)
*   [可下载的强化学习示例任务](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/example_tasks.md)

## 平台核心特性 (Platform Features)

*   **真实 Android 生态**：智能体直接与原汁原味的 Android 操作系统进行交互（支持 Android Studio 模拟器或真实物理手机），访问数十亿人类用户日常使用的完全相同的应用程序、UI 框架和系统服务。
*   **丰富且基于订阅的遥测数据 (`DeviceState`)**：可按需订阅智能体所需的遥测信号：
    *   **屏幕截图 (Screenshots)**：高帧率、已解码的 RGB 图像帧缓冲区（`width`, `height`, `raw_pixels`）。
    *   **无障碍树 (Accessibility Trees)**：直接从设备端 `AccessibilityService` 流式传输完整的 `AndroidAccessibilityForest` 窗口与 UI 节点层级树。
    *   **系统与传感器流**：前台应用包名/Activity、logcat 系统日志流、设备系统设置、GPS 地理位置、音频输出以及 IMU 惯性测量单元传感器（加速度计、陀螺仪、磁力计、气压计、光线传感器、近距离传感器）。
*   **表现力极强的动作接口 (`Action`)**：
    *   **触摸与多点触控手势**：归一化在 `[0.0, 1.0]` 范围内的 `(x, y)` 坐标，支持跨多个手指 `pointer_id` 的 `TOUCH_DOWN`、`TOUCH_MOVE` 与 `TOUCH_UP`，轻松模拟点击、滑动、滚动和双指捏合缩放。
    *   **硬件按键与原生文本输入**：注入 Android 物理按键代码（`BACK`, `HOME`, `ENTER` 等），在获得焦点的 UI 节点上直接设置文本内容（`ACTION_TYPE_SET_TEXT`），或触发剪贴板操作（`CUT`, `COPY`, `PASTE`）。
    *   **直接 ADB 命令执行**：通过 `device.execute_adb_call()` 运行结构化或通用的 `AdbRequest` 指令。
*   **可组合的强化学习层**：训练 RL 策略时，只需使用 `android_env.rl.environment.AndroidEnv` 和 `TaskWrapper` 包装 `AndroidDevice`，即可直接复用自定义的 `.textproto` 任务定义、奖励解析器以及 `dm_env` / Gymnasium 包装器。

## 快速入门 (Getting Started)

### 安装指南

通过 PyPI 安装 AndroidEnv：

```shell
$ python3 -m pip install android-env
```

或者从 `main` 分支克隆仓库代码并通过 Bazel 进行编译与测试：

```shell
$ git clone https://github.com/google-deepmind/android_env/
$ cd android_env
$ bazel test //...
```

本地使用 Bazel 构建 PyPI wheel 分发包：

```shell
$ bazel build //:android_env_wheel
```

### 1. 配置 Android 设备

通过 USB 调试（`adb devices`）连接物理 Android 设备，或者使用 Android Studio 创建 Android 虚拟设备（AVD）。详细分步操作请参阅[模拟器配置指南](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/emulator_guide.md)。

### 2. 使用 `AndroidDevice` 进行直接控制

对于无需强化学习回合循环（Episode loops）的 UI 智能体、大模型评测与自动化脚本：

```python
import numpy as np
from android_env.components import android_device_loader
from android_env.components import config_classes
from android_env.proto import device_env_service_pb2

config = config_classes.AndroidDeviceConfig(serial='emulator-5554')
with android_device_loader.load_android_device(config) as device:
  # 订阅屏幕截图与无障碍树信号：
  device.update_subscriptions({
      device_env_service_pb2.DEVICE_SIGNAL_SCREENSHOT,
      device_env_service_pb2.DEVICE_SIGNAL_ACCESSIBILITY_TREE,
  })

  # 读取最新设备状态：
  state = device.get_state()

  # 点击屏幕中心位置：
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

### 3. 启动交互式 Web Playground

直接在浏览器中实时浏览设备屏幕、检查无障碍树节点并执行 ADB 命令：

```shell
$ bazel run //android_env/playground:launch -- \
    --config=android_env/configs/emulator_config.py
```

### 4. 强化学习接入 (`dm_env`)

如需定义包含奖励机制与回合重置的 MDP 任务，请参阅[任务指南](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/tasks_guide.md)、[示例任务库](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/example_tasks.md)以及[详细操作说明](https://github.com/google-deepmind/android_env/blob/gh-pages/docs/instructions.md)。

## 关于 AndroidEnv (About)

本项目由 [Google DeepMind](https://deepmind.google/) 研发并维护。您可以查阅发布在 arXiv 上的原始[技术论文](https://arxiv.org/abs/2105.13231)以及官方[介绍博客文章](https://www.deepmind.com/publications/androidenv-the-android-learning-environment)。

如果您在学术研究中使用了 AndroidEnv，请参考以下 BibTeX 条目引用本工作：

```bibtex
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

免责声明：这不是一款得到 Google 官方支持的产品 (Disclaimer: This is not an official Google product)。

---

> **翻译说明（Translation Disclaimer）**
> 本文档由社区志愿者（[@JasonYeYuhe](https://github.com/JasonYeYuhe)）人工翻译并维护，旨在降低中文开发者的阅读门槛。最后同步日期：2026年10月22日。若译文与英文原版存在任何出入或滞后，请以 [英文原版 (README.md)](README.md) 为准。欢迎通过 PR 协助改进译文！
