// Copyright 2025 DeepMind Technologies Limited.
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

import android.util.Log
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import org.junit.Rule
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.atLeastOnce
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.robolectric.junit.rules.ExpectedLogMessagesRule

@RunWith(AndroidJUnit4::class)
class GameLogicThreadTest {

  // Rule to assert log messages, taken as a reference from MainActivityTest.kt
  @get:Rule val expectedLogMessagesRule = ExpectedLogMessagesRule()

  private val mockGame: GameLogic = mock()
  private val testTag = "TestAndroidRLTask"

  @Test
  fun run_iteratesGameAndLogs() {
    // Arrange
    val gameLogicThread = GameLogicThread(mockGame, testTag)

    // Act
    gameLogicThread.start()
    Thread.sleep(100) // Allow time for the thread to execute at least once.
    gameLogicThread.finish()
    gameLogicThread.join() // Wait for the thread to terminate.

    // Assert
    // Verify that the game's core methods were called at least once.
    verify(mockGame, atLeastOnce()).reset()
    verify(mockGame, atLeastOnce()).run()
    // Expect the log message from the run() loop.
    // The mock 'game.run()' returns false by default.
    expectedLogMessagesRule.expectLogMessage(Log.INFO, testTag, "0 - false")
  }

  @Test
  fun finish_stopsTheThread() {
    // Arrange
    val gameLogicThread = GameLogicThread(mockGame, testTag)

    // Act
    gameLogicThread.start()
    // Let it run for a moment before stopping it.
    Thread.sleep(50)
    gameLogicThread.finish()
    gameLogicThread.join()

    // Assert
    assertThat(gameLogicThread.isAlive).isFalse()
  }
}
