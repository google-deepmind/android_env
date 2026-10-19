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

import android.media.MediaFormat
import android.view.accessibility.AccessibilityNodeInfo
import com.androidenv.proto.Action as ProtoAction
import com.androidenv.proto.ActionType as ProtoActionType
import com.androidenv.proto.AudioFrame as ProtoAudioFrame
import com.androidenv.proto.DeviceSignal as ProtoDeviceSignal
import com.androidenv.proto.DeviceState as ProtoDeviceState
import com.androidenv.proto.FloatArray as ProtoFloatArray
import com.androidenv.proto.GpsCoordinates as ProtoGpsCoordinates
import com.androidenv.proto.StreamedSignalMetadata as ProtoMetadata
import com.androidenv.proto.StringList as ProtoStringList
import com.androidenv.proto.StringMap as ProtoStringMap

/** Utility functions to convert between Core model classes and Proto classes. */
object ProtoConversions {

  fun ProtoAction.toCore(): Action {
    val coreType =
      when (actionType) {
        ProtoActionType.ACTION_TYPE_TOUCH_DOWN -> ActionType.TOUCH_DOWN
        ProtoActionType.ACTION_TYPE_TOUCH_UP -> ActionType.TOUCH_UP
        ProtoActionType.ACTION_TYPE_TOUCH_MOVE -> ActionType.TOUCH_MOVE
        ProtoActionType.ACTION_TYPE_KEY_EVENT -> ActionType.KEY_EVENT
        ProtoActionType.ACTION_TYPE_SET_TEXT -> ActionType.SET_TEXT
        ProtoActionType.ACTION_TYPE_SET_SELECTION -> ActionType.SET_SELECTION
        ProtoActionType.ACTION_TYPE_CUT -> ActionType.CUT
        ProtoActionType.ACTION_TYPE_COPY -> ActionType.COPY
        ProtoActionType.ACTION_TYPE_PASTE -> ActionType.PASTE
        else -> ActionType.KEY_EVENT // Default fallback
      }
    val pos =
      if (hasTouchPosition()) {
        listOf(touchPosition.x, touchPosition.y)
      } else {
        null
      }
    val key = if (hasKeycode()) keycode else null
    val pointer = if (hasPointerId()) pointerId else null
    val textVal = if (hasText()) text else null
    val selStart = if (hasSelectionStart()) selectionStart else null
    val selEnd = if (hasSelectionEnd()) selectionEnd else null
    return Action(coreType, pos, key, pointer, textVal, selStart, selEnd)
  }

  fun ProtoDeviceSignal.toCore(): DeviceSignal? {
    return when (this) {
      ProtoDeviceSignal.DEVICE_SIGNAL_SCREENSHOT -> DeviceSignal.SCREENSHOT
      ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_TREE -> DeviceSignal.ACCESSIBILITY_TREE
      ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS -> DeviceSignal.ACCESSIBILITY_EVENTS
      ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_PACKAGE -> DeviceSignal.ACTIVE_PACKAGE
      ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_ACTIVITY -> DeviceSignal.ACTIVE_ACTIVITY
      ProtoDeviceSignal.DEVICE_SIGNAL_SYSTEM_LOGS -> DeviceSignal.SYSTEM_LOGS
      ProtoDeviceSignal.DEVICE_SIGNAL_RUNNING_PROCESSES -> DeviceSignal.RUNNING_PROCESSES
      ProtoDeviceSignal.DEVICE_SIGNAL_DEVICE_SETTINGS -> DeviceSignal.DEVICE_SETTINGS
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_ACCELEROMETER -> DeviceSignal.SENSOR_ACCELEROMETER
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_GYROSCOPE -> DeviceSignal.SENSOR_GYROSCOPE
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_MAGNETOMETER -> DeviceSignal.SENSOR_MAGNETOMETER
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_BAROMETER -> DeviceSignal.SENSOR_BAROMETER
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_AMBIENT_TEMP -> DeviceSignal.SENSOR_AMBIENT_TEMP
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_LIGHT -> DeviceSignal.SENSOR_LIGHT
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_PROXIMITY -> DeviceSignal.SENSOR_PROXIMITY
      ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_HEART_RATE -> DeviceSignal.SENSOR_HEART_RATE
      ProtoDeviceSignal.DEVICE_SIGNAL_LOCATION_GPS -> DeviceSignal.LOCATION_GPS
      ProtoDeviceSignal.DEVICE_SIGNAL_AUDIO_OUTPUT -> DeviceSignal.AUDIO_OUTPUT
      ProtoDeviceSignal.DEVICE_SIGNAL_BATTERY_POWER -> DeviceSignal.BATTERY_POWER
      else -> null
    }
  }

