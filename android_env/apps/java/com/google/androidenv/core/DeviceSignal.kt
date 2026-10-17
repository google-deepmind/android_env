// Copyright 2026 DeepMind Technologies Limited.
//
// Licensed under the Apache License, Version 2.0 (the "License");
// you may not use this file except in compliance with the License.
// You may obtain a copy of the License at
//
//     http://www.apache.org/licenses/LICENSE-2.0
//
// Unless required by applicable law or agreed to in writing, software
// distributed under the License is distributed on an "AS IS" BASIS,
// WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
// See the License for the specific language governing permissions and
// limitations under the License.

package com.google.androidenv.core

/** Signals that can be dynamically subscribed to. */
enum class DeviceSignal {
  SCREENSHOT,
  ACCESSIBILITY_TREE,
  ACCESSIBILITY_EVENTS,
  ACTIVE_PACKAGE,
  ACTIVE_ACTIVITY,
  SYSTEM_LOGS,
  RUNNING_PROCESSES,
  DEVICE_SETTINGS,
  SENSOR_ACCELEROMETER,
  SENSOR_GYROSCOPE,
  SENSOR_MAGNETOMETER,
  SENSOR_BAROMETER,
  SENSOR_AMBIENT_TEMP,
  SENSOR_LIGHT,
  SENSOR_PROXIMITY,
  SENSOR_HEART_RATE,
  LOCATION_GPS,
  AUDIO_OUTPUT,
  BATTERY_POWER,
}
