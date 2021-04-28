# AndroidEnv - Running the environment

In order to create an AndroidEnv instance you will need to provide two main
components: a [simulator](#the-simulator) and a [task](#the-task). In the
following sections we will provide information about how you can create these.

### The simulator

First, you will need to provide an Android device that environment (and through
it, the agent) can communicate with. While this could be a real device as well,
in most cases you will want to use a virtual, emulated device. There are many
ways to simulate such a device; in our example we will use
[Android Studio](https://developer.android.com/studio) to create one. Follow
this step-by-step [guide](emulator_guide.md) to create a virtual device, then
follow the steps below to attach this to your environment.

### The task

A `task` is a particular definition of an RL problem that the agent will be
interacting with. A `task` might include critical RL information such as what
are the rewards, when are episodes supposed to terminate, and what reset
procedures the environment should perform upon episode termination (e.g. start
or relaunch an app, clear cache etc.). These information are packaged into a
`Task()` proto message which gets passed passed to AndroidEnv. Please see
[tasks_guide.md](tasks_guide.md) for details on features and capabilities of
tasks, as well as how to create custom ones; or use one of our example tasks
provided in [example_tasks.md](example_tasks.md).

### Create the env

After setting up the simulator and creating a task, you might find that
`android_env.load()` function is a handy tool for creating an env instance, once
you provide the relevant arguments:

*   `task_path`: path pointing to the `.textproto` file describing the desired
    task.
*   `avd_name`: the name of the AVD specified when the AVD was created in
    Android Studio.
*   `android_avd_home` (Optional): Path where the AVD was installed. Defaults to
    `~/.android/avd`.
*   `android_sdk_root` (Optional): Root directory of the Android SDK. Defaults
    to `~/Android/Sdk`.
*   `emulator_path` (Optional): Path to the emulator binary. Defaults to
    `~/Android/Sdk/emulator/emulator`.
*   `adb_path` (Optional): Path to the ADB
    ([Android Debug Bridge](https://developer.android.com/studio/command-line/adb)).
    Defaults to `~/Android/Sdk/platform-tools/adb`.

Thus an example configuration might look like (depending on how you set up your
emulator):

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

## Example scripts

See our `examples` directory a few simple example agent setups.

*   `run_random_agent.py`: Runs a simple loop performing randomly selected
    actions in the environment.
*   `run_acme_agent.py`: Runs a training loop with an acme DQN agent,
    implemented in the popular DeepMind RL framework. This will require that the
    optional depenecy [acme](https://github.com/deepmind/acme) is installed.
*   `run_human_agent.py`: Creates a `pygame` instance that lets a human user
    interact with the environment and observe environment mechanics such as
    rewards or task extras. This will require that the optional depenecy
    [pygame](https://www.pygame.org/wiki/GettingStarted) is installed.
