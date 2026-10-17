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
import android.graphics.Path
import android.view.accessibility.AccessibilityEvent
import android.view.accessibility.AccessibilityNodeInfo
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.Shadows.shadowOf
import org.robolectric.android.controller.ServiceController
import org.robolectric.shadows.ShadowAccessibilityService

@RunWith(AndroidJUnit4::class)
class InputServiceTest {

  private lateinit var serviceController: ServiceController<InputService>
  private lateinit var service: InputService
  private lateinit var shadowService: ShadowAccessibilityService

  @Before
  fun setUp() {
    serviceController = Robolectric.buildService(InputService::class.java)
    service = serviceController.create().get()
    shadowService = shadowOf(service)
  }

  @After
  fun tearDown() {
    serviceController.destroy()
    // Clean up singleton
    val field = InputService::class.java.getDeclaredField("instance")
    field.isAccessible = true
    field.set(null, null)

    // Clean up companion variables
    val activePackageField = InputService::class.java.getDeclaredField("activePackage")
    activePackageField.isAccessible = true
    activePackageField.set(null, "")

    val activeActivityField = InputService::class.java.getDeclaredField("activeActivity")
    activeActivityField.isAccessible = true
    activeActivityField.set(null, "")
  }

  @Test
  fun onCreate_setsSingletonInstance() {
    assertThat(InputService.getInstance()).isEqualTo(service)
  }

  @Test
  fun injectGesture_dispatchesGestureToSystem() {
    val path =
      Path().apply {
        moveTo(100f, 200f)
        lineTo(300f, 400f)
      }
    val stroke = GestureDescription.StrokeDescription(path, 0, 100)
    val gesture = GestureDescription.Builder().addStroke(stroke).build()

    service.injectGesture(gesture)

    val dispatched = shadowService.gesturesDispatched
    assertThat(dispatched).hasSize(1)
    val dispatchedGesture = dispatched[0].description()
    assertThat(dispatchedGesture.strokeCount).isEqualTo(1)

    val dispatchedStroke = dispatchedGesture.getStroke(0)
    assertThat(dispatchedStroke.duration).isEqualTo(100)
  }

  @Test
  fun getRootNode_returnsRootFromActiveWindow() {
    val rootNode =
      AccessibilityNodeInfo().apply {
        packageName = "com.test.package"
        className = "android.widget.FrameLayout"
      }

    // Direct setup using shadow
    shadowService.setRootInActiveWindow(rootNode)

    val root = service.getRootNode()
    assertThat(root).isNotNull()
    assertThat(root?.packageName).isEqualTo("com.test.package")
    assertThat(root?.className).isEqualTo("android.widget.FrameLayout")
  }

  @Test
  fun onAccessibilityEvent_windowStateChanged_updatesActivePackageAndActivity() {
    val event =
      AccessibilityEvent().apply {
        eventType = AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED
        packageName = "com.example.app"
        className = "com.example.app.MainActivity"
      }

    service.onAccessibilityEvent(event)

    assertThat(InputService.activePackage).isEqualTo("com.example.app")
    assertThat(InputService.activeActivity).isEqualTo("com.example.app.MainActivity")
  }

  @Test
  fun onServiceConnected_setsSingletonInstance() {
    val field = InputService::class.java.getDeclaredField("instance")
    field.isAccessible = true
    field.set(null, null)

    val method = InputService::class.java.getDeclaredMethod("onServiceConnected")
    method.isAccessible = true
    method.invoke(service)

    assertThat(InputService.getInstance()).isEqualTo(service)
  }

  @Test
  fun onInterrupt_doesNothing() {
    service.onInterrupt()
  }

  @Test(expected = IllegalStateException::class)
  @Suppress("CheckReturnValue")
  fun getInstance_notConnected_throwsException() {
    val field = InputService::class.java.getDeclaredField("instance")
    field.isAccessible = true
    field.set(null, null)

    InputService.getInstance()
  }

  @Test
  fun onAccessibilityEvent_whenTrackingEnabled_buffersEvent() {
    service.isEventTrackingEnabled = true
    val event =
      AccessibilityEvent().apply {
        eventType = AccessibilityEvent.TYPE_VIEW_CLICKED
        packageName = "com.test.app"
        className = "android.widget.Button"
        eventTime = 12345L
      }

    service.onAccessibilityEvent(event)

    val events = service.popEvents()
    assertThat(events).hasSize(1)
    assertThat(events[0].eventMap["event_type"]).contains("TYPE_VIEW_CLICKED")
    assertThat(events[0].eventMap["package_name"]).isEqualTo("com.test.app")
    assertThat(events[0].eventMap["class_name"]).isEqualTo("android.widget.Button")

    // Buffer cleared after popEvents
    assertThat(service.popEvents()).isEmpty()
  }

  @Test
  fun onAccessibilityEvent_whenTrackingDisabled_doesNotBufferEvent() {
    service.isEventTrackingEnabled = false
    val event =
      AccessibilityEvent().apply {
        eventType = AccessibilityEvent.TYPE_VIEW_CLICKED
        packageName = "com.test.app"
        className = "android.widget.Button"
        eventTime = 12345L
      }

    service.onAccessibilityEvent(event)

    val events = service.popEvents()
    assertThat(events).isEmpty()
  }

  @Test
  fun clearEvents_clearsBufferedEvents() {
    service.isEventTrackingEnabled = true
    val event =
      AccessibilityEvent().apply {
        eventType = AccessibilityEvent.TYPE_VIEW_CLICKED
        packageName = "com.test.app"
        className = "android.widget.Button"
      }
    service.onAccessibilityEvent(event)

    service.clearEvents()
    assertThat(service.popEvents()).isEmpty()
  }

  @Test
  fun systemGestureInjector_allMethods_whenBoundAndUnbound() {
    val injector = SystemGestureInjector()

    // 1. When bound
    assertThat(injector.getRootNode()).isNull()
    assertThat(injector.getActivePackage()).isEqualTo("")
    assertThat(injector.getActiveActivity()).isEqualTo("")
    assertThat(injector.performGlobalAction(1)).isTrue()
    try {
      val stroke =
        GestureDescription.StrokeDescription(
          android.graphics.Path().apply { lineTo(10f, 10f) },
          0L,
          100L,
        )
      val gesture = GestureDescription.Builder().addStroke(stroke).build()
      injector.injectGesture(gesture, null)
    } catch (e: Exception) {
      // Ignored if service.dispatchGesture fails in unit test environment
    }
    injector.setEventTrackingEnabled(true)
    val event =
      AccessibilityEvent().apply {
        eventType = AccessibilityEvent.TYPE_VIEW_CLICKED
        packageName = "com.test.app"
        className = "android.widget.Button"
      }
    service.onAccessibilityEvent(event)

    val events = injector.popEvents()
    assertThat(events).hasSize(1)

    injector.setEventTrackingEnabled(true)
    service.onAccessibilityEvent(event)
    injector.clearEvents()
    assertThat(injector.popEvents()).isEmpty()

    // 2. When unbound (test catch blocks)
    val field = InputService::class.java.getDeclaredField("instance")
    field.isAccessible = true
    field.set(null, null)

    assertThat(injector.popEvents()).isEmpty()
    injector.setEventTrackingEnabled(true)
    injector.clearEvents()
  }
}
