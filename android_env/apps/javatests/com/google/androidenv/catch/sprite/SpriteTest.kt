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
import org.junit.Test
import org.junit.runner.RunWith
import org.junit.runners.JUnit4
import org.mockito.Mockito.verifyNoInteractions
import org.mockito.kotlin.mock
import org.mockito.kotlin.times
import org.mockito.kotlin.verify

/** Trivial tests to ensure the types in the API are correct. */
@RunWith(JUnit4::class)
class SpriteTest {

  @Test
  fun defaultImplementationDoesNothing() {
    // Arrange.
    val mockCanvas: Canvas = mock()
    val sprite = Sprite()

    // Act.
    sprite.draw(mockCanvas)

    // Assert.
    verifyNoInteractions(mockCanvas) // No methods should be called on the canvas.
  }

  @Test
  fun draw_argumentsAreForwarded() {
    // Arrange.
    val mockSprite: Sprite = mock()
    val mockCanvas: Canvas = mock()

    // Act.
    mockSprite.draw(mockCanvas)

    // Assert.
    verify(mockSprite, times(1)).draw(mockCanvas)
  }
}
