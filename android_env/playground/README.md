# AndroidEnv Playground

Interactive playground for AndroidEnv, allowing human interaction via a web
browser. It streams the emulator screen and forwards your clicks, touches, and
keyboard inputs over WebSockets, avoiding X11 and Pygame display issues.

## Quick Start (Open Source)

### Prerequisites

1. **Android SDK and Tools**:
   Ensure `adb` and `emulator` are installed and available in `$PATH`
   (or located under `$ANDROID_HOME` or `~/Android/Sdk`).
2. **Android Virtual Device (AVD)**:
   Create an AVD using Android Studio or the `avdmanager` command-line tool.
   For AndroidWorld evaluation, ensure your AVD is named `androidworld_avd`
   (or customize via the config parameter).

### Option 1: Running with Bazel

Run the Playground binary directly using Bazel:

```bash
bazel run //android_env/playground:playground -- \
  --config=android_env/playground/configs/emulator_config.py \
  --port=8080 \
  --alsologtostderr
```

You can pass a custom AVD name as a configuration argument:

```bash
bazel run //android_env/playground:playground -- \
  --config=android_env/playground/configs/emulator_config.py:my_custom_avd \
  --port=8080
```

### Option 2: Running with Python

After installing `android-env[playground]` via pip:

```bash
# Connect to an already-running emulator or physical device:
android-env-playground --serial=emulator-5554 --port=8080

# Or launch a local AVD directly by name:
android-env-playground --avd_name=androidworld_avd --port=8080
```

Or run the module with a custom config file from a source checkout:

```bash
python -m android_env.playground.playground \
  --config=android_env/playground/configs/emulator_config.py \
  --port=8080
```

### Accessing the Interface

Once the server logs `Serving on port 8080...`, open your browser to:

[http://localhost:8080](http://localhost:8080)

If you are running on a remote server or cloud workstation, forward the port
via SSH:

```bash
ssh -L 8080:localhost:8080 <remote_host>
```
