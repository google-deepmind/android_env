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

import android.graphics.Bitmap
import android.view.accessibility.AccessibilityNodeInfo

/** GPS coordinates. */
data class GpsCoordinates(val latitude: Double, val longitude: Double, val altitude: Double)

/** Represents a single audio frame. */
data class AudioFrame(
  val rawBytes: ByteArray,
  val sampleRateHz: Int,
  val channelCount: Int,
  val sampleFormat: String? = null,
) {
  override fun equals(other: Any?): Boolean {
    if (javaClass != other?.javaClass) return false

    other as AudioFrame

    if (!rawBytes.contentEquals(other.rawBytes)) return false
    if (sampleRateHz != other.sampleRateHz) return false
    if (channelCount != other.channelCount) return false
    if (sampleFormat != other.sampleFormat) return false

    return true
  }

  override fun hashCode(): Int {
    var result = rawBytes.contentHashCode()
    result = 31 * result + sampleRateHz
    result = 31 * result + channelCount
    result = 31 * result + (sampleFormat?.hashCode() ?: 0)
    return result
  }
}

/** Telemetry metrics for device battery state, current draw, voltage, and calculated power. */
data class BatteryPowerMetrics(
  val levelPercent: Int,
  val currentNowUa: Long,
  val voltageMv: Int,
  val powerMw: Double,
  val temperatureCelsius: Float,
  val status: String,
  val pluggedSource: String,
  val chargeCounterUah: Long,
  val thermalStatus: Int,
  val energyCounterNwh: Long = 0L,
)

/** Represents the complete, raw state of the Android device at a point in time. */
data class DeviceState(
  val screenshot: StreamedSignal<Bitmap>,
  val accessibilityRoot: StreamedSignal<AccessibilityNodeInfo>,
  val accessibilityEvents:
    StreamedSignal<List<com.google.androidenv.accessibilityforwarder.EventRequest>> =
    StreamedSignal.empty(),
  val activePackage: StreamedSignal<String>,
  val activeActivity: StreamedSignal<String>,
  val systemLogs: StreamedSignal<List<String>>,
  val runningProcesses: StreamedSignal<List<String>>,
  val deviceSettings: StreamedSignal<Map<String, String>>,

  // Fine-grained optional sensor streams
  // [x, y, z] in m/s^2 (linear acceleration)
  val accelerometer: StreamedSignal<List<Float>>,
  // [x, y, z] in rad/s (angular speed)
  val gyroscope: StreamedSignal<List<Float>>,
  // [x, y, z] in uT (magnetic field / compass)
  val magnetometer: StreamedSignal<List<Float>>,
  // Atmospheric pressure in hPa
  val barometer: StreamedSignal<Float>,
  // Ambient temperature in degrees Celsius (°C)
  val ambientTemp: StreamedSignal<Float>,
  // Illuminance in lx (lux)
  val lightLevel: StreamedSignal<Float>,
  // Proximity distance in centimeters (cm)
  val proximity: StreamedSignal<Float>,
  // Latitude, Longitude, Altitude
  val locationGps: StreamedSignal<GpsCoordinates>,

  // Smartwatch & Audio Wearables
  // Heart rate in beats per minute (BPM)
  val heartRate: StreamedSignal<Float>,
  // Audio frequencies streamed from speaker
  val audioOutput: StreamedSignal<AudioFrame>,
  // Battery & power telemetry metrics
  val batteryPower: StreamedSignal<BatteryPowerMetrics> = StreamedSignal.empty(),
  val snapshotTimestampUs: Long,
  val orientation: Int = 0,
)
