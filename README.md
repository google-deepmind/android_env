
# AndroidEnv - The Android Learning Environment

<img align="right" src="docs/images/device_control.gif" width="160" height="240">

[AndroidEnv](https://github.com/deepmind/android_env) is a Python library that
exposes an [Android](https://www.android.com/) device as a Reinforcement
Learning (RL) environment. The library provides a flexible platform for defining
custom tasks on top of the Android Operating System, including any Android
application. Agents interact with the device through a universal action
interface - the touchscreen - by sending localized touch and lift events to the
system. The library processes these events and returns pixel observations and
rewards as provided by specific [task definitions](docs/tasks_guide.md). For
example, rewards might be given for events such as successfully scrolling down a
page, sending an email, or achieving some score in a game, depending on the
research purpose and how the user configures the task.

[![tests](https://github.com/deepmind/android_env/actions/workflows/tests.yml/badge.svg?branch=main)](https://github.com/deepmind/android_env/actions/workflows/tests.yml)
[![PyPI version](https://badge.fury.io/py/android-env.svg)](https://badge.fury.io/py/android-env)
[![Downloads](https://pepy.tech/badge/android-env)](https://pepy.tech/project/android-env)

## Index

*   [Environment details](android_env/g3doc/public/docs/environment.md)
*   [Running AndroidEnv](android_env/g3doc/public/docs/instructions.md)
*   [Setting up a virtual Android device](android_env/g3doc/public/docs/emulator_guide.md)
*   [Defining a task in AndroidEnv](android_env/g3doc/public/docs/tasks_guide.md)
*   [Example tasks available for download](android_env/g3doc/public/docs/example_tasks.md)

## Environment features

There are a number of aspects that make AndroidEnv a challenging yet suitable
environment for Reinforcement Learning research:

*   Allowing agents to interact with a system used daily by billions of users
    around the world, AndroidEnv offers a platform for RL agents to navigate,
    learn tasks and have direct impact in **real-world contexts**. The
    environment wraps a simulated Android device, which runs independently from
    the environment, completely unaltered, and works in exactly the same way as
    the devices that humans use, exposing exactly the same features and
    services.

*   The platform offers a virtually infinite **range of possible tasks**, all
    sharing a common action interface. The library facilitates the design of
    Reinforcement Learning tasks for any existing or custom built Android
    application. For example, it exposes the broad world of Android games,
    ranging from card games, puzzle games, time reactive games, all requiring a
    diverse set of action combinations and interaction types.

*   The environment runs on top of a **real-time simulation** of an Android
    device. In other words, the environment dynamics does not wait for the agent
    to deliberate, and the speed of the simulation cannot be increased.

*   The observation is a collection of **RGB values** corresponding to the
    displayed pixels on the screen. The exact screen resolution depends on the
    simulated device, but in general it will be considered relatively large in
    an RL context. However, users have the option of downsampling each
    observation.

*   The learning environment has an interesting, **complex action space** unique
    to the touchscreen interface of Android.

    *   The raw, **hybrid action space** consists of a continuous tuple
        signifying the action location, and a discrete signal determining
        whether the agent wants to touch the screen or lift its virtual finger.
    *   Raw actions are highly **composable**: the Android UI and most
        applications were designed so that they could be intuitively navigated
        via common
        [touchscreen gestures](https://developer.android.com/training/gestures/detector)
        such as tapping, scrolling, swiping, pinching, drag & drop etc. This is
        still the case in AndroidEnv: to trigger meaningful changes in the
        environment, the agent often has to perform carefully timed and
        positioned sequences of raw actions. For example, in order to navigate
        to the next image in a photo gallery, the agent would have to perform a
        *swipe*, touching the screen multiple times, gradually shifting the
        actions' positions to the right. Thus, in most contexts raw actions do
        not trigger changes in the state of the environment unless correctly
        chained together to make up a human gesture.
    *   The action interface is **closely related to the observation space**, as
        meaningful touch and lift events are often either co-localized or
        strongly correlated to the location or movement of salient objects in
        the observation. For example, the position of a button on the screen
        aligns with the location of the actions that trigger the button press.
    *   The library provides tools for flexibly **altering the action
        interface** if needed for particular studies, such as discretization or
        hard-coding gesture skills. Still, we believe that the real challenge
        remains in devising agents that are capable of dealing with a large
        suite of diverse tasks, through acting and learning in the complex
        unifying action interface.

# Getting started

### Installation

The easiest way to get AndroidEnv is with pip:

```shell
$ python3 -m pip install android-env
```

Please note that `/examples` are not included in this package.

Alternatively, you can clone the repository from git's `main` branch:

```shell
$ git clone https://github.com/deepmind/android_env/
$ cd android_env
$ python3 setup.py install
```

Update: the environment now runs on Windows, but please keep in mind that this
option is not well-maintained or widely supported, as Unix-based systems are the
primary target platforms of this project.

### Create a simulator

Before running the environment, you will need access to an emulated Android
device. For instructions on creating a virtual Android device, see the
[Emulator guide](docs/emulator_guide.md).

### Define a task

Then, you will want to define what the agent's *task* is. At this point, the
agent will be able to communicate with the emulated device, but it will not yet
have an objective, or access to signals such as rewards or RL episode ends.
Learn [how to define an RL task](docs/tasks_guide.md) of your own, or use one of
the [existing task definitions](docs/example_tasks.md) for training.

### Load and run

To find out how to run and train agents on AndroidEnv, see these
[detailed instructions](docs/instructions.md). Here you can also find example
scripts demonstrating how to run a random agent, an
[acme](https://github.com/deepmind/acme) agent, or a human agent on AndroidEnv.

## About

This library is developed and maintained by [DeepMind](http://deepmind.com). \
You can find the [technical report](https://arxiv.org/abs/2105.13231) on Arxiv,
as well as an introductory
[blog
post](https://www.deepmind.com/publications/androidenv-the-android-learning-environment)
on DeepMind's website.

If you use AndroidEnv in your research, you can cite the paper using the
following BibTeX:

```
@article{ToyamaEtAl2021AndroidEnv,
  title     = {{AndroidEnv}: A Reinforcement Learning Platform for Android},
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
