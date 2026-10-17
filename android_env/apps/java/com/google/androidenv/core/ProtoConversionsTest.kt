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

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.androidenv.proto.Action as ProtoAction
import com.androidenv.proto.ActionType as ProtoActionType
import com.androidenv.proto.DeviceSignal as ProtoDeviceSignal
import com.google.common.truth.Truth.assertThat
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

@RunWith(AndroidJUnit4::class)
@Config(manifest = Config.NONE)
class ProtoConversionsTest {

  @Test
  fun testProtoActionToCore_touchDown() {
    val protoAction =
      ProtoAction.newBuilder()
        .setActionType(ProtoActionType.ACTION_TYPE_TOUCH_DOWN)
        .setTouchPosition(com.androidenv.proto.Point.newBuilder().setX(0.5f).setY(0.8f))
        .setPointerId(3)
        .build()

    val coreAction: Action = with(ProtoConversions) { protoAction.toCore() }

    assertThat(coreAction.actionType).isEqualTo(ActionType.TOUCH_DOWN)
    val touchPosition = coreAction.touchPosition
    requireNotNull(touchPosition)
    assertThat(touchPosition[0]).isEqualTo(0.5f)
    assertThat(touchPosition[1]).isEqualTo(0.8f)
    assertThat(coreAction.pointerId).isEqualTo(3)
  }

  @Test
  fun testProtoActionToCore_keyEvent() {
    val protoAction =
      ProtoAction.newBuilder()
        .setActionType(ProtoActionType.ACTION_TYPE_KEY_EVENT)
        .setKeycode(42)
        .build()

    val coreAction: Action = with(ProtoConversions) { protoAction.toCore() }

    assertThat(coreAction.actionType).isEqualTo(ActionType.KEY_EVENT)
    assertThat(coreAction.keycode).isEqualTo(42)
    assertThat(coreAction.pointerId).isNull()
  }

  @Test
  fun testProtoActionToCore_setText() {
    val protoAction =
      ProtoAction.newBuilder()
        .setActionType(ProtoActionType.ACTION_TYPE_SET_TEXT)
        .setText("hello world")
        .build()

    val coreAction: Action = with(ProtoConversions) { protoAction.toCore() }

    assertThat(coreAction.actionType).isEqualTo(ActionType.SET_TEXT)
    assertThat(coreAction.text).isEqualTo("hello world")
  }

  @Test
  fun testProtoActionToCore_setSelection() {
    val protoAction =
      ProtoAction.newBuilder()
        .setActionType(ProtoActionType.ACTION_TYPE_SET_SELECTION)
        .setSelectionStart(2)
        .setSelectionEnd(5)
        .build()

    val coreAction: Action = with(ProtoConversions) { protoAction.toCore() }

    assertThat(coreAction.actionType).isEqualTo(ActionType.SET_SELECTION)
    assertThat(coreAction.selectionStart).isEqualTo(2)
    assertThat(coreAction.selectionEnd).isEqualTo(5)
  }

  @Test
  fun testProtoActionToCore_cutCopyPaste() {
    val cutAction = ProtoAction.newBuilder().setActionType(ProtoActionType.ACTION_TYPE_CUT).build()
    val copyAction =
      ProtoAction.newBuilder().setActionType(ProtoActionType.ACTION_TYPE_COPY).build()
    val pasteAction =
      ProtoAction.newBuilder().setActionType(ProtoActionType.ACTION_TYPE_PASTE).build()

    with(ProtoConversions) {
      assertThat(cutAction.toCore().actionType).isEqualTo(ActionType.CUT)
      assertThat(copyAction.toCore().actionType).isEqualTo(ActionType.COPY)
      assertThat(pasteAction.toCore().actionType).isEqualTo(ActionType.PASTE)
    }
  }

  @Test
  fun testProtoSignalToCore() {
    with(ProtoConversions) {
      assertThat(ProtoDeviceSignal.DEVICE_SIGNAL_SCREENSHOT.toCore())
        .isEqualTo(DeviceSignal.SCREENSHOT)
      assertThat(ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_PACKAGE.toCore())
        .isEqualTo(DeviceSignal.ACTIVE_PACKAGE)
      assertThat(ProtoDeviceSignal.DEVICE_SIGNAL_BATTERY_POWER.toCore())
        .isEqualTo(DeviceSignal.BATTERY_POWER)
    }
  }

  @Test
  fun testCoreSignalToProto() {
    with(ProtoConversions) {
      assertThat(DeviceSignal.SCREENSHOT.toProto())
        .isEqualTo(ProtoDeviceSignal.DEVICE_SIGNAL_SCREENSHOT)
      assertThat(DeviceSignal.ACTIVE_PACKAGE.toProto())
        .isEqualTo(ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_PACKAGE)
      assertThat(DeviceSignal.BATTERY_POWER.toProto())
        .isEqualTo(ProtoDeviceSignal.DEVICE_SIGNAL_BATTERY_POWER)
    }
  }

