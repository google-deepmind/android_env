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

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.util.Log
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo

/**
 * AccessibilityService that handles action injection (gestures) and accessibility tree gathering.
 * Must be manually enabled in Android Settings.
 */
class InputService : AccessibilityService() {

  override fun onCreate() {
    Log.i(TAG, "InputService::onCreate()")
    super.onCreate()
    instance = this
  }

  override fun onServiceConnected() {
    Log.i(TAG, "InputService::onServiceConnected()")
    super.onServiceConnected()
    instance = this
  }

  @Volatile var isEventTrackingEnabled: Boolean = false
  private val eventBuffer =
    mutableListOf<com.google.androidenv.accessibilityforwarder.EventRequest>()

  override fun onAccessibilityEvent(event: AccessibilityEvent) {
    if (isEventTrackingEnabled) {
      val map = mutableMapOf<String, String>()
      map["event_type"] = AccessibilityEvent.eventTypeToString(event.eventType)
      map["package_name"] = event.packageName?.toString() ?: ""
      map["class_name"] = event.className?.toString() ?: ""
      map["text"] = event.text.filterNotNull().joinToString(" ")
      map["content_description"] = event.contentDescription?.toString() ?: ""
      map["event_time"] =
        ((System.currentTimeMillis() - android.os.SystemClock.uptimeMillis() + event.eventTime) *
            1000L)
          .toString()

      val eventProto =
        com.google.androidenv.accessibilityforwarder.EventRequest.newBuilder()
          .putAllEvent(map)
          .build()

      synchronized(eventBuffer) {
        if (eventBuffer.size < 1000) {
          eventBuffer.add(eventProto)
        }
      }
    }

    if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
      val pkg = event.packageName?.toString()
      val cls = event.className?.toString()
      if (pkg != null) {
        activePackage = pkg
      }
      if (cls != null) {
        activeActivity = cls
      }
      if (
        pkg == "com.android.systemui" && cls?.contains("MediaProjectionPermissionActivity") == true
      ) {
        autoAcceptMediaProjection()
      }
    }
  }

  fun clearEvents() {
    synchronized(eventBuffer) { eventBuffer.clear() }
  }

  fun popEvents(): List<com.google.androidenv.accessibilityforwarder.EventRequest> {
    synchronized(eventBuffer) {
      val copy = ArrayList(eventBuffer)
      eventBuffer.clear()
      return copy
    }
  }

  private fun autoAcceptMediaProjection() {
    Log.i(TAG, "Attempting to auto-accept MediaProjection permission dialog...")
    val rootNode = rootInActiveWindow
    if (rootNode == null) {
      Log.w(TAG, "rootInActiveWindow is null")
      return
    }

    // Search for "Start now" (English)
    var nodes = rootNode.findAccessibilityNodeInfosByText("Start now")
    if (nodes.isEmpty()) {
      // Try "Start recording"
      nodes = rootNode.findAccessibilityNodeInfosByText("Start recording")
    }
    if (nodes.isEmpty()) {
      Log.w(TAG, "Could not find 'Start now' or 'Start recording' button")
      dumpNodeTree(rootNode, 0)
      return
    }

    for (node in nodes) {
      if (node.isClickable) {
        val success = node.performAction(AccessibilityNodeInfo.ACTION_CLICK)
        Log.i(TAG, "Clicked auto-accept button: ${node.text}, success=$success")
        if (success) return
      } else {
        var parent = node.parent
        while (parent != null) {
          if (parent.isClickable) {
            val success = parent.performAction(AccessibilityNodeInfo.ACTION_CLICK)
            Log.i(TAG, "Clicked parent auto-accept button: success=$success")
            if (success) return
          }
          parent = parent.parent
        }
      }
    }
    Log.w(TAG, "Failed to click any matching button")
  }

  private fun dumpNodeTree(node: AccessibilityNodeInfo?, depth: Int) {
    if (node == null) return
    val indent = "  ".repeat(depth)
    Log.d(
      TAG,
      "$indent Node: text=${node.text}, class=${node.className}, id=${node.viewIdResourceName}, clickable=${node.isClickable}",
    )
    for (i in 0 until node.childCount) {
      dumpNodeTree(node.getChild(i), depth + 1)
    }
  }

  override fun onInterrupt() {}

  fun getRootNode(): AccessibilityNodeInfo? {
    return rootInActiveWindow
  }

  fun getRootNodes(): List<AccessibilityNodeInfo> {
    val roots = mutableListOf<AccessibilityNodeInfo>()
    val allWindows =
      try {
        windows
      } catch (e: Exception) {
        null
      }
    if (!allWindows.isNullOrEmpty()) {
      for (w in allWindows) {
        val root = w.root
        if (root != null) {
          roots.add(root)
        }
      }
    }
    if (roots.isEmpty()) {
      val activeRoot = rootInActiveWindow
      if (activeRoot != null) {
        roots.add(activeRoot)
      }
    }
    return roots
  }

  fun injectGesture(gesture: GestureDescription, callback: GestureResultCallback? = null) {
    dispatchGesture(gesture, callback, /* handler= */ null)
  }

  companion object {
    private const val TAG = "AndroidEnvInputService"

    @Volatile private var instance: InputService? = null

    @com.google.errorprone.annotations.CanIgnoreReturnValue
    fun getInstance(): InputService {
      return instance
        ?: throw IllegalStateException(
          "InputService not connected. Enable it in Accessibility Settings."
        )
    }

    var activePackage: String = ""
      private set

    var activeActivity: String = ""
      private set
  }
}
