# AndroidEnv - Running the environment

In order to create an AndroidEnv instance you will need to provide two main
components: a [simulator](#the-simulator) and a [task](#the-task). In the
following sections you will learn how you can create them.

### The simulator

First, you will need to provide your Android virtual device (AVD) that the
environment (and through it, the agent) can communicate with. While this can also
be a physical device, in most cases you will need a virtual emulated device.
There are many ways to emulate an AVD - in our examples, we will use
[Android Studio](https://developer.android.com/studio) to create one.

1. In Android Studio, create a virtual device by following this step-by-step
[guide](emulator_guide.md).
2. Follow the steps below to attach the AVD to your environment.

### The task and examples with games and other apps

A `task` is a particular definition of an RL problem that the agent will be
interacting with. A `task` may include critical RL information, such as what the
rewards are, when the episodes are supposed to terminate, and what the reset
procedures are that the environment should perform upon episode termination
(e.g. start or relaunch an app, clear cache, etc.). This information is packaged
into a `Task()` proto message, which gets passed passed to AndroidEnv.

* For ready-made example tasks provided with AndroidEnv, check out
  the [Available tasks](example_tasks.md), featuring Vokram (with Markov Decision
  Process (MDP)), Pong, DroidFish (a chess clone), Blockinger (a tetris clone),
  and more.

* See the [Tasks guide](tasks_guide.md) for details on features and
  capabilities of tasks, as well as how to create custom ones.

### Create the environment

After setting up the simulator and creating a task, you may find the 
`android_env.load()` function handy for creating an environment instance by
providing relevant arguments, such as:

*   `task_path`: the path pointing to the `.textproto` file describing the
    desired task.
*   `avd_name`: the name of the AVD specified when your created it in Android
    Studio.
*   `android_avd_home` (Optional): the path to where the AVD is installed. 
    (default value: `~/.android/avd`).
*   `android_sdk_root` (Optional): thr root directory of the Android SDK. 
    (default value: `~/Android/Sdk`).
*   `emulator_path` (Optional): the path to the emulator binary. (default:
    `~/Android/Sdk/emulator/emulator`).
*   `adb_path` (Optional): the path to the ADB
    ([Android Debug Bridge](https://developer.android.com/studio/command-line/adb)).
    (default value: `~/Android/Sdk/platform-tools/adb`).

Your example configuration may look like, depending on how you set up your
emulator:

```python
import android_env

env = android_env.load(
    avd_name='my_avd',
    android_avd_home='/Users/username/.android/avd',
    android_sdk_root='/Users/username/Library/Android/sdk',
    emulator_path='/Users/username/Library/Android/sdk/emulator/emulator',
    adb_path='/Users/username/Library/Android/sdk/platform-tools/adb',
    task_path='/Users/username/android_env/my_tasks/my_task.textproto',
)
```

## Example RL agent scripts

The `examples` directory contains a few simple example agent setups, such as:

*   [`run_random_agent.py`](https://github.com/deepmind/android_env/blob/main/examples/run_random_agent.py):
    Runs a simple loop performing randomly selected actions in the environment.
*   [`run_acme_agent.py`](https://github.com/deepmind/android_env/blob/main/examples/run_acme_agent.py):
    Runs a training loop with an [Acme](https://deepmind.com/research/publications/Acme)
    DQN agent, implemented in the popular DeepMind RL framework. This will
    require to install the [`acme`](https://github.com/deepmind/acme)
    dependency.
*   [`run_human_agent.py`](https://github.com/deepmind/android_env/blob/main/examples/run_human_agent.py):
    Creates a [`pygame`](https://www.pygame.org) instance that lets a human user
    interact with the environment and observe environment mechanics, such as
    rewards or task extras. You will need to install the [PyGame] dependency.
