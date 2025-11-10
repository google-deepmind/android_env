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
import android.graphics.Rect
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.Suite
import org.mockito.kotlin.argumentCaptor
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.robolectric.ParameterizedRobolectricTestRunner

@RunWith(Suite::class)
@Suite.SuiteClasses(
  PaddleTest.ConstructorTests::class,
  PaddleTest.MoveTests::class,
  PaddleTest.XSetterTests::class,
  PaddleTest.DrawTests::class,
)
class PaddleTest {

  @RunWith(AndroidJUnit4::class)
  class ConstructorTests() {

    @Test
    fun x_initialValueShouldBeAtCenter() {
      with(Paddle(maxX = 30)) { assertThat(x).isEqualTo(15) }
      with(Paddle(maxX = 31)) { assertThat(x).isEqualTo(15) }
    }

    @Test
    fun topLeft_correspondsToGivenValues() {
      with(Paddle(width = 10, height = 6, maxX = 40, y = 33)) {
        assertThat(topLeft()).isEqualTo(Point(x = 15, y = 30))
      }
    }

    @Test
    fun topRight_correspondsToGivenValues() {
      with(Paddle(width = 10, height = 6, maxX = 40, y = 33)) {
        assertThat(topRight()).isEqualTo(Point(x = 25, y = 30))
      }
    }
  }

  @RunWith(ParameterizedRobolectricTestRunner::class)
  class MoveTests(private val p: ParamPack) {

    @Test
    fun move_expectedDestination() {
      // Arrange.
      with(Paddle(maxX = 50)) {
        // Act.
        move(deltaX = p.displacement)

        // Assert.
        assertThat(x).isEqualTo(p.expectedX)
      }
    }

    data class ParamPack(val displacement: Int, val expectedX: Int)

    companion object {
      @JvmStatic
      @ParameterizedRobolectricTestRunner.Parameters(name = "param = {0}")
      fun parameters() =
        listOf(
          // Initial position is x==25.
          ParamPack(displacement = 10, expectedX = 35),
          ParamPack(displacement = -10, expectedX = 15),
          ParamPack(displacement = 0, expectedX = 25),
          // Going beyond the left and right walls should clamp the values to 0 and 50.
          ParamPack(displacement = -26, expectedX = 0),
          ParamPack(displacement = 26, expectedX = 50),
        )
    }
  }

  @RunWith(ParameterizedRobolectricTestRunner::class)
  class XSetterTests(private val p: ParamPack) {

    @Test
    fun xSetter_expectedDestination() {
      // Arrange.
      with(Paddle(maxX = 50)) {
        // Act.
        x = p.target

        // Assert.
        assertThat(x).isEqualTo(p.expectedX)
      }
    }

    data class ParamPack(val target: Int, val expectedX: Int)

    companion object {
      @JvmStatic
      @ParameterizedRobolectricTestRunner.Parameters(name = "param = {0}")
      fun parameters() =
        listOf(
          // Initial position is x==25.
          ParamPack(target = 0, expectedX = 0),
          ParamPack(target = 15, expectedX = 15),
          ParamPack(target = 25, expectedX = 25),
          ParamPack(target = 35, expectedX = 35),
          ParamPack(target = 50, expectedX = 50),
          // Going beyond the left and right walls should clamp the values to 0 and 50.
          ParamPack(target = -1, expectedX = 0),
          ParamPack(target = 51, expectedX = 50),
        )
    }
  }

  @RunWith(AndroidJUnit4::class)
  class DrawTests() {

    @Test
    fun draw_initialPosition() {
      // Arrange.
      val mockCanvas: Canvas = mock()
      val rectCaptor = argumentCaptor<Rect>()
      val paintCaptor = argumentCaptor<Paint>()
      with(Paddle(color = Color.RED, width = 100, height = 20, maxX = 300, y = 400)) {
        // Act.
        draw(mockCanvas)

        // Assert.
        assertThat(x).isEqualTo(150)
        verify(mockCanvas).drawRect(rectCaptor.capture(), paintCaptor.capture())
        with(rectCaptor.lastValue) {
          assertThat(bottom).isEqualTo(400 + 10)
          assertThat(top).isEqualTo(400 - 10)
          assertThat(left).isEqualTo(150 - 50)
          assertThat(right).isEqualTo(150 + 50)
        }
      }
    }

    @Test
    fun draw_afterMove() {
      // Arrange.
      val mockCanvas: Canvas = mock()
      val rectCaptor = argumentCaptor<Rect>()
      val paintCaptor = argumentCaptor<Paint>()
      with(Paddle(color = Color.RED, width = 100, height = 20, maxX = 300, y = 400)) {
        // Act.
        move(50)
        draw(mockCanvas)

        // Assert.
        assertThat(x).isEqualTo(200)
        verify(mockCanvas).drawRect(rectCaptor.capture(), paintCaptor.capture())
        with(rectCaptor.lastValue) {
          assertThat(bottom).isEqualTo(400 + 10)
          assertThat(top).isEqualTo(400 - 10)
          assertThat(left).isEqualTo(200 - 50)
          assertThat(right).isEqualTo(200 + 50)
        }
        with(paintCaptor.lastValue) {
          assertThat(color).isEqualTo(Color.RED)
          assertThat(style).isEqualTo(Paint.Style.FILL)
        }
      }
    }
  }
}
