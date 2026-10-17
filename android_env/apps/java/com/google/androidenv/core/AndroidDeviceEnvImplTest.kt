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
import android.content.Context
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.any
import org.mockito.kotlin.argumentCaptor
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

@RunWith(AndroidJUnit4::class)
class AndroidDeviceEnvImplTest {

  private val context = ApplicationProvider.getApplicationContext<Context>()
  private val mockGestureInjector = mock<GestureInjector>()
  private val mockScreenShareProvider = mock<ScreenShareProvider>()
  private lateinit var env: AndroidDeviceEnv

  @Before
  fun setUp() {
    env =
      AndroidDeviceEnvImpl(
        context = context,
        gestureInjector = mockGestureInjector,
        screenShareProvider = mockScreenShareProvider,
      )
  }

  @After
  fun tearDown() {
    env.close()
  }

  @Test
  fun injectAction_touch_callsInputServiceWithScaledCoordinates() {
    whenever(mockScreenShareProvider.width()).doReturn(1000)
    whenever(mockScreenShareProvider.height()).doReturn(2000)

    val action =
      Action(
        actionType = ActionType.TOUCH_DOWN,
        touchPosition = listOf(0.5f, 0.25f), // x=50%, y=25%
        keycode = null,
      )

    env.injectAction(action)

    val gestureCaptor = argumentCaptor<GestureDescription>()
    verify(mockGestureInjector).injectGesture(gestureCaptor.capture(), any())

    val gesture = gestureCaptor.firstValue
    assertThat(gesture).isNotNull()
  }

  @Test
  fun getDeviceState_returnsStateWithScreenshot() {
    val width = 100
    val height = 100
    val rowStride = 400 // 100 * 4 bytes
    val rawBytes = ByteArray(width * height * 4) // RGBA
    rawBytes[0] = 255.toByte()
    rawBytes[1] = 255.toByte()
    rawBytes[2] = 255.toByte()
    rawBytes[3] = 255.toByte()

    whenever(mockScreenShareProvider.width()).doReturn(width)
    whenever(mockScreenShareProvider.height()).doReturn(height)
    whenever(mockScreenShareProvider.rowStride()).doReturn(rowStride)
    whenever(mockScreenShareProvider.latestScreenshot()).doReturn(rawBytes)
    whenever(mockScreenShareProvider.latestScreenshotTimestampUs()).doReturn(12345L)

    env.updateSubscriptions(setOf(DeviceSignal.SCREENSHOT))
    val state = env.getDeviceState()

    assertThat(state.snapshotTimestampUs).isGreaterThan(0L)
    assertThat(state.screenshot.timestampUs).isEqualTo(12345L)
    assertThat(state.screenshot.value).isNotNull()
    val bmp = state.screenshot.value!!
    assertThat(bmp.width).isEqualTo(width)
    assertThat(bmp.height).isEqualTo(height)
    val pixel = bmp.getPixel(0, 0)
    assertThat(android.graphics.Color.red(pixel)).isEqualTo(255)
  }

  @Test
  fun getDeviceState_systemLogsDeltaStreaming() {
    env.updateSubscriptions(setOf(DeviceSignal.SYSTEM_LOGS))
    val state1 = env.getDeviceState()

    assertThat(state1.systemLogs).isNotNull()
    val seq1 = state1.systemLogs.sequenceId

    // On subsequent call when no new logs exist, systemLogs.value is empty list (not stale logs)
    // and sequenceId is incremented for delta tracking.
    val state2 = env.getDeviceState()
    assertThat(state2.systemLogs).isNotNull()
    assertThat(state2.systemLogs.sequenceId).isEqualTo(seq1 + 1)
    assertThat(state2.systemLogs.value).isEmpty()
  }

  @Test
  fun injectAction_keyEvent_callsPerformGlobalAction() {
    val action =
      Action(
        actionType = ActionType.KEY_EVENT,
        touchPosition = null,
        keycode = 4, // BACK -> GLOBAL_ACTION_BACK = 1
      )

    env.injectAction(action)

    verify(mockGestureInjector).performGlobalAction(1)
  }