  fun DeviceSignal.toProto(): ProtoDeviceSignal {
    return when (this) {
      DeviceSignal.SCREENSHOT -> ProtoDeviceSignal.DEVICE_SIGNAL_SCREENSHOT
      DeviceSignal.ACCESSIBILITY_TREE -> ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_TREE
      DeviceSignal.ACCESSIBILITY_EVENTS -> ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS
      DeviceSignal.ACTIVE_PACKAGE -> ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_PACKAGE
      DeviceSignal.ACTIVE_ACTIVITY -> ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_ACTIVITY
      DeviceSignal.SYSTEM_LOGS -> ProtoDeviceSignal.DEVICE_SIGNAL_SYSTEM_LOGS
      DeviceSignal.RUNNING_PROCESSES -> ProtoDeviceSignal.DEVICE_SIGNAL_RUNNING_PROCESSES
      DeviceSignal.DEVICE_SETTINGS -> ProtoDeviceSignal.DEVICE_SIGNAL_DEVICE_SETTINGS
      DeviceSignal.SENSOR_ACCELEROMETER -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_ACCELEROMETER
      DeviceSignal.SENSOR_GYROSCOPE -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_GYROSCOPE
      DeviceSignal.SENSOR_MAGNETOMETER -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_MAGNETOMETER
      DeviceSignal.SENSOR_BAROMETER -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_BAROMETER
      DeviceSignal.SENSOR_AMBIENT_TEMP -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_AMBIENT_TEMP
      DeviceSignal.SENSOR_LIGHT -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_LIGHT
      DeviceSignal.SENSOR_PROXIMITY -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_PROXIMITY
      DeviceSignal.SENSOR_HEART_RATE -> ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_HEART_RATE
      DeviceSignal.LOCATION_GPS -> ProtoDeviceSignal.DEVICE_SIGNAL_LOCATION_GPS
      DeviceSignal.AUDIO_OUTPUT -> ProtoDeviceSignal.DEVICE_SIGNAL_AUDIO_OUTPUT
      DeviceSignal.BATTERY_POWER -> ProtoDeviceSignal.DEVICE_SIGNAL_BATTERY_POWER
    }
  }

