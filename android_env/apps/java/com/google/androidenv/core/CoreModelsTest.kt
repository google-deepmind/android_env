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
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.annotation.Config

@RunWith(AndroidJUnit4::class)
@Config(manifest = Config.NONE)
class CoreModelsTest {

  @Test
  fun testActionEqualsAndHashCode() {
    val pos1 = listOf(0.1f, 0.2f)
    val pos2 = listOf(0.1f, 0.2f)
    val pos3 = listOf(0.3f, 0.4f)

    val action1 = Action(ActionType.TOUCH_DOWN, pos1, null)
    val action2 = Action(ActionType.TOUCH_DOWN, pos2, null)
    val action3 = Action(ActionType.TOUCH_DOWN, pos3, null)
    val actionDifferentType = Action(ActionType.TOUCH_UP, pos1, null)
    val actionNullPos = Action(ActionType.TOUCH_DOWN, null, null)

    // Structural equality check (automatically supported by List in data class)
    assertThat(action1).isEqualTo(action2)
    assertThat(action1.hashCode()).isEqualTo(action2.hashCode())

    assertThat(action1).isNotEqualTo(action3)
    assertThat(action1).isNotEqualTo(actionDifferentType)
    assertThat(action1).isNotEqualTo(actionNullPos)
  }

  @Test
  fun testAudioFrameEqualsAndHashCode() {
    val bytes1 = byteArrayOf(-31)
    val bytes2 = byteArrayOf(-31)
    val bytes3 = byteArrayOf(4, 5, 6)

    val frame1 = AudioFrame(bytes1, 44100, 2)
    val frame2 = AudioFrame(bytes2, 44100, 2)
    val frame3 = AudioFrame(bytes3, 44100, 2)
    val frameDifferentRate = AudioFrame(bytes1, 22050, 2)
    val frameDifferentChannels = AudioFrame(bytes1, 44100, 1)
    val frameDifferentFormat = AudioFrame(bytes1, 44100, 2, "PCM_16")

    assertThat(frame1).isEqualTo(frame1)
    assertThat(frame1).isEqualTo(frame2)
    assertThat(frame1.hashCode()).isEqualTo(frame2.hashCode())

    assertThat(frame1).isNotEqualTo(frame3)
    assertNotEqualObjects(frame1, "different_type")
    assertThat(frame1).isNotEqualTo(null)
    assertThat(frame1).isNotEqualTo(frameDifferentRate)
    assertThat(frame1).isNotEqualTo(frameDifferentChannels)
    assertThat(frame1).isNotEqualTo(frameDifferentFormat)

    // Test hash code inequality to prevent mutations
    assertThat(frame1.hashCode()).isNotEqualTo(frame3.hashCode())
    assertThat(frame1.hashCode()).isNotEqualTo(frameDifferentRate.hashCode())
    assertThat(frame1.hashCode()).isNotEqualTo(frameDifferentFormat.hashCode())

    // Specific test for channelCount mutation (result = 31 * result + channelCount)
    // We use channelCount = 0 for both frames to make them equal under mutation (result * 0 = 0)
    // but they differ in sampleRateHz so they should have different hash codes originally.
    val frameChannels0Rate1 = AudioFrame(bytes1, 44100, 0)
    val frameChannels0Rate2 = AudioFrame(bytes1, 22050, 0)
    assertThat(frameChannels0Rate1.hashCode()).isNotEqualTo(frameChannels0Rate2.hashCode())

    // Specific test for sampleFormat hashCode mutation (result = 31 * result +
    // (sampleFormat?.hashCode() ?: 0))
    // We choose strings "foo?" and "foo " which have hash codes differing by 31.
    // We choose channelCount 2 and 1 respectively, so that BaseA - BaseB = 1.
    // Under mutation (+ is changed to -), they will have the same hashCode.
    val frameFormatMutation1 = AudioFrame(bytes1, 44100, 2, "foo?")
    val frameFormatMutation2 = AudioFrame(bytes1, 44100, 1, "foo ")
    assertThat(frameFormatMutation1.hashCode()).isNotEqualTo(frameFormatMutation2.hashCode())
  }

  @Test
  fun testGpsCoordinates() {
    val gps1 = GpsCoordinates(1.0, 2.0, 3.0)
    val gps2 = GpsCoordinates(1.0, 2.0, 3.0)
    val gps3 = GpsCoordinates(4.0, 5.0, 6.0)

    assertThat(gps1).isEqualTo(gps2)
    assertThat(gps1.hashCode()).isEqualTo(gps2.hashCode())
    assertThat(gps1).isNotEqualTo(gps3)
    assertThat(gps1.latitude).isEqualTo(1.0)
    assertThat(gps1.longitude).isEqualTo(2.0)
    assertThat(gps1.altitude).isEqualTo(3.0)
  }

