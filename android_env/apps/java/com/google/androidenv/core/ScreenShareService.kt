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

import android.app.Activity
import android.app.Notification
import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Context
import android.content.Intent
import android.content.res.Resources
import android.graphics.PixelFormat
import android.hardware.display.DisplayManager
import android.media.AudioAttributes
import android.media.AudioFormat
import android.media.AudioPlaybackCaptureConfiguration
import android.media.AudioRecord
import android.media.Image
import android.media.ImageReader
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.IBinder
import android.util.DisplayMetrics
import android.util.Log
import android.view.WindowManager
import androidx.annotation.RequiresApi
import androidx.core.content.IntentCompat

/** A Service to project the screen and capture screenshots in the background. */
class ScreenShareService : Service() {

  private var mediaProjection: MediaProjectionWrapper? = null
  private var virtualDisplay: VirtualDisplayWrapper? = null
  private var displayDensity: Int = -1
  private var displayWidth: Int = -1
  private var displayHeight: Int = -1
  private var displayRowStride: Int = -1
  private var imageReader: ImageReader? = null
  private var server: AndroidDeviceEnvWebSocketServer? = null

  lateinit var mediaProjectionManagerWrapper: MediaProjectionManagerWrapper

  private var audioRecord: AudioRecord? = null
  private var audioThread: Thread? = null
  @Volatile private var isRecording = false

  @Volatile private var latestImage: ByteArray? = null
  @Volatile private var latestImageTimestampUs: Long = 0

  @Volatile var activeVideoMime: String? = null
  @Volatile var activeVideoWidth: Int = -1
  @Volatile var activeVideoHeight: Int = -1

  interface ScreenCaptureListener {
    fun onFrameCaptured(
      rgbaBytes: ByteArray,
      width: Int,
      height: Int,
      rowStride: Int,
      timestampUs: Long,
    )
  }

  @Volatile var frameListener: ScreenCaptureListener? = null

  interface AudioCaptureListener {
    fun onAudioCaptured(
      rawBytes: ByteArray,
      sampleRateHz: Int,
      channelCount: Int,
      sampleFormat: Int,
    )
  }

  override fun onBind(intent: Intent): IBinder? = null

  override fun onCreate() {
    Log.i(TAG, "ScreenShareService::onCreate()")
    instance = this
    if (!::mediaProjectionManagerWrapper.isInitialized) {
      mediaProjectionManagerWrapper =
        RealMediaProjectionManagerWrapper(
          getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
        )
    }
  }

  override fun onStartCommand(intent: Intent, flags: Int, startId: Int): Int {
    Log.i(TAG, "onStartCommand()")

    val action = intent.getStringExtra("ACTION")
    if (action == "START") {
      Log.i(TAG, "Starting MediaProjection")
      val notification = getNotification(this)
      startForeground(notification.first, notification.second)

      val data: Intent? = IntentCompat.getParcelableExtra(intent, "DATA", Intent::class.java)
      val resultCode = intent.getIntExtra("RESULT_CODE", Activity.RESULT_CANCELED)
      startProjection(data, resultCode)
      startWebSocketServer()
    } else if (action == "STOP") {
      Log.i(TAG, "Stopping MediaProjection")
      stopWebSocketServer()
      stopProjection()
      stopSelf()
    } else {
      stopSelf()
    }

    return START_NOT_STICKY
  }

  fun latestScreenshot(): ByteArray? = latestImage

  fun latestScreenshotTimestampUs(): Long = latestImageTimestampUs

  fun getMediaProjection(): MediaProjectionWrapper? = mediaProjection

  fun width(): Int = displayWidth

  fun height(): Int = displayHeight

  fun density(): Int = displayDensity

  fun rowStride(): Int = displayRowStride

