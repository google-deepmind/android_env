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

import android.accessibilityservice.AccessibilityService
import android.annotation.SuppressLint
import android.app.Activity
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.provider.Settings
import android.util.Log
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.activity.ComponentActivity
import androidx.activity.result.ActivityResult
import androidx.activity.result.contract.ActivityResultContracts

/**
 * Main activity that orchestrates permissions (Accessibility and MediaProjection) and starts either
 * the WebSocket server (PoC 1) or the In-Process Agent (PoC 2). Can be controlled via Intents for
 * headless automation.
 */
@SuppressLint("SetTextI18n")
class MainActivity : ComponentActivity() {

  private lateinit var statusTextView: TextView
  private lateinit var serverButton: Button

  private enum class PendingAction {
    NONE,
    START_SERVER,
  }

  private var pendingAction = PendingAction.NONE
  private var isResumed = false
  private var pendingCommand: String? = null

  private val screenCaptureLauncher =
    registerForActivityResult(ActivityResultContracts.StartActivityForResult()) { result ->
      onScreenCaptureResult(result)
    }

  override fun onCreate(savedInstanceState: Bundle?) {
    Log.e("CRITICAL_DEBUG", "MainActivity onCreate called!!!")
    super.onCreate(savedInstanceState)

    if (savedInstanceState != null) {
      val actionName = savedInstanceState.getString("PENDING_ACTION")
      if (actionName != null) {
        pendingAction = PendingAction.valueOf(actionName)
        Log.e("CRITICAL_DEBUG", "Restored pendingAction: $pendingAction")
      }
    }

    // Programmatic UI
    val layout =
      LinearLayout(this).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(50, 50, 50, 50)
      }
    statusTextView =
      TextView(this).apply {
        text = "Status: Idle"
        textSize = 18f
        layoutParams =
          LinearLayout.LayoutParams(
              LinearLayout.LayoutParams.MATCH_PARENT,
              LinearLayout.LayoutParams.WRAP_CONTENT,
            )
            .apply { setMargins(0, 0, 0, 50) }
      }
    serverButton =
      Button(this).apply {
        text = "Start WebSocket Server"
        layoutParams =
          LinearLayout.LayoutParams(
              LinearLayout.LayoutParams.MATCH_PARENT,
              LinearLayout.LayoutParams.WRAP_CONTENT,
            )
            .apply { setMargins(0, 0, 0, 20) }
        setOnClickListener { triggerAction(PendingAction.START_SERVER) }
      }
    layout.addView(statusTextView)
    layout.addView(serverButton)
    setContentView(layout)

