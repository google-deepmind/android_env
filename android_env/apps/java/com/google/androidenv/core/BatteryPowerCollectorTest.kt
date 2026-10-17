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

import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.androidenv.core.ProtoConversions.toCore
import com.google.androidenv.core.ProtoConversions.toProto
import com.google.common.truth.Truth.assertThat
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.shadows.ShadowLooper

@RunWith(AndroidJUnit4::class)
class BatteryPowerCollectorTest {

  @Test
  fun testGetLatestMetrics_returnsValidDefaultsOrSimulatedMetrics() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    val metrics = collector.getLatestMetrics()

    assertThat(metrics.levelPercent).isAtLeast(0)
    assertThat(metrics.levelPercent).isAtMost(100)
    assertThat(metrics.voltageMv).isGreaterThan(0)
    assertThat(metrics.temperatureCelsius).isNotNull()
    assertThat(metrics.status).isNotEmpty()
    assertThat(metrics.pluggedSource).isNotEmpty()
    // Verify powerMw calculation did not overflow or produce invalid negative megawatt spikes
    assertThat(metrics.powerMw).isFinite()
  }

  @Test
  fun testStartAndStop_lifecycleSucceedsWithoutExceptions() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    collector.start()
    val metricsAfterStart = collector.getLatestMetrics()
    assertThat(metricsAfterStart.voltageMv).isGreaterThan(0)

    collector.stop()
    // Stopping twice should be a no-op and not throw
    collector.stop()
  }

  @Test
  fun testGetLatestMetrics_defensiveSafeguardsAndSentinels() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    val metrics = collector.getLatestMetrics()

    // Verify temperature is not corrupted by missing extra default (-1 / 10 = -0.1)
    assertThat(metrics.temperatureCelsius).isAtLeast(-20.0f)
    assertThat(metrics.temperatureCelsius).isAtMost(80.0f)

    // Verify pluggedSource is valid and not overridden by bitwise two's-complement trap
    assertThat(metrics.pluggedSource).isAnyOf("UNPLUGGED", "AC", "USB", "WIRELESS", "DOCK_OR_OTHER")

    // Verify chargeCounter is non-negative (no -1L sentinel leak)
    assertThat(metrics.chargeCounterUah).isAtLeast(0L)
    // Verify energyCounterNwh is non-negative (no Long.MIN_VALUE leak)
    assertThat(metrics.energyCounterNwh).isAtLeast(0L)
  }

  @Test
  fun testGetLatestMetrics_multipleSequentialCallsSucceed() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    collector.start()
    for (i in 1..10) {
      val metrics = collector.getLatestMetrics()
      assertThat(metrics.levelPercent).isAtLeast(0)
      assertThat(metrics.voltageMv).isGreaterThan(0)
      assertThat(metrics.powerMw).isFinite()
    }
    collector.stop()
  }

  @Test
  fun testDeviceSignalEnum_batteryPowerConversion() {
    val signal = DeviceSignal.BATTERY_POWER
    val protoSignal = signal.toProto()
    assertThat(protoSignal).isEqualTo(com.androidenv.proto.DeviceSignal.DEVICE_SIGNAL_BATTERY_POWER)
    assertThat(protoSignal.toCore()).isEqualTo(DeviceSignal.BATTERY_POWER)
  }

  @Test
  fun testBatteryPowerMetrics_protoConversionInDeviceState() {
    val metrics =
      BatteryPowerMetrics(
        levelPercent = 85,
        currentNowUa = 450_000L,
        voltageMv = 4200,
        powerMw = 1890.0,
        temperatureCelsius = 28.5f,
        status = "DISCHARGING",
        pluggedSource = "UNPLUGGED",
        chargeCounterUah = 3_000_000L,
        thermalStatus = 0,
        energyCounterNwh = 15_000_000_000L,
      )

    val deviceState =
      DeviceState(
        screenshot = StreamedSignal.empty(),
        accessibilityRoot = StreamedSignal.empty(),
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
        batteryPower = StreamedSignal(metrics, 123456789L, 1L),
        snapshotTimestampUs = 123456789L,
        orientation = 0,
      )

    val protoState = deviceState.toProto()
    val batteryProtoSignal =
      protoState.signalsList.find {
        it.type == com.androidenv.proto.DeviceSignal.DEVICE_SIGNAL_BATTERY_POWER
      }

    assertThat(batteryProtoSignal).isNotNull()
    assertThat(batteryProtoSignal!!.hasBatteryPower()).isTrue()

    val protoMetrics = batteryProtoSignal.batteryPower
    assertThat(protoMetrics.levelPercent).isEqualTo(85)
    assertThat(protoMetrics.currentNowUa).isEqualTo(450_000L)
    assertThat(protoMetrics.voltageMv).isEqualTo(4200)
    assertThat(protoMetrics.powerMw).isEqualTo(1890.0)
    assertThat(protoMetrics.temperatureCelsius).isEqualTo(28.5f)
    assertThat(protoMetrics.status).isEqualTo("DISCHARGING")
    assertThat(protoMetrics.pluggedSource).isEqualTo("UNPLUGGED")
    assertThat(protoMetrics.chargeCounterUah).isEqualTo(3_000_000L)
    assertThat(protoMetrics.thermalStatus).isEqualTo(0)
    assertThat(protoMetrics.energyCounterNwh).isEqualTo(15_000_000_000L)
  }

  @Test
  fun testParseBatteryIntent_powerConnectedAndDisconnected() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    collector.start()
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val connectedIntent = android.content.Intent(android.content.Intent.ACTION_POWER_CONNECTED)
    context.sendBroadcast(connectedIntent)
    ShadowLooper.idleMainLooper()

    val metricsConnected = collector.getLatestMetrics()
    assertThat(metricsConnected.status).isEqualTo("CHARGING")
    assertThat(metricsConnected.pluggedSource).isEqualTo("AC")

    val disconnectedIntent =
      android.content.Intent(android.content.Intent.ACTION_POWER_DISCONNECTED)
    context.sendBroadcast(disconnectedIntent)
    ShadowLooper.idleMainLooper()

    val metricsDisconnected = collector.getLatestMetrics()
    assertThat(metricsDisconnected.status).isEqualTo("DISCHARGING")
    assertThat(metricsDisconnected.pluggedSource).isEqualTo("UNPLUGGED")
    collector.stop()
  }

  @Test
  fun testParseBatteryIntent_powerConnectedWhenAlreadyPluggedUsb_preservesUsbSource() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    collector.start()
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()

    val intentUsb =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(
          android.os.BatteryManager.EXTRA_PLUGGED,
          android.os.BatteryManager.BATTERY_PLUGGED_USB,
        )
        putExtra(
          android.os.BatteryManager.EXTRA_STATUS,
          android.os.BatteryManager.BATTERY_STATUS_CHARGING,
        )
      }
    context.sendBroadcast(intentUsb)
    ShadowLooper.idleMainLooper()

    assertThat(collector.getLatestMetrics().pluggedSource).isEqualTo("USB")

    val connectedIntent = android.content.Intent(android.content.Intent.ACTION_POWER_CONNECTED)
    context.sendBroadcast(connectedIntent)
    ShadowLooper.idleMainLooper()

    val metrics = collector.getLatestMetrics()
    assertThat(metrics.status).isEqualTo("CHARGING")
    assertThat(metrics.pluggedSource).isEqualTo("USB")
    collector.stop()
  }

  @Test
  fun testParseBatteryIntent_powerConnectedWhenAlreadyPluggedWireless_preservesWirelessSource() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    collector.start()
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()

    val intentWireless =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(
          android.os.BatteryManager.EXTRA_PLUGGED,
          android.os.BatteryManager.BATTERY_PLUGGED_WIRELESS,
        )
        putExtra(
          android.os.BatteryManager.EXTRA_STATUS,
          android.os.BatteryManager.BATTERY_STATUS_CHARGING,
        )
      }
    context.sendBroadcast(intentWireless)
    ShadowLooper.idleMainLooper()

    assertThat(collector.getLatestMetrics().pluggedSource).isEqualTo("WIRELESS")

    val connectedIntent = android.content.Intent(android.content.Intent.ACTION_POWER_CONNECTED)
    context.sendBroadcast(connectedIntent)
    ShadowLooper.idleMainLooper()

    val metrics = collector.getLatestMetrics()
    assertThat(metrics.status).isEqualTo("CHARGING")
    assertThat(metrics.pluggedSource).isEqualTo("WIRELESS")
    collector.stop()
  }

  @Test
  fun testParseBatteryIntent_batteryChangedVariations() {
    val collector = BatteryPowerCollector(ApplicationProvider.getApplicationContext())
    collector.start()
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()

    // Test charging status, AC plugged, low voltage scaling (<100 decivolts/volts -> mV
    // conversion), and level/scale
    val intentAc =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(android.os.BatteryManager.EXTRA_VOLTAGE, 4) // 4V -> 4000mV
        putExtra(android.os.BatteryManager.EXTRA_TEMPERATURE, 312) // 31.2 C
        putExtra(
          android.os.BatteryManager.EXTRA_STATUS,
          android.os.BatteryManager.BATTERY_STATUS_CHARGING,
        )
        putExtra(
          android.os.BatteryManager.EXTRA_PLUGGED,
          android.os.BatteryManager.BATTERY_PLUGGED_AC,
        )
        putExtra(android.os.BatteryManager.EXTRA_LEVEL, 45)
        putExtra(android.os.BatteryManager.EXTRA_SCALE, 50) // 90%
      }
    context.sendBroadcast(intentAc)
    ShadowLooper.idleMainLooper()
    var metrics = collector.getLatestMetrics()

    assertThat(metrics.voltageMv).isEqualTo(4000)
    assertThat(metrics.temperatureCelsius).isEqualTo(31.2f)
    assertThat(metrics.status).isEqualTo("CHARGING")
    assertThat(metrics.pluggedSource).isEqualTo("AC")
    assertThat(metrics.levelPercent).isEqualTo(90)

    // Test USB plugged, FULL status
    val intentUsb =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(android.os.BatteryManager.EXTRA_VOLTAGE, 4100)
        putExtra(
          android.os.BatteryManager.EXTRA_STATUS,
          android.os.BatteryManager.BATTERY_STATUS_FULL,
        )
        putExtra(
          android.os.BatteryManager.EXTRA_PLUGGED,
          android.os.BatteryManager.BATTERY_PLUGGED_USB,
        )
      }
    context.sendBroadcast(intentUsb)
    ShadowLooper.idleMainLooper()
    metrics = collector.getLatestMetrics()

    assertThat(metrics.status).isEqualTo("FULL")
    assertThat(metrics.pluggedSource).isEqualTo("USB")

    // Test WIRELESS plugged, NOT_CHARGING status (no EXTRA_VOLTAGE in intent, voltageMv remains
    // last known)
    val intentWireless =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(
          android.os.BatteryManager.EXTRA_STATUS,
          android.os.BatteryManager.BATTERY_STATUS_NOT_CHARGING,
        )
        putExtra(
          android.os.BatteryManager.EXTRA_PLUGGED,
          android.os.BatteryManager.BATTERY_PLUGGED_WIRELESS,
        )
      }
    context.sendBroadcast(intentWireless)
    ShadowLooper.idleMainLooper()
    metrics = collector.getLatestMetrics()

    assertThat(metrics.status).isEqualTo("NOT_CHARGING")
    assertThat(metrics.pluggedSource).isEqualTo("WIRELESS")
    assertThat(metrics.voltageMv).isEqualTo(4100)

    // Test UNKNOWN status and DOCK_OR_OTHER plugged
    val intentOther =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(android.os.BatteryManager.EXTRA_STATUS, 999)
        putExtra(android.os.BatteryManager.EXTRA_PLUGGED, 8) // Non-standard bit flag
      }
    context.sendBroadcast(intentOther)
    ShadowLooper.idleMainLooper()
    metrics = collector.getLatestMetrics()

    assertThat(metrics.status).isEqualTo("UNKNOWN")
    assertThat(metrics.pluggedSource).isEqualTo("DOCK_OR_OTHER")
    assertThat(metrics.voltageMv).isEqualTo(4100)

    // Test EXTRA_PLUGGED = 0 -> UNPLUGGED
    val intentUnplugged =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(android.os.BatteryManager.EXTRA_PLUGGED, 0)
      }
    context.sendBroadcast(intentUnplugged)
    ShadowLooper.idleMainLooper()
    metrics = collector.getLatestMetrics()

    assertThat(metrics.pluggedSource).isEqualTo("UNPLUGGED")
    collector.stop()
  }

  @Test
  fun testMockBatteryManager_nonSentinelCurrentAndCounters() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val mockBatteryManager = org.mockito.Mockito.mock(android.os.BatteryManager::class.java)

    org.mockito.Mockito.`when`(
        mockBatteryManager.getLongProperty(android.os.BatteryManager.BATTERY_PROPERTY_CURRENT_NOW)
      )
      .thenReturn(450_000L)
    org.mockito.Mockito.`when`(
        mockBatteryManager.getLongProperty(
          android.os.BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER
        )
      )
      .thenReturn(3_000_000L)
    org.mockito.Mockito.`when`(
        mockBatteryManager.getLongProperty(
          android.os.BatteryManager.BATTERY_PROPERTY_ENERGY_COUNTER
        )
      )
      .thenReturn(15_000_000_000L)
    org.mockito.Mockito.`when`(
        mockBatteryManager.getIntProperty(android.os.BatteryManager.BATTERY_PROPERTY_CAPACITY)
      )
      .thenReturn(85)

    val injectedCollector = BatteryPowerCollector(context, batteryManager = mockBatteryManager)
    val metrics = injectedCollector.getLatestMetrics()

    assertThat(metrics.currentNowUa).isEqualTo(450_000L)
    assertThat(metrics.chargeCounterUah).isEqualTo(3_000_000L)
    assertThat(metrics.energyCounterNwh).isEqualTo(15_000_000_000L)
    assertThat(metrics.levelPercent).isEqualTo(85)
  }

  @Test
  fun testMockBatteryManager_mAUnitAutoScaling() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val mockBatteryManager = org.mockito.Mockito.mock(android.os.BatteryManager::class.java)

    // Current < 10000 microamps (e.g. 450) triggers OEM mA -> uA auto-scaling (*1000)
    org.mockito.Mockito.`when`(
        mockBatteryManager.getLongProperty(android.os.BatteryManager.BATTERY_PROPERTY_CURRENT_NOW)
      )
      .thenReturn(450L)

    val injectedCollector = BatteryPowerCollector(context, batteryManager = mockBatteryManager)
    val metrics = injectedCollector.getLatestMetrics()

    assertThat(metrics.currentNowUa).isEqualTo(450_000L)
  }

  @Test
  fun testMockBatteryManager_allCurrentSentinels() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val mockBatteryManager = org.mockito.Mockito.mock(android.os.BatteryManager::class.java)

    val sentinels = listOf(Long.MIN_VALUE, Long.MAX_VALUE, 0L, -1L, Int.MIN_VALUE.toLong())

    for (sentinel in sentinels) {
      org.mockito.Mockito.`when`(
          mockBatteryManager.getLongProperty(android.os.BatteryManager.BATTERY_PROPERTY_CURRENT_NOW)
        )
        .thenReturn(sentinel)

      val injectedCollector = BatteryPowerCollector(context, batteryManager = mockBatteryManager)
      val metrics = injectedCollector.getLatestMetrics()

      assertThat(metrics.currentNowUa).isEqualTo(0L)
    }
  }

  @Test
  fun testRealPowerManager_thermalStatus() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val powerManager =
      context.getSystemService(android.content.Context.POWER_SERVICE) as android.os.PowerManager
    val injectedCollector = BatteryPowerCollector(context, powerManager = powerManager)
    val metrics = injectedCollector.getLatestMetrics()

    assertThat(metrics.thermalStatus).isEqualTo(0)
  }

  @Test
  fun testParseBatteryIntent_invalidOrMissingTemperatureExtra() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val testCollector = BatteryPowerCollector(context)
    testCollector.start()

    // Intent missing EXTRA_TEMPERATURE
    val intentMissingTemp =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(android.os.BatteryManager.EXTRA_VOLTAGE, 4000)
      }
    context.sendBroadcast(intentMissingTemp)
    ShadowLooper.idleMainLooper()
    var metrics = testCollector.getLatestMetrics()
    assertThat(metrics.temperatureCelsius).isEqualTo(25.0f)

    // Intent with invalid extra temperature (-2000 = -200°C)
    val intentInvalidTemp =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(android.os.BatteryManager.EXTRA_TEMPERATURE, -2000)
      }
    context.sendBroadcast(intentInvalidTemp)
    ShadowLooper.idleMainLooper()
    metrics = testCollector.getLatestMetrics()
    assertThat(metrics.temperatureCelsius).isEqualTo(25.0f)
    testCollector.stop()
  }

  @Test
  fun testMockHardwarePropertiesManager_batteryTemperature() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val mockHwManager = org.mockito.Mockito.mock(android.os.HardwarePropertiesManager::class.java)

    org.mockito.Mockito.`when`(
        mockHwManager.getDeviceTemperatures(
          android.os.HardwarePropertiesManager.DEVICE_TEMPERATURE_BATTERY,
          android.os.HardwarePropertiesManager.TEMPERATURE_CURRENT,
        )
      )
      .thenReturn(floatArrayOf(35.5f))

    val injectedCollector =
      BatteryPowerCollector(context, hardwarePropertiesManager = mockHwManager)
    val metrics = injectedCollector.getLatestMetrics()

    assertThat(metrics.temperatureCelsius).isEqualTo(35.5f)
  }

  @Test
  @Suppress("DEPRECATION")
  fun testGetLatestMetrics_withoutStart_queriesStickyIntent() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val unstartedCollector = BatteryPowerCollector(context)
    assertThat(unstartedCollector.isStarted).isFalse()

    // Send sticky battery changed broadcast
    val stickyIntent =
      android.content.Intent(android.content.Intent.ACTION_BATTERY_CHANGED).apply {
        putExtra(android.os.BatteryManager.EXTRA_VOLTAGE, 3800)
        putExtra(android.os.BatteryManager.EXTRA_LEVEL, 77)
        putExtra(android.os.BatteryManager.EXTRA_SCALE, 100)
      }
    context.sendStickyBroadcast(stickyIntent)
    ShadowLooper.idleMainLooper()

    // getLatestMetrics without calling start() re-queries sticky broadcast
    val metrics = unstartedCollector.getLatestMetrics()
    assertThat(metrics.voltageMv).isEqualTo(3800)
    assertThat(metrics.levelPercent).isEqualTo(77)
  }

  @Test
  fun testStartAndStop_lifecycle() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val lifecycleCollector = BatteryPowerCollector(context)
    assertThat(lifecycleCollector.isStarted).isFalse()

    // Verify start and stop sequence
    lifecycleCollector.start()
    assertThat(lifecycleCollector.isStarted).isTrue()

    lifecycleCollector.start() // Repeated start is no-op
    assertThat(lifecycleCollector.isStarted).isTrue()

    lifecycleCollector.stop()
    assertThat(lifecycleCollector.isStarted).isFalse()

    lifecycleCollector.stop() // Repeated stop catches unregister IllegalArgumentException cleanly
    assertThat(lifecycleCollector.isStarted).isFalse()
  }

  private class TestContextWrapper(base: android.content.Context) :
    android.content.ContextWrapper(base) {
    var registerCount = 0
    var unregisterCount = 0
    var throwOnUnregister = false

    override fun registerReceiver(
      receiver: android.content.BroadcastReceiver?,
      filter: android.content.IntentFilter?,
    ): android.content.Intent? {
      registerCount++
      return super.registerReceiver(receiver, filter)
    }

    override fun registerReceiver(
      receiver: android.content.BroadcastReceiver?,
      filter: android.content.IntentFilter?,
      flags: Int,
    ): android.content.Intent? {
      registerCount++
      return super.registerReceiver(receiver, filter, flags)
    }

    override fun unregisterReceiver(receiver: android.content.BroadcastReceiver?) {
      unregisterCount++
      if (throwOnUnregister) {
        throw IllegalArgumentException("Simulated unregister exception")
      }
      super.unregisterReceiver(receiver)
    }
  }

  @Test
  fun testStartAndStop_verifiesRegisterUnregisterGuardAndExceptionHandling() {
    val context = ApplicationProvider.getApplicationContext<android.content.Context>()
    val testContext = TestContextWrapper(context)
    val testCollector = BatteryPowerCollector(testContext)

    // 1. Calling start() twice must call context.registerReceiver EXACTLY once
    testCollector.start()
    testCollector.start()
    assertThat(testContext.registerCount).isEqualTo(1)

    // 2. Calling stop() twice must call context.unregisterReceiver EXACTLY once
    testCollector.stop()
    testCollector.stop()
    assertThat(testContext.unregisterCount).isEqualTo(1)

    // 3. Exception handling when unregisterReceiver throws IllegalArgumentException
    testContext.throwOnUnregister = true
    testCollector.start()
    testCollector.stop()
    assertThat(testCollector.isStarted).isFalse()
  }
}