  private fun startProjection(data: Intent?, resultCode: Int) {
    if (data == null) return
    if (mediaProjection != null) return

    val proj = mediaProjectionManagerWrapper.getMediaProjection(resultCode, data) ?: return
    mediaProjection = proj

    val wm = getSystemService(Context.WINDOW_SERVICE) as? WindowManager
    val metrics = DisplayMetrics()
    wm?.defaultDisplay?.getRealMetrics(metrics)

    displayDensity =
      if (metrics.densityDpi > 0) metrics.densityDpi
      else Resources.getSystem().displayMetrics.densityDpi
    displayWidth =
      if (metrics.widthPixels > 0) metrics.widthPixels
      else Resources.getSystem().displayMetrics.widthPixels
    displayHeight =
      if (metrics.heightPixels > 0) metrics.heightPixels
      else Resources.getSystem().displayMetrics.heightPixels

    proj.registerCallback(
      object : MediaProjection.Callback() {
        override fun onStop() {
          Log.i(TAG, "MediaProjection stopped")
          virtualDisplay?.release()
          imageReader?.setOnImageAvailableListener(null, null)
          stopAudioRecordingInternal()
          mediaProjection = null
        }
      },
      handler = null,
    )
    createVirtualDisplay()
    if (android.os.Build.VERSION.SDK_INT >= 29) {
      startAudioRecording(proj)
    }
  }

  private fun stopProjection() {
    isRecording = false
    audioThread?.interrupt()
    mediaProjection?.stop()
    mediaProjection = null
  }

  @RequiresApi(29)
  private fun startAudioRecording(proj: MediaProjectionWrapper) {
    if (isRecording) return
    isRecording = true
    audioThread =
      Thread {
          val config =
            AudioPlaybackCaptureConfiguration.Builder(proj.getActualMediaProjection())
              .addMatchingUsage(AudioAttributes.USAGE_MEDIA)
              .addMatchingUsage(AudioAttributes.USAGE_GAME)
              .build()

          val sampleRate = 44100
          val channelConfig = AudioFormat.CHANNEL_IN_STEREO
          val audioFormat = AudioFormat.ENCODING_PCM_16BIT
          val bufferSize = AudioRecord.getMinBufferSize(sampleRate, channelConfig, audioFormat)

          if (bufferSize == AudioRecord.ERROR_BAD_VALUE || bufferSize == AudioRecord.ERROR) {
            Log.e(TAG, "Invalid buffer size: $bufferSize")
            return@Thread
          }

          try {
            val record =
              AudioRecord.Builder()
                .setAudioFormat(
                  AudioFormat.Builder()
                    .setEncoding(audioFormat)
                    .setSampleRate(sampleRate)
                    .setChannelMask(channelConfig)
                    .build()
                )
                .setAudioPlaybackCaptureConfig(config)
                .setBufferSizeInBytes(bufferSize)
                .build()

            audioRecord = record
            record.startRecording()
            Log.i(TAG, "Audio recording started.")

            val audioBuffer = ByteArray(bufferSize)
            while (isRecording && !Thread.currentThread().isInterrupted) {
              val read = record.read(audioBuffer, 0, bufferSize)
              if (read > 0) {
                val data = audioBuffer.copyOf(read)
                audioListener?.onAudioCaptured(data, sampleRate, 2, audioFormat)
              } else if (read < 0) {
                Log.e(TAG, "Error reading audio data: $read")
                break
              }
            }
          } catch (e: SecurityException) {
            Log.e(TAG, "SecurityException starting audio recording", e)
          } catch (e: Exception) {
            Log.e(TAG, "Exception in audio recording thread", e)
          } finally {
            stopAudioRecordingInternal()
          }
        }
        .apply { start() }
  }

  private fun stopAudioRecordingInternal() {
    isRecording = false
    try {
      audioRecord?.stop()
    } catch (e: Exception) {
      // Ignore
    }
    try {
      audioRecord?.release()
    } catch (e: Exception) {
      // Ignore
    }
    audioRecord = null
    Log.i(TAG, "Audio recording stopped.")
  }

