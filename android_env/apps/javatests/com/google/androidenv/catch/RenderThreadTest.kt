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
import android.view.Surface
import android.view.SurfaceHolder
import androidx.test.ext.junit.runners.AndroidJUnit4
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.Mockito.verifyNoInteractions
import org.mockito.kotlin.any
import org.mockito.kotlin.atLeast
import org.mockito.kotlin.atMost
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify

@RunWith(AndroidJUnit4::class)
class RenderThreadTest {

  @Test
  fun run_finishBeforeStartResultsInNoRendering() {
    // Arrange.
    val surfaceHolder: SurfaceHolder = mock()
    val renderThread = RenderThread(surfaceHolder = surfaceHolder, fps = 1000)
    val game: GameLogic = mock()
    renderThread.game = game

    // Act.
    renderThread.finish()
    renderThread.start()

    // Assert.
    verifyNoInteractions(game)
    verifyNoInteractions(surfaceHolder)
  }

  @Test
  fun run_startResultsInSomeRendering() {
    // Arrange.
    val canvas: Canvas = mock()
    val surface: Surface = mock() { on { isValid() } doReturn true }
    val surfaceHolder: SurfaceHolder =
      mock() {
        on { getSurface() } doReturn surface
        on { lockCanvas() } doReturn canvas
      }
    val renderThread = RenderThread(surfaceHolder = surfaceHolder, fps = 1000)
    val game: GameLogic = mock()
    renderThread.game = game

    // Act.
    renderThread.start()
    Thread.sleep(/* millis= */ 500) // Sleep for at least one loop iteration.
    renderThread.finish()

    // Assert.
    verify(surfaceHolder, atLeast(1)).surface
    verify(surfaceHolder, atLeast(1)).lockCanvas()
    verify(surfaceHolder, atLeast(1)).unlockCanvasAndPost(any())
    verify(game, atLeast(1)).render(canvas)
  }

  @Test
  fun run_finishStopsRendering() {
    // Arrange.
    val canvas: Canvas = mock()
    val surface: Surface = mock() { on { isValid() } doReturn true }
    val surfaceHolder: SurfaceHolder =
      mock() {
        on { getSurface() } doReturn surface
        on { lockCanvas() } doReturn canvas
      }
    val renderThread = RenderThread(surfaceHolder = surfaceHolder, fps = 20)
    val game: GameLogic = mock()
    renderThread.game = game

    // Act.
    renderThread.start()
    Thread.sleep(/* millis= */ 500) // Sleep for around 10 iterations
    renderThread.finish()
    Thread.sleep(/* millis= */ 500) // Sleep some more to ensure nothing runs after.

    // Assert.
    verify(surfaceHolder, atLeast(1)).surface
    verify(surfaceHolder, atLeast(1)).lockCanvas()
    verify(surfaceHolder, atLeast(1)).unlockCanvasAndPost(any())
    // We expect [game.render()] to be executed for around 500 / (1000 / 20 = 50) = 10 times. To
    // allow for some timing non-determinism we allow it to execute up to 15 times, but not more
    // than that since [renderThread.finish()] should stop the thread from calling it.
    verify(game, atLeast(1)).render(canvas)
    verify(game, atMost(15)).render(canvas)
  }

  @Test
  fun run_expectedFramesPerSecond() {
    // Arrange.
    val canvas: Canvas = mock()
    val surface: Surface = mock() { on { isValid() } doReturn true }
    val surfaceHolder: SurfaceHolder =
      mock() {
        on { getSurface() } doReturn surface
        on { lockCanvas() } doReturn canvas
      }
    val renderThread = RenderThread(surfaceHolder = surfaceHolder, fps = 5)
    val game: GameLogic = mock()
    renderThread.game = game

    // Act.
    renderThread.start()
    Thread.sleep(/* millis= */ 2000) // Sleep for around 10 loop iterations.
    renderThread.finish()

    // Assert.
    verify(surfaceHolder, atLeast(1)).surface
    verify(surfaceHolder, atLeast(1)).lockCanvas()
    verify(surfaceHolder, atLeast(1)).unlockCanvasAndPost(any())
    // We expect [game.render()] to be called around 2000ms / 5fps = 10 times but to account for
    // timing non-determinism we allow ±4 iterations.
    verify(game, atLeast(6)).render(canvas)
    verify(game, atMost(14)).render(canvas)
  }
}
