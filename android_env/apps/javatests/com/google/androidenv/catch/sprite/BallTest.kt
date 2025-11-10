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

package com.google.androidenv.catch.sprite

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import java.time.Duration
import kotlin.random.Random
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Suite
import org.mockito.kotlin.any
import org.mockito.kotlin.argumentCaptor
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.eq
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.robolectric.ParameterizedRobolectricTestRunner

@RunWith(Suite::class)
@Suite.SuiteClasses(
  BallTest.UpdateAndResetTests::class,
  BallTest.ColorIntTest::class,
  BallTest.CheckBoundsTest::class,
  BallTest.IntersectsTest::class,
)
class BallTest {

  @RunWith(AndroidJUnit4::class)
  class UpdateAndResetTests() {
    @Test
    fun isOutOfBounds_initialState_isFalse() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.
      with(Ball(maxX = 100, maxY = 100, radius = 3.0f, speed = 1.0f, rand = mockRandom)) {
        assertThat(isOutOfBounds()).isEqualTo(false)
      }
    }

    @Test
    fun isOutOfBounds_initialState_isTrueIfRadiusExceedsMaxY() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.
      with(Ball(maxX = 100, maxY = 10, radius = 11.0f, speed = 1.0f, rand = mockRandom)) {
        assertThat(isOutOfBounds()).isEqualTo(true)
      }
    }

    @Test
    fun isOutOfBounds_initialState_isFalseIfRadiusExceedsOnlyMaxX() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.
      with(Ball(maxX = 10, maxY = 100, radius = 11.0f, speed = 1.0f, rand = mockRandom)) {
        assertThat(isOutOfBounds()).isEqualTo(false)
      }
    }

    @Test
    fun update_zeroDurationDoesNotMove_withinBounds() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.
      with(Ball(maxX = 100, maxY = 100, radius = 3.0f, speed = 1.0f, rand = mockRandom)) {
        // Act.
        update(Duration.ofMillis(0)) // The ball should not move.

        // Assert.
        assertThat(isOutOfBounds()).isEqualTo(false) // It should still be within the bounds.
      }
    }

    @Test
    fun update_zeroDurationDoesNotMove_outOfBounds() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.
      with(Ball(maxX = 100, maxY = 100, radius = 3.0f, speed = 1.0f, rand = mockRandom)) {
        update(Duration.ofMillis(110)) // Place the ball out of bounds.
        assertThat(isOutOfBounds()).isEqualTo(true)

        // Act.
        update(Duration.ofMillis(0)) // The ball should not move.

        // Assert.
        assertThat(isOutOfBounds()).isEqualTo(true) // It should still be out of bounds.
      }
    }

    @Test
    fun update_negativeDurationsMovesUp() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.
      with(Ball(maxX = 100, maxY = 100, radius = 3.0f, speed = 1.0f, rand = mockRandom)) {
        update(Duration.ofMillis(30)) // Move the ball down 30 pixels.
        assertThat(isOutOfBounds()).isEqualTo(false)

        // Act.
        update(Duration.ofMillis(-50)) // Move the ball _up_ 50 pixels.

        // Assert.
        assertThat(isOutOfBounds()).isEqualTo(true) // Now it should be out-of-bounds.
      }
    }

    @Test
    fun update_singleThrow() {
      // Ensures that a complete throw of a ball with radius==3.0f and maxY=100 behaves as expected.
      // [isOutOfBounds()] should return [false] for the first (100-3.0f-3.0f)=94 [update()] calls,
      // but [true] afterwards.

      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.
      with(Ball(maxX = 100, maxY = 100, radius = 3.0f, speed = 1.0f, rand = mockRandom)) {
        // Act.
        repeat(94) {
          update(Duration.ofMillis(1))
          assertThat(isOutOfBounds()).isEqualTo(false)
        }
        update(Duration.ofMillis(1))

        // Assert.
        assertThat(isOutOfBounds()).isEqualTo(true)
      }
    }

    @Test
    fun intersects_afterUpdate() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.

      // Act & Assert.
      with(Ball(maxX = 100, maxY = 100, radius = 3.0f, speed = 1.0f, rand = mockRandom)) {
        assertThat(intersects(LineSegment(Point(40, 0), Point(60, 0)))).isEqualTo(true)
        update(Duration.ofMillis(1))
        assertThat(intersects(LineSegment(Point(40, 0), Point(60, 0)))).isEqualTo(false)
      }
    }

    @Test
    fun reset_intersectsInitialPositionShouldBeTrue() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.

      with(Ball(maxX = 100, maxY = 100, radius = 3.0f, speed = 1.0f, rand = mockRandom)) {
        // Act.
        assertThat(intersects(LineSegment(Point(40, 0), Point(60, 0)))).isEqualTo(true)

        update(Duration.ofMillis(1)) // Move the ball 1 pixels down.
        assertThat(intersects(LineSegment(Point(40, 0), Point(60, 0))))
          .isEqualTo(false) // Segment is now outside of the ball.

        reset() // Resetting should move the ball up again.

        // Assert.
        assertThat(intersects(LineSegment(Point(40, 0), Point(60, 0))))
          .isEqualTo(true) // Segment is now inside of the ball.
      }
    }

    @Test
    fun reset_differentInitialXCoordinates() {
      // Arrange.
      val ball: Ball = Ball(maxX = 100, maxY = 100, radius = 3.0f)

      // Act.
      var pointInside: Boolean = false
      var pointOutside: Boolean = false
      while (!pointInside || !pointOutside) {
        if (ball.intersects(LineSegment(Point(45, 0), Point(55, 0)))) {
          pointInside = true
        } else {
          pointOutside = true
        }
        ball.reset() // Sample a new initial position for the ball.
      }

      // Assert.
      // Eventually after many initial positions the ball should satisfy both conditions.
      assertThat(pointInside).isEqualTo(true)
      assertThat(pointOutside).isEqualTo(true)
    }
  }

  @RunWith(ParameterizedRobolectricTestRunner::class)
  class ColorIntTest(private val c: Int) {

    @Test
    fun draw_customBallColors() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 37 }
      val mockCanvas: Canvas = mock()
      val paintCaptor = argumentCaptor<Paint>()
      val ball: Ball = Ball(maxX = 50, maxY = 80, radius = 1.23f, color = c, rand = mockRandom)

      // Act.
      ball.draw(mockCanvas)

      // Assert.
      verify(mockCanvas).drawCircle(eq(37.0f), eq(2.0f), eq(1.23f), paintCaptor.capture())
      with(paintCaptor.lastValue) {
        assertThat(color).isEqualTo(c)
        assertThat(style).isEqualTo(Paint.Style.FILL)
      }
    }

    companion object {
      @JvmStatic
      @ParameterizedRobolectricTestRunner.Parameters(name = "color = {0}")
      fun parameters() = listOf(0, 255, -1, 13579, 2468, 12384173, Color.WHITE, Color.BLUE)
    }
  }

  @RunWith(ParameterizedRobolectricTestRunner::class)
  class CheckBoundsTest(private val p: ParamPack) {

    @Test
    fun intersects_checkBounds() {
      // Arrange.
      val mockRandom: Random =
        mock() { on { nextInt(any()) } doReturn p.maxX / 2 } // Horizontal middle.

      // Act.
      val ball: Ball = Ball(maxX = p.maxX, maxY = p.maxY, radius = p.radius, rand = mockRandom)

      // Assert.
      assertThat(ball.intersects(LineSegment(Point(p.x - 1, p.y), Point(p.x + 1, p.y))))
        .isEqualTo(p.expected)
    }

    data class ParamPack(
      val maxX: Int,
      val maxY: Int,
      val radius: Float,
      val x: Int,
      val y: Int,
      val expected: Boolean,
    )

    companion object {
      @JvmStatic
      @ParameterizedRobolectricTestRunner.Parameters(name = "param = {0}")
      fun parameters() =
        listOf(
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 0,
            y = 0,
            expected = false,
          ), // Ball to the right of `x`.
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 39,
            y = 0,
            expected = false,
          ), // Ball to the right of `x`.
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 40,
            y = 10,
            expected = true,
          ), // Ball contains `x`.
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 50,
            y = 0,
            expected = true,
          ), // Ball contains `x`.
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 60,
            y = 10,
            expected = true,
          ), // Ball contains `x`.
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 61,
            y = 0,
            expected = false,
          ), // Ball to the left of `x`.
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 100,
            y = 0,
            expected = false,
          ), // Ball to the left of `x`.
          ParamPack(
            maxX = 100,
            maxY = 100,
            radius = 10.0f,
            x = 50,
            y = 21,
            expected = false,
          ), // Ball above `y`.
        )
    }
  }

  @RunWith(ParameterizedRobolectricTestRunner::class)
  class IntersectsTest(private val p: ParamPack) {

    @Test
    fun intersects_ballAtx50y10radius10() {
      // Arrange.
      val mockRandom: Random = mock() { on { nextInt(any()) } doReturn 50 } // Horizontal middle.

      // Act.
      val ball: Ball = Ball(maxX = 100, maxY = 100, radius = 10.0f, rand = mockRandom)

      // Assert.
      assertThat(ball.intersects(p.segment)).isEqualTo(p.expected)
    }

    data class ParamPack(val segment: LineSegment, val expected: Boolean)

    companion object {
      @JvmStatic
      @ParameterizedRobolectricTestRunner.Parameters(name = "param = {0}")
      fun parameters() =
        listOf(
          ParamPack(
            segment = LineSegment(Point(50, 10), Point(80, 40)),
            expected = true,
          ), // Segment that starts at the center of the ball so it should always intersect.
          ParamPack(
            segment = LineSegment(Point(49, 0), Point(51, 0)),
            expected = true,
          ), // Tangential segment that touches the bottom of the ball.
          ParamPack(
            segment = LineSegment(Point(40, 5), Point(65, 7)),
            expected = true,
          ), // Segment longer than diameter, touching the circumference twice.
          ParamPack(
            segment = LineSegment(Point(42, 2), Point(58, 1)),
            expected = true,
          ), // Segment shorter than diameter, touching the circumference twice.
          ParamPack(
            segment = LineSegment(Point(44, 4), Point(54, 3)),
            expected = true,
          ), // Segment shorter than diameter, fully inside the circle, not touching the
          // circumference.
          ParamPack(
            segment = LineSegment(Point(35, 4), Point(54, 3)),
            expected = true,
          ), // Segment that touches the circumference once "from the left".
          ParamPack(
            segment = LineSegment(Point(54, 7), Point(67, 13)),
            expected = true,
          ), // Segment that touches the circumference once "from the right".
          ParamPack(
            segment = LineSegment(Point(36, 7), Point(45, 0)),
            expected = false,
          ), // Segment "to the left of the ball". No intersection.
          ParamPack(
            segment = LineSegment(Point(58, -3), Point(60, 3)),
            expected = false,
          ), // Segment "to the right of the ball". No intersection.
        )
    }
  }
}
