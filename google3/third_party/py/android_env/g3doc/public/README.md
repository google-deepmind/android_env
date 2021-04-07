<!-- copybara:strip_begin -->
<!--*
# Document freshness: For more information, see go/fresh-source.
freshness: { owner: 'agergely' reviewed: '2021-04-06' }
*-->
<!-- copybara:strip_end -->

# AndroidEnv - The Android Learning Environment

<img align="right" src="images/device_control.gif" width="160" height="240">

[AndroidEnv](https://github.com/deepmind/android_env) is a Python library that
exposes an [Android](https://www.android.com/) device as a Reinforcement
Learning (RL) environment. The library provides a flexible platform for defining
custom tasks on top of the Android OS, including any Android application. Agents
interact with the device through a universal action interface - the
touchscreen - by sending localized touch and lift events to the system. The
library processes these events and returns pixel observations and rewards as
provided by specific [task definitions](tasks.md). For example, rewards might be
given for events such as successfully scrolling down a page, sending an email,
or achieving some score in a game, depending on the research purpose and how the
user configures the task.

## Environment features

There are a number of aspects that make AndroidEnv a challenging yet suitable
environment for Reinforcement Learning research:

*  Allowing agents to interact with a system used daily by billions of
    users around the world, AndroidEnv offers a platform for RL agents to navigate,
    learn tasks and have direct impact in **real-world contexts**. The environment wraps
    a simulaterd Android device, which runs independently from the environment,
    completely unaltered, and works in exactly the same way as the devices that
    humans use, exposing exactly the same features and services.

*  The platform offers a virtually infinite **range of possible tasks**,
    all sharing a common action interface. The library facilitates
    the design of Reinforcement Learning tasks for any existing or custom built
    Android application. For example, it exposes the broad world of Android
    games, ranging from card games, puzzle games, time reactive games,
    all requiring a diverse set of action combinations and interaction types.

*  The environment runs on top of a **real-time simulation** of an Android
    device. In other words, the environment dynamics does not wait for the agent
    to deliberate, and the speed of the simulation cannot be increased.

*  The observation is a collection of **RGB values** corresponding to the displayed
    pixels on the screen. The exact screen resolution depends on the
    simulated device, but in general it will be considered relatively large in
    an RL context. However, users have the option of downsampling each
    observation.

*  The learning environment has an interesting, **complex action space** unique
    to the touchscreen interface of Android.

    *   The raw, **hybrid action space** consists of a continuous tuple signifying the
        action location, and a discrete signal determining whether the agent
        wants to touch the screen or lift its virtual finger.
    *   Raw actions are highly **composable**: the Android UI and most
        applications were designed so that they could be intuitively navigated
        via common [touchscreen gestures](https://developer.android.com/training/gestures/detector) 
        such as tapping, scrolling, swiping,
        pinching, drag & drop etc. This is still the case in AndroidEnv: to
        trigger meaningful changes in the environment, the agent often has to
        perform carefully timed and positioned sequences of raw actions. For
        example, in order to navigate to the next image in a photo gallery, the
        agent would have to perform a *swipe*, touching the screen multiple times,
        gradually shifting the actions' positions to the right. Thus, in most
        contexts raw actions do not trigger changes in the state of the environment
        unless correctly chained together to make up a human gesture.
    *   The action interface is **closely related to the observation space**, as
        meaningful touch and lift events are often either co-localized or
        strongly correlated to the location or movement of salient objects in
        the observation. For example, the position of a button on the screen
        aligns with the location of the actions that trigger the button press.
    *   The library provides tools for flexibly **altering the action interface**
        if needed for particular studies, such as discretization or hard-coding
        gesture skills. Still, we believe that the real challenge remains in
        devising agents that are capable of dealing with a large suite of
        diverse tasks, through acting and learning in the complex unifying
        action interface.

## About

This library is developed and maintained by [DeepMind](http://deepmind.com). \
You can find the [technical report](https://arxiv.org/) on Arxiv, as well as an
introductory [blog post](https://deepmind.com/) on DeepMind's website.

Disclaimer: This is not an official Google product.

# Environment Details

For a full description of the specifics of how the environment is configured, or
details on how the observations and action spaces work, please read the
[environment documentation](environment.md). To find out how to define a custom
task, or to explore some example tasks we provided, see the
[task documentation](tasks.md).

# Quick Start Guide

Follow these instructions to install, configure and use AndroidEnv in your own
RL experiments.

## Installing AndroidEnv

### PyPI

TODO(kenjitoyama): Please verify that the instructions are correct and
functional.

The easiest way to get AndroidEnv is to use pip:

```shell
$ pip install android_env
```

That will install the `android_env` package along with all the required
dependencies. You may need to upgrade pip: `pip install --upgrade pip` for the
`android_env` install to work.

### From Source

TODO(kenjitoyama): Please verify that the instructions are correct and
functional.

Alternatively you can install latest AndroidEnv codebase from git master branch:

```shell
$ pip install --upgrade TODO
```

or from a local clone of the git repo:

```shell
$ git clone TODO
$ pip install --upgrade TODO
```

### Linux

TODO(kenjitoyama): Add instructions.

### Windows/MacOS

TODO(kenjitoyama): Add instructions. (Do we support windows?)

## Configure a task

The library provides a straightforward mechanism for setting up restricted task
contexts and specifying objectives for the agent. To learn how to define a task
on Android, see the [task documentation](tasks.md). Here you can also find some
example task definitions we provided to demonstrate the usage of the simple
mechanism AndroidEnv offers for flexibly creating custom challenges.

## Run the environment

To find out how to run and train agents on AndroidEnv, see these
[detailed instructions](instructions.md). Here you can also find example scripts
demonstrating how to run a random agent, an
[acme](https://github.com/deepmind/acme) agent, or a human agent on AndroidEnv.

## Run the tests

TODO(kenjitoyama): Add instructions for running tests

If you want to submit a pull request, please make sure the tests pass on 3.

```shell
$ TODO
```
