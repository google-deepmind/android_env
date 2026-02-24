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

import android.graphics.Canvas
import android.view.SurfaceHolder
import java.time.Duration

/** A thread that continuously renders the game logic onto a surface. */
class RenderThread(private val surfaceHolder: SurfaceHolder, private val fps: Int = 60) : Thread() {

  /** Whether this thread should continuously run. */
  private var shouldRun: Boolean = true
  /** How long to sleep at each [run()] iteration. */
  private val sleepTime: Duration = Duration.ofMillis((1000.0 / fps).toLong())
  /** The class responsible for issuing rendering commands to the canvas. */
  var game: GameLogic? = null

  /**
   * Runs the current game logic [run()] to completion.
   *
   * Notice that [shouldRun] cannot have a private getter with a public setter (please see
   * https://youtrack.jetbrains.com/issue/KT-3110 for details), hence this public function. Also
   * notice that we cannot call this function [stop()] since it would shadow [Thread.stop()].
   */
  public fun finish() {
    shouldRun = false
  }

  /** Continuously renders the [game] onto [surfaceHolder]. */
  public override fun run() {
    while (shouldRun) {
      if (surfaceHolder.surface?.isValid() ?: false) {
        val c: Canvas = surfaceHolder.lockCanvas()
        game?.render(c)
        surfaceHolder.unlockCanvasAndPost(c)
      }
      Thread.sleep(sleepTime.toMillis())
    }
  }
}
