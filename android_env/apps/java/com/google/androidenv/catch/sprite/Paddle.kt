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

package com.google.androidenv.catch.sprite

import android.graphics.Canvas
import android.graphics.Color
import android.graphics.Paint
import android.graphics.Rect
import kotlin.ranges.coerceIn

/** Represents a paddle to hit/catch a falling ball. */
open class Paddle(
  private val color: Int = Color.WHITE,
  // Width and height in pixels.
  private val width: Int = 80,
  private val height: Int = 10,
  // maxX is the maximum X value for the center of the paddle.
  private val maxX: Int = 100,
  // The vertical position of the center of this paddle in pixels.
  val y: Int = 100,
) : Sprite() {

  // Memoize a few things to make [draw()] a bit faster.
  private val halfH = height / 2
  private val halfW = width / 2
  private val paint =
    Paint(Paint.ANTI_ALIAS_FLAG).apply {
      style = Paint.Style.FILL
      color = (this@Paddle).color
    }

  // The horizontal center of the paddle.
  var x: Int = maxX / 2 // Start in the middle.
    set(value) {
      field = value.coerceIn(0, maxX)
    }

  /** Returns the (x,y) coordinates of the top-left corner. */
  fun topLeft(): Point = Point(x - halfW, y - halfH)

  /** Returns the (x,y) coordinates of the top-right corner. */
  fun topRight(): Point = Point(x + halfW, y - halfH)

  fun move(deltaX: Int) {
    x += deltaX
  }

  override fun draw(c: Canvas) {
    val rect =
      Rect().apply {
        bottom = y + halfH
        top = y - halfH
        left = x - halfW
        right = x + halfW
      }
    c.drawRect(rect, paint)
  }
}
