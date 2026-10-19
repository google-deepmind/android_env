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

/**
 * The core, raw Android Device Environment interface. Provides direct, non-blocking state access
 * and asynchronous action injection.
 */
interface AndroidDeviceEnv {
  /** Dynamically updates the active set of signals. Stops unneeded services immediately. */
  fun updateSubscriptions(activeSignals: Set<DeviceSignal>)

  /**
   * Non-blocking pull of the absolute latest device state. Unsubscribed signals in the returned
   * DeviceState will have StreamedSignal.value = null.
   */
  fun getDeviceState(): DeviceState

  /**
   * Asynchronously injects an action (touches, keycodes) into the device. Consumes resources only
   * during the event injection (event-driven).
   */
  fun injectAction(action: Action)

  /** Frees up resources (e.g. stops background logcat readers, sensor listeners). */
  fun close() {}
}