  @Test
  fun testStreamedSignal() {
    val signal1 = StreamedSignal("test", 100L, 1L)
    val signal2 = StreamedSignal("test", 100L, 1L)
    val signal3 = StreamedSignal("other", 200L, 2L)
    val emptySignal = StreamedSignal.empty<String>()

    assertThat(signal1).isEqualTo(signal2)
    assertThat(signal1.hashCode()).isEqualTo(signal2.hashCode())
    assertThat(signal1).isNotEqualTo(signal3)

    assertThat(signal1.value).isEqualTo("test")
    assertThat(signal1.timestampUs).isEqualTo(100L)
    assertThat(signal1.sequenceId).isEqualTo(1L)

    assertThat(emptySignal.value).isNull()
    assertThat(emptySignal.timestampUs).isEqualTo(0L)
    assertThat(emptySignal.sequenceId).isEqualTo(0L)
  }

  @Test
  fun testDeviceState() {
    val screenshot = StreamedSignal.empty<Bitmap>()
    val accessibilityRoot = StreamedSignal.empty<AccessibilityNodeInfo>()
    val activePackage = StreamedSignal.empty<String>()
    val activeActivity = StreamedSignal.empty<String>()
    val systemLogs = StreamedSignal.empty<List<String>>()
    val runningProcesses = StreamedSignal.empty<List<String>>()
    val deviceSettings = StreamedSignal.empty<Map<String, String>>()
    val accelerometer = StreamedSignal.empty<List<Float>>()
    val gyroscope = StreamedSignal.empty<List<Float>>()
    val magnetometer = StreamedSignal.empty<List<Float>>()
    val barometer = StreamedSignal.empty<Float>()
    val ambientTemp = StreamedSignal.empty<Float>()
    val lightLevel = StreamedSignal.empty<Float>()
    val proximity = StreamedSignal.empty<Float>()
    val locationGps = StreamedSignal.empty<GpsCoordinates>()
    val heartRate = StreamedSignal.empty<Float>()
    val audioOutput = StreamedSignal.empty<AudioFrame>()
    val timestamp = 123456L

    val state1 =
      DeviceState(
        screenshot = screenshot,
        accessibilityRoot = accessibilityRoot,
        activePackage = activePackage,
        activeActivity = activeActivity,
        systemLogs = systemLogs,
        runningProcesses = runningProcesses,
        deviceSettings = deviceSettings,
        accelerometer = accelerometer,
        gyroscope = gyroscope,
        magnetometer = magnetometer,
        barometer = barometer,
        ambientTemp = ambientTemp,
        lightLevel = lightLevel,
        proximity = proximity,
        locationGps = locationGps,
        heartRate = heartRate,
        audioOutput = audioOutput,
        snapshotTimestampUs = timestamp,
      )

    val state2 =
      DeviceState(
        screenshot = screenshot,
        accessibilityRoot = accessibilityRoot,
        activePackage = activePackage,
        activeActivity = activeActivity,
        systemLogs = systemLogs,
        runningProcesses = runningProcesses,
        deviceSettings = deviceSettings,
        accelerometer = accelerometer,
        gyroscope = gyroscope,
        magnetometer = magnetometer,
        barometer = barometer,
        ambientTemp = ambientTemp,
        lightLevel = lightLevel,
        proximity = proximity,
        locationGps = locationGps,
        heartRate = heartRate,
        audioOutput = audioOutput,
        snapshotTimestampUs = timestamp,
      )

    assertThat(state1).isEqualTo(state2)
    assertThat(state1.hashCode()).isEqualTo(state2.hashCode())
    assertThat(state1.snapshotTimestampUs).isEqualTo(timestamp)
  }

  @Test
  fun testAndroidDeviceEnvDefaultClose() {
    val env =
      object : AndroidDeviceEnv {
        override fun updateSubscriptions(activeSignals: Set<DeviceSignal>) {}

        override fun getDeviceState(): DeviceState {
          throw UnsupportedOperationException()
        }

        override fun injectAction(action: Action) {}
      }
    env.close()
    env.updateSubscriptions(emptySet())
    try {
      val unused = env.getDeviceState()
    } catch (e: UnsupportedOperationException) {
      assertThat(e).isNotNull()
    }
    env.injectAction(Action(ActionType.TOUCH_DOWN, null, null))
  }

  @Test
  fun testDeviceSignalEnum() {
    val signals = DeviceSignal.values()
    assertThat(signals).isNotEmpty()
    assertThat(DeviceSignal.valueOf("SCREENSHOT")).isEqualTo(DeviceSignal.SCREENSHOT)
  }

  private fun assertNotEqualObjects(actual: Any?, expected: Any?) {
    assertThat(actual).isNotEqualTo(expected)
  }
}
