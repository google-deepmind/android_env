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

/** A thread that continuously runs the game logic, resetting after each internal [run()]. */
class GameLogicThread(private val game: GameLogic, private val loggingTag: String) : Thread() {

  /** Whether this thread should continuously run. */
  private var shouldRun: Boolean = true
  /** A counter of game runs. */
  private var counter: Int = 0

  /**
   * Lets the current [run()] iteration complete then break exit this [Thread].
   *
   * Notice that [shouldRun] cannot have a private getter with a public setter (please see
   * https://youtrack.jetbrains.com/issue/KT-3110 for details), hence this public function. Also
   * notice that we cannot call this function [stop()] since it would shadow [Thread.stop()].
   */
  public fun finish() {
    shouldRun = false
  }

  /** Continuously runs the [game] until [finish()] is called. */
  public override fun run() {
    while (shouldRun) {
      game.reset()
      Log.i(loggingTag, "${counter++} - ${game.run()}")
    }
  }
}
