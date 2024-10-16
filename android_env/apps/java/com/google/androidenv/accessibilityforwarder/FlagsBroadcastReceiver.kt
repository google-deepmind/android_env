// Copyright 2024 DeepMind Technologies Limited.
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

package com.google.androidenv.accessibilityforwarder

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import android.util.Log

/** Broadcast receiver responsible for enabling or disabling flags. */
class FlagsBroadcastReceiver() : BroadcastReceiver() {

  override fun onReceive(context: Context?, intent: Intent?) {
    val action = intent?.action
    Log.i(TAG, "Received broadcast intent with action: " + action)
    when (action) {
      ACTION_ENABLE_ACCESSIBILITY_TREE_LOGS -> {
        Log.i(TAG, "Enabling Accessibility Tree logging.")
        LogFlags.logAccessibilityTree = true
      }
      ACTION_DISABLE_ACCESSIBILITY_TREE_LOGS -> {
        Log.i(TAG, "Disabling Accessibility Tree logging.")
        LogFlags.logAccessibilityTree = false
      }
      ACTION_SET_GRPC -> {
        // The Android Emulator uses 10.0.2.2 as a redirect to the workstation's IP. Most often the
        // gRPC server will be running locally so it makes sense to use this as the default value.
        // See https://developer.android.com/studio/run/emulator-networking#networkaddresses.
        val host = intent.getStringExtra("host") ?: "10.0.2.2"
        // The TCP port to connect. If <=0 gRPC is disabled.
        val port = intent.getIntExtra("port", 0)
        Log.i(TAG, "Setting gRPC endpoint to ${host}:${port}.")
        LogFlags.grpcHost = host
        LogFlags.grpcPort = port
      }
      else -> Log.w(TAG, "Unknown action: ${action}")
    }
  }

  companion object {
    private const val TAG = "FlagsBroadcastReceiver"
    private const val ACTION_ENABLE_ACCESSIBILITY_TREE_LOGS =
      "accessibility_forwarder.intent.action.ENABLE_ACCESSIBILITY_TREE_LOGS"
    private const val ACTION_DISABLE_ACCESSIBILITY_TREE_LOGS =
      "accessibility_forwarder.intent.action.DISABLE_ACCESSIBILITY_TREE_LOGS"
    private const val ACTION_SET_GRPC = "accessibility_forwarder.intent.action.SET_GRPC"
  }
}
