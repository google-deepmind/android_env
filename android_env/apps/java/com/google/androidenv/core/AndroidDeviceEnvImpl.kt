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

import android.content.Context
import android.graphics.Bitmap
import android.hardware.Sensor
import android.hardware.SensorEvent
import android.hardware.SensorEventListener
import android.hardware.SensorManager
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import android.view.accessibility.AccessibilityNodeInfo
import java.io.BufferedReader
import java.io.ByteArrayOutputStream
import java.io.InputStreamReader
import java.util.concurrent.ConcurrentLinkedQueue

/**
 * Concrete implementation of AndroidDeviceEnv that interacts with Android APIs. Uses
 * ScreenShareService and InputService under the hood.
 */
class AndroidDeviceEnvImpl(
  private val context: Context,
  private val gestureInjector: GestureInjector = SystemGestureInjector(),
  private val screenShareProvider: ScreenShareProvider = SystemScreenShareProvider(),
) : AndroidDeviceEnv {

  init {
    screenShareProvider.setAudioListener(
      object : ScreenShareService.AudioCaptureListener {
        override fun onAudioCaptured(
          rawBytes: ByteArray,
          sampleRateHz: Int,
          channelCount: Int,
          sampleFormat: Int,
        ) {
          if (synchronized(this@AndroidDeviceEnvImpl) { activeSignals.contains(DeviceSignal.AUDIO_OUTPUT) }) {
            val formatStr =
              when (sampleFormat) {
                android.media.AudioFormat.ENCODING_PCM_16BIT -> "pcm16"
                else -> "unknown"
              }
            val frame = AudioFrame(rawBytes, sampleRateHz, channelCount, formatStr)
            audioTracker.update(frame, System.nanoTime() / 1000)
          }
        }
      }
    )
  }

  private val sensorManager = context.getSystemService(Context.SENSOR_SERVICE) as SensorManager
  private val activeSignals = mutableSetOf<DeviceSignal>()

  // Trackers for streamed signals (thread-safe updates)
  private val screenshotTracker = StreamTracker<Bitmap>()
  private val a11yTracker = StreamTracker<AccessibilityNodeInfo>()
  private val a11yEventsTracker =
    StreamTracker<List<com.google.androidenv.accessibilityforwarder.EventRequest>>()
  private val activePackageTracker = StreamTracker<String>()
  private val activeActivityTracker = StreamTracker<String>()
  private val systemLogsTracker = StreamTracker<List<String>>()
  private val audioTracker = AudioStreamTracker()
  private val batteryPowerTracker = StreamTracker<BatteryPowerMetrics>()
  private val batteryPowerCollector = BatteryPowerCollector(context)

  private var logcatStreamer: LogcatStreamer? = null

  // Sensor trackers
  private val accelTracker = StreamTracker<List<Float>>()
  private val gyroTracker = StreamTracker<List<Float>>()
  private val magTracker = StreamTracker<List<Float>>()
  private val baroTracker = StreamTracker<Float>()
  private val tempTracker = StreamTracker<Float>()
  private val lightTracker = StreamTracker<Float>()
  private val proxTracker = StreamTracker<Float>()

  // Screenshot cache to detect changes
  private var lastScreenshotTimestampUs: Long = 0

  // Touch gesture tracking state
  private var isTouching = false
  private var latestX = 0.0f
  private var latestY = 0.0f
  private var latestStrokeDescription:
    android.accessibilityservice.GestureDescription.StrokeDescription? =
    null

  private val gestureLock = Any()

  private val sensorListener =
    object : SensorEventListener {
      override fun onSensorChanged(event: SensorEvent) {
        val eventTimestampUs = event.timestamp / 1000
        synchronized(this@AndroidDeviceEnvImpl) {
          when (event.sensor.type) {
            Sensor.TYPE_ACCELEROMETER -> {
              if (activeSignals.contains(DeviceSignal.SENSOR_ACCELEROMETER)) {
                accelTracker.update(event.values.toList(), eventTimestampUs)
              }
            }
            Sensor.TYPE_GYROSCOPE -> {
              if (activeSignals.contains(DeviceSignal.SENSOR_GYROSCOPE)) {
                gyroTracker.update(event.values.toList(), eventTimestampUs)
              }
            }
            Sensor.TYPE_MAGNETIC_FIELD -> {
              if (activeSignals.contains(DeviceSignal.SENSOR_MAGNETOMETER)) {
                magTracker.update(event.values.toList(), eventTimestampUs)
              }
            }
            Sensor.TYPE_PRESSURE -> {
              if (activeSignals.contains(DeviceSignal.SENSOR_BAROMETER)) {
                baroTracker.update(event.values[0], eventTimestampUs)
              }
            }
            Sensor.TYPE_AMBIENT_TEMPERATURE -> {
              if (activeSignals.contains(DeviceSignal.SENSOR_AMBIENT_TEMP)) {
                tempTracker.update(event.values[0], eventTimestampUs)
              }
            }
            Sensor.TYPE_LIGHT -> {
              if (activeSignals.contains(DeviceSignal.SENSOR_LIGHT)) {
                lightTracker.update(event.values[0], eventTimestampUs)
              }
            }
            Sensor.TYPE_PROXIMITY -> {
              if (activeSignals.contains(DeviceSignal.SENSOR_PROXIMITY)) {
                proxTracker.update(event.values[0], eventTimestampUs)
              }
            }
          }
        }
      }

      override fun onAccuracyChanged(sensor: Sensor, accuracy: Int) {}
    }

  override fun updateSubscriptions(activeSignals: Set<DeviceSignal>) {
    synchronized(this) {
      this.activeSignals.clear()
      this.activeSignals.addAll(activeSignals)
      Log.i(TAG, "updateSubscriptions: $activeSignals")

      // Manage Logcat Streamer
      if (activeSignals.contains(DeviceSignal.SYSTEM_LOGS)) {
        if (logcatStreamer == null) {
          logcatStreamer = LogcatStreamer().apply { start() }
        }
      } else {
        logcatStreamer?.stop()
        logcatStreamer = null
      }

      if (!activeSignals.contains(DeviceSignal.ACCESSIBILITY_TREE)) {
        a11yTracker.recycle()
      }

      if (activeSignals.contains(DeviceSignal.ACCESSIBILITY_EVENTS)) {
        gestureInjector.setEventTrackingEnabled(true)
      } else {
        a11yEventsTracker.recycle()
        gestureInjector.setEventTrackingEnabled(false)
        gestureInjector.clearEvents()
      }

      // Re-register sensor listeners

      sensorManager.unregisterListener(sensorListener)

      if (activeSignals.contains(DeviceSignal.SENSOR_ACCELEROMETER)) {
        sensorManager.getDefaultSensor(Sensor.TYPE_ACCELEROMETER)?.let {
          sensorManager.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_GAME)
        }
      }
      if (activeSignals.contains(DeviceSignal.SENSOR_GYROSCOPE)) {
        sensorManager.getDefaultSensor(Sensor.TYPE_GYROSCOPE)?.let {
          sensorManager.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_GAME)
        }
      }
      if (activeSignals.contains(DeviceSignal.SENSOR_MAGNETOMETER)) {
        sensorManager.getDefaultSensor(Sensor.TYPE_MAGNETIC_FIELD)?.let {
          sensorManager.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_GAME)
        }
      }
      if (activeSignals.contains(DeviceSignal.SENSOR_BAROMETER)) {
        sensorManager.getDefaultSensor(Sensor.TYPE_PRESSURE)?.let {
          sensorManager.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_GAME)
        }
      }
      if (activeSignals.contains(DeviceSignal.SENSOR_AMBIENT_TEMP)) {
        sensorManager.getDefaultSensor(Sensor.TYPE_AMBIENT_TEMPERATURE)?.let {
          sensorManager.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_GAME)
        }
      }
      if (activeSignals.contains(DeviceSignal.SENSOR_LIGHT)) {
        sensorManager.getDefaultSensor(Sensor.TYPE_LIGHT)?.let {
          sensorManager.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_GAME)
        }
      }
      if (activeSignals.contains(DeviceSignal.SENSOR_PROXIMITY)) {
        sensorManager.getDefaultSensor(Sensor.TYPE_PROXIMITY)?.let {
          sensorManager.registerListener(sensorListener, it, SensorManager.SENSOR_DELAY_GAME)
        }
      }

      if (activeSignals.contains(DeviceSignal.BATTERY_POWER)) {
        batteryPowerCollector.start()
      } else {
        batteryPowerCollector.stop()
      }
    }
  }

  private val actionHandler = ActionHandler(gestureInjector)

  override fun injectAction(action: Action) {
    try {
      val wm = context.getSystemService(Context.WINDOW_SERVICE) as? WindowManager
      val metrics = DisplayMetrics()
      wm?.defaultDisplay?.getRealMetrics(metrics)
      val width =
        if (screenShareProvider.width() > 0) screenShareProvider.width() else metrics.widthPixels
      val height =
        if (screenShareProvider.height() > 0) screenShareProvider.height() else metrics.heightPixels

      actionHandler.injectAction(action, width, height)
    } catch (e: Exception) {
      Log.e(TAG, "Failed to inject action: ${e.message}", e)
    }
  }

  override fun close() {
    synchronized(this) {
      logcatStreamer?.stop()
      logcatStreamer = null
      sensorManager.unregisterListener(sensorListener)
      batteryPowerCollector.stop()
      a11yTracker.recycle()
    }
  }

  override fun getDeviceState(): DeviceState {
    val nowUs = System.currentTimeMillis() * 1000L
    val wm = context.getSystemService(Context.WINDOW_SERVICE) as? android.view.WindowManager
    val rotation = wm?.defaultDisplay?.rotation ?: 0

    // 1. Gather ScreenShare updates
    try {
      val imgTs = screenShareProvider.latestScreenshotTimestampUs()
      if (imgTs > lastScreenshotTimestampUs) {
        val rawBytes = screenShareProvider.latestScreenshot()
        if (rawBytes != null) {
          val bmp =
            rgbaToBitmap(
              rawBytes,
              screenShareProvider.width(),
              screenShareProvider.height(),
              screenShareProvider.rowStride(),
            )
          screenshotTracker.update(bmp, imgTs)
          lastScreenshotTimestampUs = imgTs
        }
      }
    } catch (e: Exception) {
      Log.w(TAG, "Screenshot not available: ${e.message}")
    }

    // 2. Gather Accessibility updates
    try {
      if (synchronized(this) { activeSignals.contains(DeviceSignal.ACCESSIBILITY_TREE) }) {
        gestureInjector.getRootNode()?.let { root -> a11yTracker.update(root, nowUs) }
      }
      if (synchronized(this) { activeSignals.contains(DeviceSignal.ACCESSIBILITY_EVENTS) }) {
        val newEvents = gestureInjector.popEvents()
        a11yEventsTracker.update(newEvents, nowUs)
      }
      if (synchronized(this) { activeSignals.contains(DeviceSignal.ACTIVE_PACKAGE) }) {
        val pkg = gestureInjector.getActivePackage()
        if (pkg.isNotEmpty()) activePackageTracker.update(pkg, nowUs)
      }
      if (synchronized(this) { activeSignals.contains(DeviceSignal.ACTIVE_ACTIVITY) }) {
        val act = gestureInjector.getActiveActivity()
        if (act.isNotEmpty()) activeActivityTracker.update(act, nowUs)
      }
    } catch (e: Exception) {
      Log.w(TAG, "Accessibility not available: ${e.message}")
    }

    // 3. Gather Logcat updates
    try {
      logcatStreamer?.let { streamer ->
        if (synchronized(this) { activeSignals.contains(DeviceSignal.SYSTEM_LOGS) }) {
          val newLogs = streamer.getNewLogs()
          // Update the tracker unconditionally so value is updated to the latest batch
          // (empty list when no logs occurred) and sequenceId is incremented for downstream delta
          // tracking.
          systemLogsTracker.update(newLogs, nowUs)
        }
      }
    } catch (e: Exception) {
      Log.w(TAG, "Logcat not available: ${e.message}")
    }

    // 4. Gather Battery & Power updates
    try {
      if (synchronized(this) { activeSignals.contains(DeviceSignal.BATTERY_POWER) }) {
        val batteryMetrics = batteryPowerCollector.getLatestMetrics()
        batteryPowerTracker.update(batteryMetrics, nowUs)
      }
    } catch (e: Exception) {
      Log.w(TAG, "BatteryPower metrics not available: ${e.message}")
    }

    // Assemble and return the state
    synchronized(this) {
      return DeviceState(
        screenshot =
          if (activeSignals.contains(DeviceSignal.SCREENSHOT)) screenshotTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        accessibilityRoot =
          if (activeSignals.contains(DeviceSignal.ACCESSIBILITY_TREE))
            a11yTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        accessibilityEvents =
          if (activeSignals.contains(DeviceSignal.ACCESSIBILITY_EVENTS))
            a11yEventsTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        activePackage =
          if (activeSignals.contains(DeviceSignal.ACTIVE_PACKAGE))
            activePackageTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        activeActivity =
          if (activeSignals.contains(DeviceSignal.ACTIVE_ACTIVITY))
            activeActivityTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        systemLogs =
          if (activeSignals.contains(DeviceSignal.SYSTEM_LOGS)) systemLogsTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        runningProcesses = StreamedSignal.empty(), // Stubbed
        deviceSettings = StreamedSignal.empty(), // Stubbed
        accelerometer =
          if (activeSignals.contains(DeviceSignal.SENSOR_ACCELEROMETER))
            accelTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        gyroscope =
          if (activeSignals.contains(DeviceSignal.SENSOR_GYROSCOPE)) gyroTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        magnetometer =
          if (activeSignals.contains(DeviceSignal.SENSOR_MAGNETOMETER))
            magTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        barometer =
          if (activeSignals.contains(DeviceSignal.SENSOR_BAROMETER)) baroTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        ambientTemp =
          if (activeSignals.contains(DeviceSignal.SENSOR_AMBIENT_TEMP))
            tempTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        lightLevel =
          if (activeSignals.contains(DeviceSignal.SENSOR_LIGHT)) lightTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        proximity =
          if (activeSignals.contains(DeviceSignal.SENSOR_PROXIMITY)) proxTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        locationGps = StreamedSignal.empty(), // Stubbed
        heartRate = StreamedSignal.empty(), // Stubbed
        audioOutput =
          if (activeSignals.contains(DeviceSignal.AUDIO_OUTPUT)) audioTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        batteryPower =
          if (activeSignals.contains(DeviceSignal.BATTERY_POWER)) batteryPowerTracker.toStreamedSignal()
          else StreamedSignal.empty(),
        snapshotTimestampUs = nowUs,
        orientation = rotation,
      )
    }
  }

  @Suppress("UseKtx")
  private fun rgbaToBitmap(rgba: ByteArray, width: Int, height: Int, rowStride: Int): Bitmap {
    val bitmap = Bitmap.createBitmap(width, height, Bitmap.Config.ARGB_8888)
    if (rowStride == width * 4 || rowStride <= 0) {
      bitmap.copyPixelsFromBuffer(java.nio.ByteBuffer.wrap(rgba))
    } else {
      val buffer = java.nio.ByteBuffer.wrap(rgba)
      val cleanBuffer = java.nio.ByteBuffer.allocate(width * height * 4)
      val rowBytes = width * 4
      val row = ByteArray(rowBytes)
      for (i in 0 until height) {
        buffer.position(i * rowStride)
        buffer.get(row, 0, rowBytes)
        cleanBuffer.put(row)
      }
      cleanBuffer.rewind()
      bitmap.copyPixelsFromBuffer(cleanBuffer)
    }
    return bitmap
  }

  private class StreamTracker<T> {
    var value: T? = null
      private set

    var timestampUs: Long = 0
      private set

    var sequenceId: Long = 0
      private set

    @Synchronized
    fun update(newValue: T, newTimestampUs: Long) {
      @Suppress("DEPRECATION") (value as? AccessibilityNodeInfo)?.recycle()
      value = newValue
      timestampUs = newTimestampUs
      sequenceId++
    }

    @Synchronized
    fun recycle() {
      @Suppress("DEPRECATION") (value as? AccessibilityNodeInfo)?.recycle()
      value = null
    }

    @Synchronized
    fun toStreamedSignal(): StreamedSignal<T> {
      return StreamedSignal(value, timestampUs, sequenceId)
    }
  }

  private class AudioStreamTracker {
    private val byteBuffer = ByteArrayOutputStream()
    private var sampleRateHz: Int = 44100
    private var channelCount: Int = 2
    private var sampleFormat: String? = null
    private var timestampUs: Long = 0
    private var sequenceId: Long = 0

    @Synchronized
    fun update(frame: AudioFrame, newTimestampUs: Long) {
      if (byteBuffer.size() == 0) {
        timestampUs = newTimestampUs
        sampleRateHz = frame.sampleRateHz
        channelCount = frame.channelCount
        sampleFormat = frame.sampleFormat
      }
      try {
        byteBuffer.write(frame.rawBytes)
      } catch (e: Exception) {
        // Ignored
      }
      sequenceId++
    }

    @Synchronized
    fun toStreamedSignal(): StreamedSignal<AudioFrame> {
      if (byteBuffer.size() == 0) {
        return StreamedSignal(null, timestampUs, sequenceId)
      }
      val accumulatedBytes = byteBuffer.toByteArray()
      byteBuffer.reset()
      val frame =
        AudioFrame(
          rawBytes = accumulatedBytes,
          sampleRateHz = sampleRateHz,
          channelCount = channelCount,
          sampleFormat = sampleFormat,
        )
      return StreamedSignal(frame, timestampUs, sequenceId)
    }
  }

  private class LogcatStreamer {
    private var process: Process? = null
    private var reader: BufferedReader? = null
    private val logQueue = ConcurrentLinkedQueue<String>()
    private var thread: Thread? = null
    private val maxQueueSize = 10000

    @Synchronized
    fun start() {
      if (thread != null) return
      Log.i(TAG, "Starting LogcatStreamer.")
      thread =
        Thread {
            try {
              process = ProcessBuilder("logcat", "-T", "1").start()
              reader = BufferedReader(InputStreamReader(process!!.inputStream))
              var line: String?
              while (!Thread.currentThread().isInterrupted) {
                line = reader?.readLine()
                if (line == null) break
                if (line.isNotEmpty()) {
                  if (logQueue.size >= maxQueueSize) {
                    logQueue.poll()
                  }
                  logQueue.add(line)
                }
              }
              Log.i(TAG, "Logcat reading thread finished.")
            } catch (e: Exception) {
              Log.e(TAG, "Error in LogcatStreamer thread", e)
            } finally {
              cleanup()
            }
          }
          .apply { start() }
    }

    private fun cleanup() {
      try {
        reader?.close()
      } catch (e: Exception) {}
      reader = null
      try {
        process?.destroy()
      } catch (e: Exception) {}
      process = null
    }

    @Synchronized
    fun stop() {
      if (thread == null) return
      Log.i(TAG, "Stopping LogcatStreamer.")

      cleanup()
      thread?.interrupt()

      try {
        thread?.join(5000)
      } catch (e: InterruptedException) {
        Log.w(TAG, "Interrupted while joining LogcatStreamer thread.")
        Thread.currentThread().interrupt()
      } finally {
        thread = null
      }
    }

    fun getNewLogs(maxLogs: Int = 1000): List<String> {
      val logs = mutableListOf<String>()
      while (logs.size < maxLogs) {
        val line = logQueue.poll() ?: break
        logs.add(line)
      }
      return logs
    }
  }

  companion object {
    private const val TAG = "AndroidDeviceEnvImpl"
  }
}
