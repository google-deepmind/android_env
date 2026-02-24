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

package com.google.androidenv.catch

import android.content.Intent
import android.util.Log
import androidx.test.ext.junit.rules.ActivityScenarioRule
import androidx.test.ext.junit.runners.AndroidJUnit4
import java.lang.reflect.Method
import org.junit.Before
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.junit.rules.ExpectedLogMessagesRule

@RunWith(AndroidJUnit4::class)
class MainActivityTest {
  @get:Rule(order = 0) val activityScenarioRule = ActivityScenarioRule(MainActivity::class.java)
  @get:Rule(order = 1) val expectedLogMessagesRule = ExpectedLogMessagesRule()

  @Before
  fun setUp() {
    expectedLogMessagesRule.expectLogMessage(Log.INFO, TAG, "MainActivity::onCreate()")
  }

  @Test
  fun surfaceChanged_logsStartsGame() {
    activityScenarioRule.scenario.onActivity { activity ->
      // Arrange.
      val surfaceView = activity.findViewById<android.view.SurfaceView>(R.id.surfaceView)
      val surfaceHolder = surfaceView.holder

      // Act - Trigger the surfaceChanged callback with positive width and height.
      activity.surfaceChanged(surfaceHolder, 0, 100, 200)

      // Assert.
      expectedLogMessagesRule.expectLogMessage(Log.INFO, TAG, "MainActivity::surfaceChanged()")
      expectedLogMessagesRule.expectLogMessage(Log.INFO, TAG, "MainActivity::startGame()")
    }
  }

  @Test
  fun onNewIntent_logsStartsGame_errorsOnUninitializedWidthOrHeight() {
    // Arrange.
    val newIntent = Intent()
    // Find the onNewIntent method using reflection
    val onNewIntentMethod: Method =
      MainActivity::class.java.getDeclaredMethod("onNewIntent", Intent::class.java)
    // Enable access to protected method
    onNewIntentMethod.isAccessible = true

    activityScenarioRule.scenario.onActivity { activity ->
      // Act - Invoke the onNewIntent method using reflection.
      onNewIntentMethod.invoke(activity, newIntent)

      // Assert.
      expectedLogMessagesRule.expectLogMessage(Log.INFO, TAG, "MainActivity::onNewIntent()")
      expectedLogMessagesRule.expectLogMessage(Log.INFO, TAG, "MainActivity::startGame()")
      // In this test case where we don't call surfaceChanged(), default width and height
      // are -1 and should trigger this error to prevent Ball from initializing
      // with invalid negative values, since nextInt() expects a positive number.
      expectedLogMessagesRule.expectLogMessage(
        Log.ERROR,
        TAG,
        "MainActivity::startGame() - Width or height not initialized yet.",
      )
    }
  }

  companion object {
    private const val TAG = "AndroidRLTask"
  }
}
