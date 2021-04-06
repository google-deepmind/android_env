# AndroidEnv - Instructions

<!-- copybara:strip_begin -->

<!--*
# Document freshness: For more information, see go/fresh-source.
freshness: { owner: 'agergely' reviewed: '2021-02-19' }
*-->

<!-- copybara:strip_end -->

## Loading the environment

In order to create an AndroidEnv instance you will need to provide two main
components: a [simulator](#the-simulator) and a [task](#the-task). In the
following sections we will provide information about how you can create these.

### The simulator

First, you will need to provide an Android device that environment (and through
it, the agent) can communicate with. While this could be a real device as well,
in most cases you will want to use a virtual, emulated device. There are many
ways to simulate such a device; in our example we will use
[Android Studio](https://developer.android.com/studio) to create one and walk
you through the necessary steps for attaching this to your environment.

TODO(agergely) Add instructions for creating an AVD with Android Studio

### The task

A `task` is a particular definition of an RL problem that the agent will be
interacting with. A `task` might include critical RL information such as what
are the rewards, when are episodes supposed to terminate, and what reset
procedures the environment should perform upon episode termination (e.g. start
or relaunch an app, clear cache etc.). These information are packaged into a
`Task()` proto message which gets passed passed to AndroidEnv. Please see
[tasks.md](tasks.md) for details on features and capabilities of tasks, as well
as how to create custom ones; or use one of our example tasks provided at
[this link](https://pantheon.corp.google.com/storage/browser/android_env-tasks).

### Create the env

After setting up the simulator and creating a task, you might find that the
`load()` function in `loader.py` is a handy tool for creating an env instance,
once you provide all relevant arguments:

*   `avd_name`: the name of the AVD specified when the AVD was created in
    Android Studio.
*   `android_avd_home`: Path where the AVD was installed.
*   `android_sdk_root`: Root directory of the Android SDK.
*   `emulator_path`: Path to the emulator binary.
*   `adb_path`: Path to the ADB.
*   `task_path`: path poiting to the `.textproto` file describing the desired
    task.

Thus an example configuration might look like (depending on how you set up your
emulator):

```
--avd_name=my_avd
--android_avd_home=/Users/username/.android/avd
--android_sdk_root=/Users/username/Library/Android/sdk
--emulator_path=/Users/username/Library/Android/sdk/emulator/emulator
--adb_path=/Users/username/Library/Android/sdk/platform-tools/adb
--task_path=/Users/username/android_env/my_tasks/my_task.textproto
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
