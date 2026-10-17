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

package com.google.androidenv.core

import android.content.Intent
import android.hardware.display.VirtualDisplay
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Handler
import android.view.Surface

/** Wrapper for [VirtualDisplay] to facilitate testing. */
interface VirtualDisplayWrapper {
  fun release()
}

/** Real implementation of [VirtualDisplayWrapper]. */
class RealVirtualDisplayWrapper(private val virtualDisplay: VirtualDisplay) :
  VirtualDisplayWrapper {
  override fun release() {
    virtualDisplay.release()
  }
}

/** Wrapper for [MediaProjection] to facilitate testing. */
interface MediaProjectionWrapper {
  fun registerCallback(callback: MediaProjection.Callback, handler: Handler?)

  fun createVirtualDisplay(
    name: String,
    width: Int,
    height: Int,
    dpi: Int,
    flags: Int,
    surface: Surface?,
    callback: VirtualDisplay.Callback?,
    handler: Handler?,
  ): VirtualDisplayWrapper?

  fun stop()

  fun getActualMediaProjection(): MediaProjection
}

/** Real implementation of [MediaProjectionWrapper]. */
class RealMediaProjectionWrapper(private val mediaProjection: MediaProjection) :
  MediaProjectionWrapper {
  override fun registerCallback(callback: MediaProjection.Callback, handler: Handler?) {
    mediaProjection.registerCallback(callback, handler)
  }

  override fun createVirtualDisplay(
    name: String,
    width: Int,
    height: Int,
    dpi: Int,
    flags: Int,
    surface: Surface?,
    callback: VirtualDisplay.Callback?,
    handler: Handler?,
  ): VirtualDisplayWrapper? {
    val vd =
      mediaProjection.createVirtualDisplay(
        name,
        width,
        height,
        dpi,
        flags,
        surface,
        callback,
        handler,
      )
    return vd?.let { RealVirtualDisplayWrapper(it) }
  }

  override fun stop() {
    mediaProjection.stop()
  }

  override fun getActualMediaProjection(): MediaProjection = mediaProjection
}

/** Wrapper for [MediaProjectionManager] to facilitate testing. */
interface MediaProjectionManagerWrapper {
  fun getMediaProjection(resultCode: Int, resultData: Intent): MediaProjectionWrapper?
}

/** Real implementation of [MediaProjectionManagerWrapper]. */
class RealMediaProjectionManagerWrapper(private val manager: MediaProjectionManager) :
  MediaProjectionManagerWrapper {
  override fun getMediaProjection(resultCode: Int, resultData: Intent): MediaProjectionWrapper? {
    val mp = manager.getMediaProjection(resultCode, resultData)
    return mp?.let { RealMediaProjectionWrapper(it) }
  }
}