  @Test
  fun testCoreDeviceStateToProto_packsSignalsCorrectly() {
    val dummyBitmap =
      android.graphics.Bitmap.createBitmap(1, 1, android.graphics.Bitmap.Config.ARGB_8888)
    val screenshotSignal = StreamedSignal(value = dummyBitmap, timestampUs = 1000L, sequenceId = 1L)
    val activePkgSignal =
      StreamedSignal(value = "com.android.chrome", timestampUs = 2000L, sequenceId = 2L)

    val coreState =
      DeviceState(
        screenshot = screenshotSignal,
        accessibilityRoot = StreamedSignal(null, 0L, 0L),
        accessibilityEvents = StreamedSignal(null, 0L, 0L),
        activePackage = activePkgSignal,
        activeActivity = StreamedSignal(null, 0L, 0L),
        systemLogs = StreamedSignal(null, 0L, 0L),
        runningProcesses = StreamedSignal(null, 0L, 0L),
        deviceSettings = StreamedSignal(null, 0L, 0L),
        accelerometer = StreamedSignal(null, 0L, 0L),
        gyroscope = StreamedSignal(null, 0L, 0L),
        magnetometer = StreamedSignal(null, 0L, 0L),
        barometer = StreamedSignal(null, 0L, 0L),
        ambientTemp = StreamedSignal(null, 0L, 0L),
        lightLevel = StreamedSignal(null, 0L, 0L),
        proximity = StreamedSignal(null, 0L, 0L),
        locationGps = StreamedSignal(null, 0L, 0L),
        heartRate = StreamedSignal(null, 0L, 0L),
        audioOutput = StreamedSignal(null, 0L, 0L),
        snapshotTimestampUs = 9999L,
      )

    val protoState = with(ProtoConversions) { coreState.toProto() }

    assertThat(protoState.snapshotTimestampUs).isEqualTo(9999L)
    assertThat(protoState.signalsCount).isEqualTo(3)

    // Verify device settings signal (always present in WIP)
    val protoSettings =
      protoState.signalsList.find { it.type == ProtoDeviceSignal.DEVICE_SIGNAL_DEVICE_SETTINGS }
    assertThat(protoSettings).isNotNull()
    assertThat(protoSettings!!.deviceSettings.entriesMap).containsKey("device_time_ms")

    // Verify screenshot signal with embedded screenshot value over WebSocket
    val protoScreenshot =
      protoState.signalsList.find { it.type == ProtoDeviceSignal.DEVICE_SIGNAL_SCREENSHOT }
    assertThat(protoScreenshot).isNotNull()
    assertThat(protoScreenshot!!.metadata.timestampUs).isEqualTo(1000L)
    assertThat(protoScreenshot.metadata.sequenceId).isEqualTo(1L)
    assertThat(protoScreenshot.hasScreenshot()).isTrue()

    // Verify active package signal (value present)
    val protoPkg =
      protoState.signalsList.find { it.type == ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_PACKAGE }
    assertThat(protoPkg).isNotNull()
    assertThat(protoPkg!!.metadata.timestampUs).isEqualTo(2000L)
    assertThat(protoPkg.metadata.sequenceId).isEqualTo(2L)
    assertThat(protoPkg.activePackage).isEqualTo("com.android.chrome")
  }

  @Test
  fun testCoreDeviceStateToProto_packsAccessibilitySignals() {
    val mockNode =
      android.view.accessibility.AccessibilityNodeInfo.obtain().apply {
        className = "android.widget.Button"
        text = "Click Me"
      }
    val event =
      com.google.androidenv.accessibilityforwarder.EventRequest.newBuilder()
        .putEvent("event_type", "TYPE_VIEW_CLICKED")
        .build()

    val coreState =
      DeviceState(
        screenshot = StreamedSignal.empty(),
        accessibilityRoot = StreamedSignal(value = mockNode, timestampUs = 3000L, sequenceId = 3L),
        accessibilityEvents =
          StreamedSignal(value = listOf(event), timestampUs = 4000L, sequenceId = 4L),
        activePackage = StreamedSignal.empty(),
        activeActivity = StreamedSignal.empty(),
        systemLogs = StreamedSignal.empty(),
        runningProcesses = StreamedSignal.empty(),
        deviceSettings = StreamedSignal.empty(),
        accelerometer = StreamedSignal.empty(),
        gyroscope = StreamedSignal.empty(),
        magnetometer = StreamedSignal.empty(),
        barometer = StreamedSignal.empty(),
        ambientTemp = StreamedSignal.empty(),
        lightLevel = StreamedSignal.empty(),
        proximity = StreamedSignal.empty(),
        locationGps = StreamedSignal.empty(),
        heartRate = StreamedSignal.empty(),
        audioOutput = StreamedSignal.empty(),
        snapshotTimestampUs = 9999L,
      )

    val protoState = with(ProtoConversions) { coreState.toProto() }

    val protoTree =
      protoState.signalsList.find { it.type == ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_TREE }
    assertThat(protoTree).isNotNull()
    assertThat(protoTree!!.hasAccessibilityForest()).isTrue()
    assertThat(protoTree.accessibilityForest.windowsCount).isEqualTo(1)

    val protoEvents =
      protoState.signalsList.find {
        it.type == ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS
      }
    assertThat(protoEvents).isNotNull()
    assertThat(protoEvents!!.hasAccessibilityEvents()).isTrue()
    assertThat(protoEvents.accessibilityEvents.eventsCount).isEqualTo(1)
  }

