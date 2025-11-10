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

import android.graphics.Canvas
import androidx.test.core.view.MotionEventBuilder
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.androidenv.catch.sprite.Background
import com.google.androidenv.catch.sprite.Ball
import com.google.androidenv.catch.sprite.Paddle
import com.google.common.truth.Truth.assertThat
import java.time.Duration
import java.time.Instant
import kotlin.random.Random
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.any
import org.mockito.kotlin.atLeast
import org.mockito.kotlin.atMost
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.mock
import org.mockito.kotlin.spy
import org.mockito.kotlin.times
import org.mockito.kotlin.verify

@RunWith(AndroidJUnit4::class)
class GameLogicTest {

  @Test
  fun run_ballIsMissed() {
    // Arrange.
    val width = 123
    val height = 33
    val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 37 }
    val game =
      GameLogic(
        rand = mockRandom,
        width = width,
        height = height,
        ball = Ball(maxX = width, maxY = height, radius = 5.0f, rand = mockRandom),
        paddle = Paddle(maxX = width, y = height, width = 3, height = 2),
      )
    game.reset()
    game.handleTouch(
      MotionEventBuilder.newBuilder().setPointer(/* x= */ 12.0f, /* y= */ 31.0f).build()
    )

    // Act.
    val outcome = game.run() // Ball falls at x==37, ev.x==12 so ball is missed.

    // Assert.
    assertThat(outcome).isEqualTo(false)
  }

  @Test
  fun run_ballIsCaught() {
    // Arrange.
    val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 53 }
    val game = GameLogic(rand = mockRandom, width = 321, height = 47)
    game.reset()
    game.handleTouch(
      MotionEventBuilder.newBuilder().setPointer(/* x= */ 53.0f, /* y= */ 43.0f).build()
    )

    // Act.
    val outcome = game.run() // Ball falls at x==53, ev.x==53 so ball is caught.

    // Assert.
    assertThat(outcome).isEqualTo(true)
  }

  @Test
  fun run_resetAllowsMultipleGamesToBePlayedWithASingleObjectAndDoesNotHang() {
    // Arrange.
    val mockRandom: Random = mock()
    val game = GameLogic(width = 101, height = 59, rand = mockRandom)

    // Act.
    repeat(17) {
      game.reset()
      val unused = game.run() // Ignore the outcome since we only care about run() terminating.
    }

    // Assert.
    // [rand.nextInt()] should be called once at construction and then 17 times for [reset()].
    verify(mockRandom, times(18)).nextInt(any())
  }

  @Test
  fun run_inASeparateThread() {
    // Arrange.
    val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 23 }
    val game = GameLogic(rand = mockRandom, width = 321, height = 89)
    game.reset()
    game.handleTouch(
      MotionEventBuilder.newBuilder().setPointer(/* x= */ 23.0f, /* y= */ 29.0f).build()
    )
    var outcome: Boolean = false

    class MyThread(val g: GameLogic, var outcome: Boolean) : Thread() {
      public override fun run() {
        outcome = g.run()
      }
    }
    val someThread = MyThread(game, outcome)

    // Act.
    someThread.start() // Ball falls at x==23, ev.x==23 so ball is caught.
    someThread.join()

    // Assert.
    assertThat(outcome).isEqualTo(true)
  }

  @Test
  fun run_fpsLeadstoApproximatelyNumberOfElapsedTimeAndUpdateCalls() {
    // Arrange.
    val width = 123
    val height = 300
    val ball = spy(Ball(maxX = width, maxY = height, speed = 2.0f, radius = 1.0f))
    val game = GameLogic(fps = 100, width = width, height = height, ball = ball)
    game.reset()

    // Act.
    val start = Instant.now()
    val unused = game.run()
    val end = Instant.now()

    // Assert.
    val elapsed = Duration.between(start, end)
    // The ball should take around `height / speed = 150` milliseconds to reach the bottom. Due to
    // timing non-determinism, we accept values between 100 and 200.
    assertThat(elapsed.toMillis()).isAtLeast(100L)
    assertThat(elapsed.toMillis()).isAtMost(200L)
    // At fps==100, we expect [update()] to be called every `1000 / 100 = 10` milliseconds. We
    // expect [elapsed] to be around 150ms (checked above) which should be around `150 / 10 = 15`
    // calls, so to account for timing non-determinism we accept between 5 and 25 calls.
    verify(ball, atLeast(5)).update(any())
    verify(ball, atMost(25)).update(any())
  }

  @Test
  fun render_drawCanBeCalledMultipleTimesWithinASingleRun() {
    // Arrange.
    val width = 321
    val height = 89
    val mockCanvas: Canvas = mock()
    val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 23 }
    val background = spy(Background())
    val paddle = spy(Paddle())
    val ball = spy(Ball(maxX = width, maxY = height))
    val game =
      GameLogic(
        rand = mockRandom,
        width = width,
        height = height,
        background = background,
        ball = ball,
        paddle = paddle,
      )
    game.reset()
    game.handleTouch(
      MotionEventBuilder.newBuilder().setPointer(/* x= */ 23.0f, /* y= */ 29.0f).build()
    )

    class MyThread(val g: GameLogic) : Thread() {
      public override fun run() {
        val unused = g.run()
      }
    }
    val someThread = MyThread(game)

    // Act.
    someThread.start()
    repeat(11) { game.render(mockCanvas) }
    someThread.join()

    // Assert.
    verify(background, times(11)).draw(mockCanvas)
    verify(ball, times(11)).draw(mockCanvas)
    verify(paddle, times(11)).draw(mockCanvas)
  }
}
