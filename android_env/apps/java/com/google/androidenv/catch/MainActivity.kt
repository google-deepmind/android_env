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

import android.app.Activity
import android.content.Intent
import android.graphics.Color
import android.os.Bundle
import android.util.Log
import android.view.SurfaceHolder
import android.view.SurfaceView
import android.view.View
import android.view.Window
import com.google.androidenv.catch.sprite.Background
import com.google.androidenv.catch.sprite.Ball
import com.google.androidenv.catch.sprite.Paddle

/** The activity that allows users to play the RL game of Catch. */
class MainActivity() : Activity(), SurfaceHolder.Callback {

  private var surfaceView: SurfaceView? = null
  private var renderThread: RenderThread? = null
  private var gameLogicThread: GameLogicThread? = null

  private val fps: Int = 60
  private var gameCounter: Int = 0
  private var width: Int = -1
  private var height: Int = -1

  private var extras: Bundle? = null

  // [Activity] overrides.

  /** Initializes the Android [View] and sets up callbacks. */
  override fun onCreate(savedInstanceState: Bundle?) {
    super.onCreate(savedInstanceState)
    Log.i(TAG, "MainActivity::onCreate()")
    requestWindowFeature(Window.FEATURE_NO_TITLE)
    setContentView(R.layout.main)
    val surface: SurfaceView? = findViewById(R.id.surfaceView)
    if (surface == null) throw Exception("Could not create SurfaceView. Aborting...")

    surface.visibility = View.VISIBLE
    surface.holder.addCallback(this)
    surfaceView = surface
    extras = intent?.extras
  }

  override fun onNewIntent(intent: Intent?) {
    super.onNewIntent(intent)
    Log.i(TAG, "MainActivity::onNewIntent()")
    extras = intent?.extras
    startGame()
  }

  // [SurfaceHolder.Callback] overrides.

  override fun surfaceCreated(holder: SurfaceHolder) {
    Log.i(TAG, "MainActivity::surfaceCreated()")
    renderThread = RenderThread(surfaceHolder = holder, fps = fps).also { it.start() }
  }

  override fun surfaceChanged(holder: SurfaceHolder, format: Int, width: Int, height: Int) {
    Log.i(TAG, "MainActivity::surfaceChanged()")
    this.width = width
    this.height = height
    startGame()
  }

  override fun surfaceDestroyed(holder: SurfaceHolder) {
    Log.i(TAG, "MainActivity::surfaceDestroyed()")
    renderThread?.finish()
    renderThread?.join()
    gameLogicThread?.finish()
    gameLogicThread?.join()
  }

  private fun startGame() {
    Log.i(TAG, "MainActivity::startGame()")
    if (width <= 0 || height <= 0) {
      Log.e(TAG, "MainActivity::startGame() - Width or height not initialized yet.")
      return
    }
    val backgroundColor = Color.parseColor(extras?.getString("backgroundColor") ?: "BLACK")
    val ballColor = Color.parseColor(extras?.getString("ballColor") ?: "WHITE")
    val ballRadius = extras?.getFloat("ballRadius", 10.0f) ?: 10.0f
    val ballSpeed = extras?.getFloat("ballSpeed", 0.2f) ?: 0.2f
    val paddleColor = Color.parseColor(extras?.getString("paddleColor") ?: "WHITE")
    val paddleWidth = extras?.getInt("paddleWidth", 80) ?: 80
    val paddleHeight = extras?.getInt("paddleHeight", 10) ?: 10
    Log.i(TAG, "MainActivity::startGame() - extras bundle: $extras")
    val game =
      GameLogic(
        width = width,
        height = height,
        fps = fps,
        background = Background(color = backgroundColor),
        ball =
          Ball(
            maxX = width,
            maxY = height,
            color = ballColor,
            radius = ballRadius,
            speed = ballSpeed,
          ),
        paddle =
          Paddle(
            color = paddleColor,
            width = paddleWidth,
            height = paddleHeight,
            maxX = width,
            y = (height - paddleHeight / 2),
          ),
      )

    // Stop the previous game logic thread if it's running.
    gameLogicThread?.finish()
    gameLogicThread?.join()

    // Create and start the new GameLogicThread, passing the game instance.
    gameLogicThread = GameLogicThread(game, TAG).also { it.start() }

    // Pass the same game instance to the render thread.
    renderThread?.game = game

    surfaceView?.setOnTouchListener(
      // Suppress warning for ClickableViewAccessibility since click handling
      // is not within an OnTouchListener.
      @SuppressWarnings("ClickableViewAccessibility")
      View.OnTouchListener { _, motionEvent ->
        game.handleTouch(motionEvent)
        true
      }
    )
  }

  companion object {
    private const val TAG = "AndroidRLTask"
  }
}