  @Test
  fun testCoreDeviceStateToProto_withScreenShareServiceSettings() {
    val controller =
      org.robolectric.Robolectric.buildService(ScreenShareService::class.java).create()
    val service = controller.get()
    service.activeVideoMime = android.media.MediaFormat.MIMETYPE_VIDEO_HEVC
    service.activeVideoWidth = 1920
    service.activeVideoHeight = 1080

    val coreState =
      DeviceState(
        screenshot = StreamedSignal.empty(),
        accessibilityRoot = StreamedSignal.empty(),
        accessibilityEvents = StreamedSignal.empty(),
        activePackage = StreamedSignal.empty(),
        activeActivity = StreamedSignal.empty(),
        systemLogs = StreamedSignal.empty(),
        runningProcesses = StreamedSignal.empty(),
        deviceSettings = StreamedSignal.empty(),
        accelerometer = StreamedSignal.empty(),
        gyroscope = StreamedSignal.empty(),
        magnetometer = StreamedSignal.empty(),
        barometer = StreamedSignal.empty(),
        ambientTemp = StreamedSignal.empty(),
        lightLevel = StreamedSignal.empty(),
        proximity = StreamedSignal.empty(),
        locationGps = StreamedSignal.empty(),
        heartRate = StreamedSignal.empty(),
        audioOutput = StreamedSignal.empty(),
        snapshotTimestampUs = 9999L,
      )

    val protoState = with(ProtoConversions) { coreState.toProto() }

    val protoSettings =
      protoState.signalsList.find { it.type == ProtoDeviceSignal.DEVICE_SIGNAL_DEVICE_SETTINGS }
    assertThat(protoSettings).isNotNull()
    val entries = protoSettings!!.deviceSettings.entriesMap
    assertThat(entries["video_codec"]).isEqualTo("h265")
    assertThat(entries["video_width"]).isEqualTo("1920")
    assertThat(entries["video_height"]).isEqualTo("1080")
  }

  @Test
  fun testCoreDeviceStateToProto_packsBatteryPowerSignal() {
    val metrics =
      BatteryPowerMetrics(
        levelPercent = 90,
        currentNowUa = 300_000L,
        voltageMv = 4100,
        powerMw = 1230.0,
        temperatureCelsius = 27.0f,
        status = "CHARGING",
        pluggedSource = "USB",
        chargeCounterUah = 2_800_000L,
        thermalStatus = 1,
        energyCounterNwh = 12_000_000_000L,
      )

    val coreState =
      DeviceState(
        screenshot = StreamedSignal.empty(),
        accessibilityRoot = StreamedSignal.empty(),
        accessibilityEvents = StreamedSignal.empty(),
        activePackage = StreamedSignal.empty(),
        activeActivity = StreamedSignal.empty(),
        systemLogs = StreamedSignal.empty(),
        runningProcesses = StreamedSignal.empty(),
        deviceSettings = StreamedSignal.empty(),
        accelerometer = StreamedSignal.empty(),
        gyroscope = StreamedSignal.empty(),
        magnetometer = StreamedSignal.empty(),
        barometer = StreamedSignal.empty(),
        ambientTemp = StreamedSignal.empty(),
        lightLevel = StreamedSignal.empty(),
        proximity = StreamedSignal.empty(),
        locationGps = StreamedSignal.empty(),
        heartRate = StreamedSignal.empty(),
        audioOutput = StreamedSignal.empty(),
        batteryPower = StreamedSignal(value = metrics, timestampUs = 5000L, sequenceId = 5L),
        snapshotTimestampUs = 9999L,
      )

    val protoState = with(ProtoConversions) { coreState.toProto() }

    val protoBattery =
      protoState.signalsList.find { it.type == ProtoDeviceSignal.DEVICE_SIGNAL_BATTERY_POWER }
    assertThat(protoBattery).isNotNull()
    assertThat(protoBattery!!.metadata.timestampUs).isEqualTo(5000L)
    assertThat(protoBattery.metadata.sequenceId).isEqualTo(5L)
    assertThat(protoBattery.hasBatteryPower()).isTrue()
    assertThat(protoBattery.batteryPower.levelPercent).isEqualTo(90)
    assertThat(protoBattery.batteryPower.energyCounterNwh).isEqualTo(12_000_000_000L)
  }
}

