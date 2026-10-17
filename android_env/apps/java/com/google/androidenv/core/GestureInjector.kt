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

import android.accessibilityservice.GestureDescription
import android.view.accessibility.AccessibilityNodeInfo

/** Interface for injecting gestures and querying accessibility node info. */
interface GestureInjector {
  fun injectGesture(
    gesture: GestureDescription,
    callback: android.accessibilityservice.AccessibilityService.GestureResultCallback? = null,
  )

  fun getRootNode(): AccessibilityNodeInfo?

  fun getRootNodes(): List<AccessibilityNodeInfo> {
    return getRootNode()?.let { listOf(it) } ?: emptyList()
  }

  fun getActivePackage(): String

  fun getActiveActivity(): String

  fun popEvents(): List<com.google.androidenv.accessibilityforwarder.EventRequest>

  fun setEventTrackingEnabled(enabled: Boolean)

  fun clearEvents()

  @com.google.errorprone.annotations.CanIgnoreReturnValue
  fun performGlobalAction(action: Int): Boolean
}

/** Production implementation that delegates to the InputService singleton. */
class SystemGestureInjector : GestureInjector {
  override fun injectGesture(
    gesture: GestureDescription,
    callback: android.accessibilityservice.AccessibilityService.GestureResultCallback?,
  ) {
    InputService.getInstance().injectGesture(gesture, callback)
  }

  override fun getRootNode(): AccessibilityNodeInfo? {
    return InputService.getInstance().getRootNode()
  }

  override fun getRootNodes(): List<AccessibilityNodeInfo> {
    return try {
      InputService.getInstance().getRootNodes()
    } catch (e: Exception) {
      val root = getRootNode()
      if (root != null) listOf(root) else emptyList()
    }
  }

  override fun getActivePackage(): String {
    return InputService.activePackage
  }

  override fun getActiveActivity(): String {
    return InputService.activeActivity
  }

  override fun popEvents(): List<com.google.androidenv.accessibilityforwarder.EventRequest> {
    return try {
      InputService.getInstance().popEvents()
    } catch (e: Exception) {
      emptyList()
    }
  }

  override fun setEventTrackingEnabled(enabled: Boolean) {
    try {
      InputService.getInstance().isEventTrackingEnabled = enabled
    } catch (e: Exception) {
      // Ignored if service not bound
    }
  }

  override fun clearEvents() {
    try {
      InputService.getInstance().clearEvents()
    } catch (e: Exception) {
      // Ignored if service not bound
    }
  }

  override fun performGlobalAction(action: Int): Boolean {
    return InputService.getInstance().performGlobalAction(action)
  }
}