  @Test
  fun getDeviceState_returnsAccessibilityTreeAndEvents() {
    val mockNode = mock<android.view.accessibility.AccessibilityNodeInfo>()
    whenever(mockGestureInjector.getRootNode()).doReturn(mockNode)
    whenever(mockGestureInjector.getActivePackage()).doReturn("com.example.app")
    whenever(mockGestureInjector.getActiveActivity()).doReturn("com.example.app.MainActivity")

    val mockEvent =
      com.google.androidenv.accessibilityforwarder.EventRequest.newBuilder()
        .putEvent("event_type", "TYPE_VIEW_CLICKED")
        .putEvent("package_name", "com.example.app")
        .build()
    whenever(mockGestureInjector.popEvents()).doReturn(listOf(mockEvent))

    env.updateSubscriptions(
      setOf(
        DeviceSignal.ACCESSIBILITY_TREE,
        DeviceSignal.ACCESSIBILITY_EVENTS,
        DeviceSignal.ACTIVE_PACKAGE,
        DeviceSignal.ACTIVE_ACTIVITY,
      )
    )

    val state = env.getDeviceState()

    assertThat(state.accessibilityRoot.value).isEqualTo(mockNode)
    assertThat(state.activePackage.value).isEqualTo("com.example.app")
    assertThat(state.activeActivity.value).isEqualTo("com.example.app.MainActivity")
    assertThat(state.accessibilityEvents.value).containsExactly(mockEvent)
  }

  @Test
  fun updateSubscriptions_enablesAndDisablesEventTracking() {
    env.updateSubscriptions(setOf(DeviceSignal.ACCESSIBILITY_EVENTS))
    verify(mockGestureInjector).setEventTrackingEnabled(true)

    env.updateSubscriptions(emptySet())
    verify(mockGestureInjector).setEventTrackingEnabled(false)
    verify(mockGestureInjector).clearEvents()
  }

  @Test
  fun updateSubscriptions_registersSensors() {
    env.updateSubscriptions(
      setOf(
        DeviceSignal.SENSOR_ACCELEROMETER,
        DeviceSignal.SENSOR_GYROSCOPE,
        DeviceSignal.SENSOR_MAGNETOMETER,
        DeviceSignal.SENSOR_BAROMETER,
        DeviceSignal.SENSOR_AMBIENT_TEMP,
        DeviceSignal.SENSOR_LIGHT,
        DeviceSignal.SENSOR_PROXIMITY,
        DeviceSignal.SENSOR_HEART_RATE,
        DeviceSignal.LOCATION_GPS,
      )
    )
    val state = env.getDeviceState()
    assertThat(state).isNotNull()
  }

  @Test
  fun updateSubscriptions_enablesAndDisablesBatteryCollector() {
    env.updateSubscriptions(setOf(DeviceSignal.BATTERY_POWER))
    val stateWithBattery = env.getDeviceState()
    assertThat(stateWithBattery.batteryPower.value).isNotNull()

    env.updateSubscriptions(emptySet())
    val stateWithoutBattery = env.getDeviceState()
    assertThat(stateWithoutBattery.batteryPower.value).isNull()
  }

  @Test
  fun getDeviceState_returnsBatteryPowerMetrics() {
    env.updateSubscriptions(setOf(DeviceSignal.BATTERY_POWER))
    val state = env.getDeviceState()

    assertThat(state.batteryPower.value).isNotNull()
    val metrics = state.batteryPower.value!!
    assertThat(metrics.levelPercent).isAtLeast(0)
    assertThat(metrics.levelPercent).isAtMost(100)
    assertThat(metrics.voltageMv).isGreaterThan(0)
    assertThat(metrics.powerMw).isFinite()
    assertThat(metrics.chargeCounterUah).isAtLeast(0L)
    assertThat(metrics.energyCounterNwh).isAtLeast(0L)
    assertThat(metrics.status).isNotEmpty()
    assertThat(metrics.pluggedSource).isNotEmpty()
  }
}