  fun DeviceState.toProto(): ProtoDeviceState {
    val builder =
      ProtoDeviceState.newBuilder()
        .setSnapshotTimestampUs(snapshotTimestampUs)
        .setOrientation(orientation)

    fun <T> addSignalIfPresent(
      signal: StreamedSignal<T>,
      signalType: ProtoDeviceSignal,
      valueBuilder: (T, com.androidenv.proto.StreamedSignal.Builder) -> Unit,
    ) {
      val rawValue = signal.value
      if (rawValue != null) {
        val signalBuilder =
          com.androidenv.proto.StreamedSignal.newBuilder()
            .setType(signalType)
            .setMetadata(
              ProtoMetadata.newBuilder()
                .setTimestampUs(signal.timestampUs)
                .setSequenceId(signal.sequenceId)
                .build()
            )
        valueBuilder(rawValue, signalBuilder)
        builder.addSignals(signalBuilder.build())
      }
    }

    // 1. Screenshot (Compressed JPEG bytes included directly in StreamedSignal over WebSocket)
    val rawScreenshot = screenshot.value
    if (rawScreenshot != null) {
      val stream = java.io.ByteArrayOutputStream()
      rawScreenshot.compress(android.graphics.Bitmap.CompressFormat.JPEG, 80, stream)
      val jpegBytes = stream.toByteArray()

      val screenshotVal =
        com.androidenv.proto.ScreenshotValue.newBuilder()
          .setEncodedBytes(com.google.protobuf.ByteString.copyFrom(jpegBytes))
          .build()

      val signalBuilder =
        com.androidenv.proto.StreamedSignal.newBuilder()
          .setType(ProtoDeviceSignal.DEVICE_SIGNAL_SCREENSHOT)
          .setMetadata(
            ProtoMetadata.newBuilder()
              .setTimestampUs(screenshot.timestampUs)
              .setSequenceId(screenshot.sequenceId)
              .build()
          )
          .setScreenshot(screenshotVal)
      builder.addSignals(signalBuilder.build())
    }

    // 2. Accessibility Tree
    addSignalIfPresent(accessibilityRoot, ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_TREE) {
      value,
      signalBuilder ->
      val treeProto =
        com.google.androidenv.accessibilityforwarder.AndroidAccessibilityTree.newBuilder()
          .addNodes(value.toA11yNodeInfoProto())
          .build()
      val windowInfo =
        com.google.androidenv.accessibilityforwarder.AndroidAccessibilityWindowInfo.newBuilder()
          .setTree(treeProto)
          .build()
      signalBuilder.setAccessibilityForest(
        com.google.androidenv.accessibilityforwarder.AndroidAccessibilityForest.newBuilder()
          .addWindows(windowInfo)
          .build()
      )
    }

    // 3. Accessibility Events
    addSignalIfPresent(accessibilityEvents, ProtoDeviceSignal.DEVICE_SIGNAL_ACCESSIBILITY_EVENTS) {
      value,
      signalBuilder ->
      signalBuilder.setAccessibilityEvents(
        com.google.androidenv.accessibilityforwarder.EventRequestList.newBuilder()
          .addAllEvents(value)
          .build()
      )
    }

    // 3. Active Package
    addSignalIfPresent(activePackage, ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_PACKAGE) {
      value,
      signalBuilder ->
      signalBuilder.setActivePackage(value)
    }

    // 4. Active Activity
    addSignalIfPresent(activeActivity, ProtoDeviceSignal.DEVICE_SIGNAL_ACTIVE_ACTIVITY) {
      value,
      signalBuilder ->
      signalBuilder.setActiveActivity(value)
    }

    // 5. System Logs
    addSignalIfPresent(systemLogs, ProtoDeviceSignal.DEVICE_SIGNAL_SYSTEM_LOGS) {
      value,
      signalBuilder ->
      signalBuilder.setSystemLogs(ProtoStringList.newBuilder().addAllValues(value).build())
    }

    // 6. Running Processes
    addSignalIfPresent(runningProcesses, ProtoDeviceSignal.DEVICE_SIGNAL_RUNNING_PROCESSES) {
      value,
      signalBuilder ->
      signalBuilder.setRunningProcesses(ProtoStringList.newBuilder().addAllValues(value).build())
    }

    // 7. Device Settings
    val settingsMap = deviceSettings.value?.toMutableMap() ?: mutableMapOf()
    settingsMap["device_time_ms"] = System.currentTimeMillis().toString()
    val screenService =
      try {
        ScreenShareService.getInstance()
      } catch (e: IllegalStateException) {
        null
      }
    if (screenService != null) {
      val mime = screenService.activeVideoMime
      val codec =
        when (mime) {
          MediaFormat.MIMETYPE_VIDEO_HEVC -> "h265"
          "image/jpeg" -> "mjpeg"
          else -> "h264"
        }
      settingsMap["video_codec"] = codec
      val width = if (screenService.activeVideoWidth > 0) screenService.activeVideoWidth else 1080
      val height =
        if (screenService.activeVideoHeight > 0) screenService.activeVideoHeight else 1920
      settingsMap["video_width"] = width.toString()
      settingsMap["video_height"] = height.toString()
    }
    val signalBuilder =
      com.androidenv.proto.StreamedSignal.newBuilder()
        .setType(ProtoDeviceSignal.DEVICE_SIGNAL_DEVICE_SETTINGS)
        .setMetadata(
          ProtoMetadata.newBuilder()
            .setTimestampUs(
              if (deviceSettings.timestampUs > 0) deviceSettings.timestampUs
              else snapshotTimestampUs
            )
            .setSequenceId(deviceSettings.sequenceId)
            .build()
        )
        .setDeviceSettings(ProtoStringMap.newBuilder().putAllEntries(settingsMap).build())
    builder.addSignals(signalBuilder.build())

    // Sensors
    addSignalIfPresent(accelerometer, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_ACCELEROMETER) {
      value,
      signalBuilder ->
      signalBuilder.setAccelerometer(ProtoFloatArray.newBuilder().addAllValues(value).build())
    }
    addSignalIfPresent(gyroscope, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_GYROSCOPE) {
      value,
      signalBuilder ->
      signalBuilder.setGyroscope(ProtoFloatArray.newBuilder().addAllValues(value).build())
    }
    addSignalIfPresent(magnetometer, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_MAGNETOMETER) {
      value,
      signalBuilder ->
      signalBuilder.setMagnetometer(ProtoFloatArray.newBuilder().addAllValues(value).build())
    }
    addSignalIfPresent(barometer, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_BAROMETER) {
      value,
      signalBuilder ->
      signalBuilder.setBarometer(value)
    }
    addSignalIfPresent(ambientTemp, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_AMBIENT_TEMP) {
      value,
      signalBuilder ->
      signalBuilder.setAmbientTemp(value)
    }
    addSignalIfPresent(lightLevel, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_LIGHT) {
      value,
      signalBuilder ->
      signalBuilder.setLightLevel(value)
    }
    addSignalIfPresent(proximity, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_PROXIMITY) {
      value,
      signalBuilder ->
      signalBuilder.setProximity(value)
    }

    addSignalIfPresent(locationGps, ProtoDeviceSignal.DEVICE_SIGNAL_LOCATION_GPS) {
      value,
      signalBuilder ->
      signalBuilder.setLocationGps(
        ProtoGpsCoordinates.newBuilder()
          .setLatitude(value.latitude)
          .setLongitude(value.longitude)
          .setAltitude(value.altitude)
          .build()
      )
    }

    addSignalIfPresent(heartRate, ProtoDeviceSignal.DEVICE_SIGNAL_SENSOR_HEART_RATE) {
      value,
      signalBuilder ->
      signalBuilder.setHeartRate(value)
    }
    addSignalIfPresent(audioOutput, ProtoDeviceSignal.DEVICE_SIGNAL_AUDIO_OUTPUT) {
      value,
      signalBuilder ->
      val audioBuilder =
        ProtoAudioFrame.newBuilder()
          .setRawBytes(com.google.protobuf.ByteString.copyFrom(value.rawBytes))
          .setSampleRateHz(value.sampleRateHz)
          .setChannelCount(value.channelCount)
      value.sampleFormat?.let { audioBuilder.setSampleFormat(it) }
      signalBuilder.setAudioOutput(audioBuilder.build())
    }
    addSignalIfPresent(batteryPower, ProtoDeviceSignal.DEVICE_SIGNAL_BATTERY_POWER) {
      value,
      signalBuilder ->
      signalBuilder.setBatteryPower(
        com.androidenv.proto.BatteryPowerMetrics.newBuilder()
          .setLevelPercent(value.levelPercent)
          .setCurrentNowUa(value.currentNowUa)
          .setVoltageMv(value.voltageMv)
          .setPowerMw(value.powerMw)
          .setTemperatureCelsius(value.temperatureCelsius)
          .setStatus(value.status)
          .setPluggedSource(value.pluggedSource)
          .setChargeCounterUah(value.chargeCounterUah)
          .setThermalStatus(value.thermalStatus)
          .setEnergyCounterNwh(value.energyCounterNwh)
          .build()
      )
    }

    return builder.build()
  }

  @Suppress("DEPRECATION")
  private fun AccessibilityNodeInfo.toA11yNodeInfoProto():
    com.google.androidenv.accessibilityforwarder.AndroidAccessibilityNodeInfo {
    val builder =
      com.google.androidenv.accessibilityforwarder.AndroidAccessibilityNodeInfo.newBuilder()
    className?.let { builder.className = it.toString() }
    text?.let { builder.text = it.toString() }
    contentDescription?.let { builder.contentDescription = it.toString() }
    viewIdResourceName?.let { builder.viewIdResourceName = it }

    val rect = android.graphics.Rect()
    getBoundsInScreen(rect)
    builder.boundsInScreen =
      com.google.androidenv.accessibilityforwarder.ProtoRect.newBuilder()
        .setLeft(rect.left)
        .setTop(rect.top)
        .setRight(rect.right)
        .setBottom(rect.bottom)
        .build()

    builder.isClickable = isClickable
    builder.isEnabled = isEnabled
    builder.isFocusable = isFocusable
    builder.isFocused = isFocused
    return builder.build()
  }
}
