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
import android.view.MotionEvent
import com.google.androidenv.catch.sprite.Background
import com.google.androidenv.catch.sprite.Ball
import com.google.androidenv.catch.sprite.LineSegment
import com.google.androidenv.catch.sprite.Paddle
import java.time.Duration
import java.time.Instant
import kotlin.random.Random

/** The class that contains the game logic. */
open class GameLogic(
  // Expected number of frames per second.
  fps: Int = 60,
  // Pseudo random number generator.
  private val rand: Random = Random.Default,
  // Width and height of the game in pixels.
  private val width: Int,
  private val height: Int,
  // UI objects in the game.
  private var background: Background = Background(),
  private var ball: Ball = Ball(maxX = width, maxY = height, rand = rand),
  private var paddle: Paddle = Paddle(maxX = width, y = height),
) {

  private val sleepTime: Duration = Duration.ofMillis((1000.0 / fps).toLong())

  /** Reinitializes the state of the game. */
  // Need to make this open to allow for testing.
  open fun reset() {
    this.ball.reset()
  }

  /** Runs one "throw" of a [ball] that needs to be caught by the [paddle]. */
  // Need to make this open to allow for testing.
  open fun run(): Boolean {
    var lastTimestamp = Instant.now()
    do {
      Thread.sleep(sleepTime.toMillis())
      val now = Instant.now()
      val interval = Duration.between(lastTimestamp, now)
      lastTimestamp = now
      ball.update(interval)
    } while (!ball.isOutOfBounds())

    return ball.intersects(LineSegment(paddle.topLeft(), paddle.topRight()))
  }

  /** Processes a user event (e.g. a touchscreen event) and updates the [paddle] accordingly. */
  fun handleTouch(event: MotionEvent) {
    paddle.x = event.x.toInt()
  }

  /** Renders the game on [c]. */
  open fun render(c: Canvas) {
    background.draw(c)
    ball.draw(c)
    paddle.draw(c)
  }
}