  private fun createVirtualDisplay() {
    imageReader =
      ImageReader.newInstance(
        displayWidth,
        displayHeight,
        PixelFormat.RGBA_8888,
        /* maxImages = */ 2,
      )
    val flags =
      DisplayManager.VIRTUAL_DISPLAY_FLAG_OWN_CONTENT_ONLY or
        DisplayManager.VIRTUAL_DISPLAY_FLAG_PUBLIC
    virtualDisplay =
      mediaProjection?.createVirtualDisplay(
        "androidenv_screen",
        displayWidth,
        displayHeight,
        displayDensity,
        flags,
        imageReader?.surface,
        null,
        null,
      )
    imageReader?.setOnImageAvailableListener(onImageAvailableListener, null)
  }

  private val onImageAvailableListener = ImageReader.OnImageAvailableListener { reader ->
    val image: Image = reader?.acquireLatestImage() ?: return@OnImageAvailableListener
    try {
      val plane = image.planes[0]
      displayRowStride = plane.rowStride
      val buffer = plane.buffer
      val bytes = ByteArray(buffer.capacity())
      buffer.get(bytes)
      latestImage = bytes
      latestImageTimestampUs = System.nanoTime() / 1000
      frameListener?.onFrameCaptured(
        bytes,
        displayWidth,
        displayHeight,
        displayRowStride,
        latestImageTimestampUs,
      )
    } finally {
      image.close()
    }
  }

  private fun getNotification(context: Context): Pair<Int, Notification> {
    createNotificationChannel(context)
    val notification = createNotification(context)
    val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    manager.notify(NOTIFICATION_ID, notification)
    return Pair(NOTIFICATION_ID, notification)
  }

  private fun createNotificationChannel(context: Context) {
    val channel =
      NotificationChannel(
        NOTIFICATION_CHANNEL_ID,
        NOTIFICATION_CHANNEL_NAME,
        NotificationManager.IMPORTANCE_LOW,
      )
    channel.lockscreenVisibility = Notification.VISIBILITY_PRIVATE
    val manager = context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    manager.createNotificationChannel(channel)
  }

  private fun createNotification(context: Context): Notification {
    val builder = Notification.Builder(context, NOTIFICATION_CHANNEL_ID)
    // Use system drawable to avoid custom resource dependency
    builder.setSmallIcon(android.R.drawable.ic_menu_camera)
    builder.setContentTitle("AndroidEnv")
    builder.setContentText("Screen Recording Active")
    builder.setOngoing(true)
    builder.setCategory(Notification.CATEGORY_SERVICE)
    builder.setShowWhen(true)
    return builder.build()
  }

  fun isServerRunning(): Boolean = server != null

  private fun startWebSocketServer() {
    if (server != null) return
    try {
      Log.i(TAG, "Starting WebSocket server on port 8000...")
      val env = AndroidDeviceEnvImpl(applicationContext)
      val srv = AndroidDeviceEnvWebSocketServer(env, 8000)
      srv.start()
      server = srv
      Log.i(TAG, "WebSocket server started successfully.")
    } catch (e: Exception) {
      Log.e(TAG, "Failed to start WebSocket server", e)
    }
  }

  private fun stopWebSocketServer() {
    Log.i(TAG, "Stopping WebSocket server...")
    server?.stop()
    server = null
    Log.i(TAG, "WebSocket server stopped.")
  }

  override fun onDestroy() {
    Log.i(TAG, "ScreenShareService::onDestroy()")
    super.onDestroy()
    stopWebSocketServer()
    instance = null
  }

  companion object {
    private const val TAG = "ScreenShareService"
    private const val NOTIFICATION_ID = 492459162
    private const val NOTIFICATION_CHANNEL_ID = "com.androidenv"
    private const val NOTIFICATION_CHANNEL_NAME = "com.androidenv"

    @Volatile private var instance: ScreenShareService? = null

    @Volatile
    var audioListener: AudioCaptureListener? = null
      set(value) {
        field = value
        Log.i("ScreenShareService", "audioListener set to $value")
      }

    fun getInstance(): ScreenShareService {
      return instance ?: throw IllegalStateException("ScreenShareService not started.")
    }
  }
}
