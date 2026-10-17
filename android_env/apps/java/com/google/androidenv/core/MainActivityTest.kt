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
import android.content.Context
import android.content.Intent
import android.provider.Settings
import android.view.ViewGroup
import android.widget.Button
import android.widget.LinearLayout
import android.widget.TextView
import androidx.test.core.app.ActivityScenario
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.Robolectric
import org.robolectric.Shadows.shadowOf
import org.robolectric.annotation.Config

@RunWith(AndroidJUnit4::class)
@Config(sdk = [26])
class MainActivityTest {

  private val context = ApplicationProvider.getApplicationContext<Context>()

  @Before
  fun setUp() {
    setAccessibilityEnabled(false)
  }

  @After
  fun tearDown() {
    setAccessibilityEnabled(false)
  }

  private fun setAccessibilityEnabled(enabled: Boolean) {
    val value =
      if (enabled) {
        "${context.packageName}/${InputService::class.java.name}"
      } else {
        ""
      }
    Settings.Secure.putString(
      context.contentResolver,
      Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES,
      value,
    )
  }

  @Test
  fun onCreate_accessibilityDisabled_showsDisabledStatusAndDisablesButton() {
    ActivityScenario.launch(MainActivity::class.java).use { scenario ->
      scenario.onActivity { activity ->
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        val layout = content.getChildAt(0) as LinearLayout
        val statusTextView = layout.getChildAt(0) as TextView
        val serverButton = layout.getChildAt(1) as Button

        assertThat(statusTextView.text.toString()).contains("Accessibility Service disabled")
        assertThat(serverButton.isEnabled).isFalse()
      }
    }
  }

  @Test
  fun onCreate_accessibilityEnabled_showsReadyStatusAndEnablesButton() {
    setAccessibilityEnabled(true)
    ActivityScenario.launch(MainActivity::class.java).use { scenario ->
      scenario.onActivity { activity ->
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        val layout = content.getChildAt(0) as LinearLayout
        val statusTextView = layout.getChildAt(0) as TextView
        val serverButton = layout.getChildAt(1) as Button

        assertThat(statusTextView.text.toString()).isEqualTo("Status: Ready")
        assertThat(serverButton.isEnabled).isTrue()
        assertThat(serverButton.text.toString()).isEqualTo("Start WebSocket Server")
      }
    }
  }

  @Test
  fun clickStartServer_launchesScreenCaptureIntent() {
    setAccessibilityEnabled(true)
    ActivityScenario.launch(MainActivity::class.java).use { scenario ->
      scenario.onActivity { activity ->
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        val layout = content.getChildAt(0) as LinearLayout
        val serverButton = layout.getChildAt(1) as Button

        serverButton.performClick()

        val shadowActivity = shadowOf(activity)
        val startedIntent = shadowActivity.nextStartedActivityForResult
        assertThat(startedIntent).isNotNull()
      }
    }
  }

  @Test
  fun screenCaptureResult_ok_startsScreenShareService() {
    setAccessibilityEnabled(true)
    ActivityScenario.launch(MainActivity::class.java).use { scenario ->
      scenario.onActivity { activity ->
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        val layout = content.getChildAt(0) as LinearLayout
        val serverButton = layout.getChildAt(1) as Button

        serverButton.performClick()

        val shadowActivity = shadowOf(activity)
        val startedIntent = shadowActivity.nextStartedActivityForResult

        val resultData = Intent().apply { putExtra("EXTRA_DATA", "dummy") }
        shadowActivity.receiveResult(startedIntent.intent, Activity.RESULT_OK, resultData)

        val serviceIntent = shadowActivity.nextStartedService
        assertThat(serviceIntent).isNotNull()
        assertThat(serviceIntent.component?.className)
          .isEqualTo(ScreenShareService::class.java.name)
        assertThat(serviceIntent.getStringExtra("ACTION")).isEqualTo("START")
        assertThat(serviceIntent.getIntExtra("RESULT_CODE", Activity.RESULT_CANCELED))
          .isEqualTo(Activity.RESULT_OK)
      }
    }
  }

  @Test
  fun screenCaptureResult_canceled_doesNotStartServiceAndShowsError() {
    setAccessibilityEnabled(true)
    ActivityScenario.launch(MainActivity::class.java).use { scenario ->
      scenario.onActivity { activity ->
        val content = activity.findViewById<ViewGroup>(android.R.id.content)
        val layout = content.getChildAt(0) as LinearLayout
        val statusTextView = layout.getChildAt(0) as TextView
        val serverButton = layout.getChildAt(1) as Button

        serverButton.performClick()

        val shadowActivity = shadowOf(activity)
        val startedIntent = shadowActivity.nextStartedActivityForResult

        shadowActivity.receiveResult(startedIntent.intent, Activity.RESULT_CANCELED, null)

        val serviceIntent = shadowActivity.nextStartedService
        assertThat(serviceIntent).isNull()
        assertThat(statusTextView.text.toString()).contains("Screen Capture permission denied")
      }
    }
  }

  @Test
  fun intentCommand_startServer_launchesScreenCapture() {
    setAccessibilityEnabled(true)
    val intent =
      Intent(context, MainActivity::class.java).apply { putExtra("COMMAND", "START_SERVER") }
    ActivityScenario.launch<MainActivity>(intent).use { scenario ->
      scenario.onActivity { activity ->
        val shadowActivity = shadowOf(activity)
        val startedIntent = shadowActivity.nextStartedActivityForResult
        assertThat(startedIntent).isNotNull()
      }
    }
  }

  @Test
  fun intentCommand_stop_stopsService() {
    setAccessibilityEnabled(true)
    val intent = Intent(context, MainActivity::class.java).apply { putExtra("COMMAND", "STOP") }
    ActivityScenario.launch<MainActivity>(intent).use { scenario ->
      scenario.onActivity { activity ->
        val shadowActivity = shadowOf(activity)
        val serviceIntent = shadowActivity.nextStartedService
        assertThat(serviceIntent).isNotNull()
        assertThat(serviceIntent.component?.className)
          .isEqualTo(ScreenShareService::class.java.name)
        assertThat(serviceIntent.getStringExtra("ACTION")).isEqualTo("STOP")
      }
    }
  }

  @Test
  fun onNewIntent_handlesCommand() {
    setAccessibilityEnabled(true)
    val controller = Robolectric.buildActivity(MainActivity::class.java)
    val activity = controller.create().resume().get()

    val newIntent = Intent(activity, MainActivity::class.java).apply { putExtra("COMMAND", "STOP") }
    controller.newIntent(newIntent)

    val shadowActivity = shadowOf(activity)
    val serviceIntent = shadowActivity.nextStartedService
    assertThat(serviceIntent).isNotNull()
    assertThat(serviceIntent.getStringExtra("ACTION")).isEqualTo("STOP")
    controller.destroy()
  }
}
