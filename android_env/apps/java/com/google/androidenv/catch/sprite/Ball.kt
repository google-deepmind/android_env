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
import kotlin.math.ceil
import kotlin.math.sqrt
import kotlin.random.Random
import org.joda.time.Duration

/** Represents a ball that travels down in space with constant speed. */
open class Ball(
  private val maxX: Int,
  private val maxY: Int,
  private val color: Int = Color.WHITE,
  private val radius: Float = 10.0f,
  // `speed`'s unit is in pixels/ms.
  private val speed: Float = 1.0f,
  private val rand: Random = Random.Default,
) : Sprite() {

  // `x` and `y` represent the position of the center of this ball.
  //
  // Valid range [0, maxX]. 0==left, maxX==right.
  private var x: Int = rand.nextInt(maxX)
  // Valid range [0, maxY]. 0==top, maxY==bottom.
  private var y: Int = ceil(radius).toInt()

  private val paint: Paint =
    Paint(Paint.ANTI_ALIAS_FLAG).apply {
      style = Paint.Style.FILL
      color = (this@Ball).color
    }

  /** Returns `true` if this ball intersects the given line [segment]. */
  fun intersects(segment: LineSegment): Boolean {

    /** A vector with two components. */
    data class Vector2D(val u: Int, val v: Int) {
      /** Returns the dot product between two 2D vectors. */
      fun dot(other: Vector2D): Int = u * other.u + v * other.v
    }

    /** Returns the vector representing [p] minus [q]. */
    fun pointDiff(p: Point, q: Point): Vector2D = Vector2D(p.x - q.x, p.y - q.y)

    val direction = pointDiff(segment.p1, segment.p0) // p0 -> p1.
    val centerToP = pointDiff(segment.p0, Point(x, y)) // Ball center -> p0.

    // The `(centerToP + m * direction)` function models all the points in the line segment where
    // the independent variable `m` is a real number in [0,1]. Putting this function into the
    // formula for the circle (x ^ 2 + y ^ 2 = radius ^ 2) gives a quadratic equation
    // (am^2 + bm + c = 0) where:
    // [a] = direction · direction
    // [b] = 2 centerToP · direction
    // [c] = centerToP · centerToP - radius ^ 2
    val a = direction.dot(direction)
    val b = 2 * centerToP.dot(direction)
    val c = centerToP.dot(centerToP) - radius * radius

    val delta = b * b - 4 * a * c
    if (delta < 0)
      return false // No real roots means the (infinite) line does not intersect the ball.

    val d = sqrt(delta)
    val m1 = (-b - d) / (2 * a)
    val m2 = (-b + d) / (2 * a)

    // If a root is in [0,1], the line segment intersects the circumference.
    // If [m1] < 0 and [m2] > 1, the line segment is "within" the circle meaning the circle
    // intersects the infinite line, but not the line segment. In this case, we consider that it
    // touched the ball.
    return (m1 >= 0 && m1 <= 1) || (m2 >= 0 && m2 <= 1) || (m1 < 0 && m2 > 1)
  }

  /** Places the ball at the top of the screen at a random x-coordinate. */
  fun reset() {
    x = rand.nextInt(maxX)
    y = ceil(radius).toInt()
  }

  /** Moves the ball down by [timeDeltaMs]. */
  open fun update(timeDelta: Duration) {
    y += (speed * timeDelta.millis).toInt()
  }

  /** Returns whether the ball is over [maxY]. */
  fun isOutOfBounds(): Boolean = y + radius > maxY || y - radius < 0

  /** Draws this ball in `c`. */
  override fun draw(c: Canvas) {
    c.drawCircle(x.toFloat(), y.toFloat(), radius, paint)
  }
}