    handleIntent(intent)
  }

  override fun onResume() {
    super.onResume()
    isResumed = true
    updateAccessibilityStatus()
    updateServerUIStatus()
    Log.e("CRITICAL_DEBUG", "onResume: pendingCommand=$pendingCommand")
    pendingCommand?.let {
      executeCommand(it)
      pendingCommand = null
    }
  }

  override fun onPause() {
    super.onPause()
    isResumed = false
  }

  override fun onNewIntent(intent: Intent) {
    super.onNewIntent(intent)
    handleIntent(intent)
  }

  override fun onSaveInstanceState(outState: Bundle) {
    super.onSaveInstanceState(outState)
    outState.putString("PENDING_ACTION", pendingAction.name)
    Log.e("CRITICAL_DEBUG", "Saved pendingAction: ${pendingAction.name}")
  }

  private fun handleIntent(intent: Intent?) {
    val command = intent?.getStringExtra("COMMAND")
    Log.i(TAG, "Received command: $command, isResumed=$isResumed")
    if (command != null) {
      intent.removeExtra("COMMAND")
      if (isResumed) {
        executeCommand(command)
      } else {
        pendingCommand = command
        Log.e("CRITICAL_DEBUG", "Set pendingCommand to $command")
      }
    }
  }

  private fun executeCommand(command: String) {
    Log.e("CRITICAL_DEBUG", "executeCommand: $command")
    when (command) {
      "START_SERVER" -> triggerAction(PendingAction.START_SERVER)
      "STOP" -> stopWebSocketServer()
    }
  }

  private fun updateAccessibilityStatus() {
    val enabled = isAccessibilityServiceEnabled(this, InputService::class.java)
    if (!enabled) {
      statusTextView.text =
        "Status: Accessibility Service disabled.\nPlease enable 'AndroidEnv Input Service' in Settings."
      serverButton.isEnabled = false
    } else {
      statusTextView.text = "Status: Ready"
      serverButton.isEnabled = true
    }
  }

  private fun updateServerUIStatus() {
    if (!isAccessibilityServiceEnabled(this, InputService::class.java)) {
      return
    }
    val isRunning =
      try {
        ScreenShareService.getInstance().isServerRunning()
      } catch (e: IllegalStateException) {
        false
      }
    if (isRunning) {
      statusTextView.text =
        "Server: Running on ws://localhost:8000\nAccessibility: ACTIVE\nScreenCapture: ACTIVE"
      serverButton.text = "Stop WebSocket Server"
      serverButton.setOnClickListener { stopWebSocketServer() }
    } else {
      statusTextView.text = "Status: Ready"
      serverButton.text = "Start WebSocket Server"
      serverButton.setOnClickListener { triggerAction(PendingAction.START_SERVER) }
    }
  }

  private fun triggerAction(action: PendingAction) {
    if (!isAccessibilityServiceEnabled(this, InputService::class.java)) {
      Log.w(TAG, "Cannot trigger action: Accessibility disabled.")
      return
    }

    Log.e("CRITICAL_DEBUG", "triggerAction: action=$action, current pendingAction=$pendingAction")
    pendingAction = action
    val manager = getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
    screenCaptureLauncher.launch(manager.createScreenCaptureIntent())
  }

  private fun onScreenCaptureResult(result: ActivityResult) {
    Log.e(
      "CRITICAL_DEBUG",
      "onScreenCaptureResult: result=${result.resultCode}, pendingAction=$pendingAction",
    )
    if (result.resultCode != Activity.RESULT_OK) {
      statusTextView.text = "Status: Screen Capture permission denied."
      pendingAction = PendingAction.NONE
      return
    }
    val data = result.data ?: return

    val serviceIntent =
      Intent(this, ScreenShareService::class.java).apply {
        putExtra("ACTION", "START")
        putExtra("DATA", data)
        putExtra("RESULT_CODE", result.resultCode)
      }
    try {
      startForegroundService(serviceIntent)
      statusTextView.post { updateServerUIStatus() }
    } catch (e: Exception) {
      statusTextView.text = "Error: Failed to start screen capture: ${e.message}"
      Log.e(TAG, "Failed to start ScreenShareService", e)
    } finally {
      pendingAction = PendingAction.NONE
    }
  }

  private fun stopWebSocketServer() {
    stopScreenShareService()
    statusTextView.text = "Status: Ready"
    serverButton.text = "Start WebSocket Server"
    serverButton.setOnClickListener { triggerAction(PendingAction.START_SERVER) }
  }

  private fun stopScreenShareService() {
    val serviceIntent =
      Intent(this, ScreenShareService::class.java).apply { putExtra("ACTION", "STOP") }
    startService(serviceIntent)
  }

  private fun isAccessibilityServiceEnabled(
    context: Context,
    service: Class<out AccessibilityService>,
  ): Boolean {
    val expectedId = "${context.packageName}/${service.name}"
    val enabledServicesSetting =
      Settings.Secure.getString(
        context.contentResolver,
        Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
      ) ?: return false
    val colonSplitter = android.text.TextUtils.SimpleStringSplitter(':')
    colonSplitter.setString(enabledServicesSetting)
    while (colonSplitter.hasNext()) {
      val componentNameString = colonSplitter.next()
      if (componentNameString.equals(expectedId, ignoreCase = true)) {
        return true
      }
    }
    return false
  }

  companion object {
    private const val TAG = "MainActivity"
  }
}
