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

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.HardwarePropertiesManager
import android.os.PowerManager
import android.util.Log
import kotlin.math.abs

/**
 * APK-native Battery and Power metric extraction collector for AndroidDeviceEnv.
 * Collects real-time battery voltage, current draw, charge counter, thermal status,
 * and calculated power consumption without relying on ADB commands or sysfs file access.
 *
 * Implements hardened safeguards against integer overflow, OEM unit scaling differences,
 * and Goldfish/QEMU emulator virtualization quirks.
 */
class BatteryPowerCollector(
    private val context: Context,
    private val batteryManager: BatteryManager? =
      context.getSystemService(Context.BATTERY_SERVICE) as? BatteryManager,
    private val powerManager: PowerManager? =
      context.getSystemService(Context.POWER_SERVICE) as? PowerManager,
    private val hardwarePropertiesManager: HardwarePropertiesManager? =
      context.getSystemService(Context.HARDWARE_PROPERTIES_SERVICE) as? HardwarePropertiesManager,
) {

  private var _isStarted = false
  val isStarted: Boolean
    @Synchronized get() = _isStarted

  private var lastKnownVoltageMv: Int = 4000 // Default 3.7V - 4.0V nominal battery
  private var lastKnownTempCelsius: Float = 25.0f

  // Possible values: "CHARGING", "DISCHARGING", "FULL", "NOT_CHARGING", "UNKNOWN"
  private var lastKnownStatus: String = "UNKNOWN"

  // Possible values: "AC", "USB", "WIRELESS", "UNPLUGGED", "DOCK_OR_OTHER"
  private var lastKnownPlugged: String = "UNPLUGGED"
  private var lastKnownLevelPercent: Int = 100

  private val batteryReceiver =
    object : BroadcastReceiver() {
      override fun onReceive(context: Context?, intent: Intent?) {
        if (intent != null) {
          parseBatteryIntent(intent)
        }
      }
    }

  @Synchronized
  @Suppress("UnprotectedReceiver")
  fun start() {
    if (_isStarted) return
    val filter =
      IntentFilter().apply {
        addAction(Intent.ACTION_BATTERY_CHANGED)
        addAction(Intent.ACTION_POWER_CONNECTED)
        addAction(Intent.ACTION_POWER_DISCONNECTED)
      }
    val stickyIntent =
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.TIRAMISU) {
        context.registerReceiver(batteryReceiver, filter, Context.RECEIVER_NOT_EXPORTED)
      } else {
        context.registerReceiver(batteryReceiver, filter)
      }
    if (stickyIntent != null) {
      parseBatteryIntent(stickyIntent)
    }
    _isStarted = true
    Log.i(TAG, "BatteryPowerCollector started")
  }

  @Synchronized
  fun stop() {
    if (!_isStarted) return
    try {
      context.unregisterReceiver(batteryReceiver)
    } catch (e: IllegalArgumentException) {
      Log.w(TAG, "Receiver was not registered", e)
    }
    _isStarted = false
    Log.i(TAG, "BatteryPowerCollector stopped")
  }

  /** Captures the latest instantaneous battery and power telemetry. */
  @Synchronized
  @Suppress("UnprotectedReceiver")
  fun getLatestMetrics(): BatteryPowerMetrics {
    // Re-query sticky broadcast if not started or to ensure freshest voltage/temp
    if (!_isStarted) {
      val stickyIntent =
        context.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
      if (stickyIntent != null) {
        parseBatteryIntent(stickyIntent)
      }
    }

    val rawCurrent =
      batteryManager?.getLongProperty(BatteryManager.BATTERY_PROPERTY_CURRENT_NOW)
        ?: Long.MIN_VALUE
    val chargeCounter =
      batteryManager?.getLongProperty(BatteryManager.BATTERY_PROPERTY_CHARGE_COUNTER)
        ?: Long.MIN_VALUE
    val capacityPercent =
      batteryManager?.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY) ?: -1

    val levelPercent = if (capacityPercent in 1..100) capacityPercent else lastKnownLevelPercent

    // Normalization & Defensive Safeguards:
    // Detect sentinels (Long.MIN_VALUE, Long.MAX_VALUE, 0 on emulators, -1 or Int.MIN_VALUE on older HALs)
    val isCurrentSentinel =
      rawCurrent == Long.MIN_VALUE ||
        rawCurrent == Long.MAX_VALUE ||
        rawCurrent == 0L ||
        rawCurrent == -1L ||
        rawCurrent == Int.MIN_VALUE.toLong()

    val currentNowUa: Long =
      if (!isCurrentSentinel) {
        // Auto-detect mA vs uA scaling across OEMs
        // If absolute value is smaller than 10000, OEM likely returned mA instead of uA
        if (abs(rawCurrent) > 0 && abs(rawCurrent) < 10000) {
          rawCurrent * 1000L
        } else {
          rawCurrent
        }
      } else {
        0L
      }

    // 64-bit floating point arithmetic to prevent 32-bit Math.abs(Integer.MIN_VALUE) overflow trap
    val powerMw = (abs(currentNowUa.toDouble()) * lastKnownVoltageMv.toDouble()) / 1_000_000.0

    val thermalStatus =
      if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.Q && powerManager != null) {
        try {
          powerManager.currentThermalStatus
        } catch (e: Exception) {
          0
        }
      } else {
        0
      }

    val rawEnergyNwh =
      try {
        batteryManager?.getLongProperty(BatteryManager.BATTERY_PROPERTY_ENERGY_COUNTER)
          ?: Long.MIN_VALUE
      } catch (e: Exception) {
        Long.MIN_VALUE
      }

    val validChargeCounter =
      if (chargeCounter <= 0L || chargeCounter == Long.MAX_VALUE) {
        0L
      } else {
        chargeCounter
      }

    val validEnergyCounterNwh =
      if (rawEnergyNwh <= 0L || rawEnergyNwh == Long.MAX_VALUE) {
        0L
      } else {
        rawEnergyNwh
      }

    val bestTempCelsius = getBestBatteryTemperatureCelsius()

    return BatteryPowerMetrics(
      levelPercent = levelPercent,
      currentNowUa = currentNowUa,
      voltageMv = lastKnownVoltageMv,
      powerMw = powerMw,
      temperatureCelsius = bestTempCelsius,
      status = lastKnownStatus,
      pluggedSource = lastKnownPlugged,
      chargeCounterUah = validChargeCounter,
      thermalStatus = thermalStatus,
      energyCounterNwh = validEnergyCounterNwh,
    )
  }

  private fun getBestBatteryTemperatureCelsius(): Float {
    if (hardwarePropertiesManager != null) {
      try {
        val temps =
          hardwarePropertiesManager.getDeviceTemperatures(
            HardwarePropertiesManager.DEVICE_TEMPERATURE_BATTERY,
            HardwarePropertiesManager.TEMPERATURE_CURRENT
          )
        if (temps.isNotEmpty() && temps[0] > -100.0f) {
          return temps[0]
        }
      } catch (e: Exception) {
        // Fallback to EXTRA_TEMPERATURE when unprivileged app or SecurityException
      }
    }
    return lastKnownTempCelsius
  }

  @Synchronized
  private fun parseBatteryIntent(intent: Intent) {
    when (intent.action) {
      Intent.ACTION_POWER_CONNECTED -> {
        lastKnownStatus = "CHARGING"
        if (lastKnownPlugged == "UNPLUGGED") {
          lastKnownPlugged = "AC"
        }
        return
      }
      Intent.ACTION_POWER_DISCONNECTED -> {
        lastKnownStatus = "DISCHARGING"
        lastKnownPlugged = "UNPLUGGED"
        return
      }
    }

    val voltage = intent.getIntExtra(BatteryManager.EXTRA_VOLTAGE, -1)
    if (voltage > 0) {
      // Android EXTRA_VOLTAGE is typically reported in millivolts (mV).
      // Some old hardware reports in volts or decivolts; ensure proper mV range
      lastKnownVoltageMv = if (voltage < 100) voltage * 1000 else voltage
    }

    val tempTenths = intent.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
    if (tempTenths > -1000) {
      lastKnownTempCelsius = tempTenths / 10.0f
    }

    val statusInt = intent.getIntExtra(BatteryManager.EXTRA_STATUS, -1)
    lastKnownStatus =
      when (statusInt) {
        BatteryManager.BATTERY_STATUS_CHARGING -> "CHARGING"
        BatteryManager.BATTERY_STATUS_DISCHARGING -> "DISCHARGING"
        BatteryManager.BATTERY_STATUS_FULL -> "FULL"
        BatteryManager.BATTERY_STATUS_NOT_CHARGING -> "NOT_CHARGING"
        else -> "UNKNOWN"
      }

    if (intent.hasExtra(BatteryManager.EXTRA_PLUGGED)) {
      val pluggedInt = intent.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0)
      lastKnownPlugged =
        when {
          (pluggedInt and BatteryManager.BATTERY_PLUGGED_AC) != 0 -> "AC"
          (pluggedInt and BatteryManager.BATTERY_PLUGGED_USB) != 0 -> "USB"
          (pluggedInt and BatteryManager.BATTERY_PLUGGED_WIRELESS) != 0 -> "WIRELESS"
          pluggedInt == 0 -> "UNPLUGGED"
          else -> "DOCK_OR_OTHER"
        }
    }

    val level = intent.getIntExtra(BatteryManager.EXTRA_LEVEL, -1)
    val scale = intent.getIntExtra(BatteryManager.EXTRA_SCALE, -1)
    if (level >= 0 && scale > 0) {
      lastKnownLevelPercent = ((level.toFloat() / scale.toFloat()) * 100.0f).toInt()
    }
  }

  companion object {
    private const val TAG = "BatteryPowerCollector"
  }
}
