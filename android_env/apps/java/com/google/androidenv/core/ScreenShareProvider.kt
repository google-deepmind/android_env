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

/** Interface for providing screen dimensions, screenshot bytes, and audio capture. */
interface ScreenShareProvider {
  fun width(): Int

  fun height(): Int

  fun rowStride(): Int

  fun latestScreenshot(): ByteArray?

  fun latestScreenshotTimestampUs(): Long

  fun setAudioListener(listener: ScreenShareService.AudioCaptureListener?)
}

/** Production implementation that delegates to the ScreenShareService singleton. */
class SystemScreenShareProvider : ScreenShareProvider {
  override fun width(): Int = ScreenShareService.getInstance().width()

  override fun height(): Int = ScreenShareService.getInstance().height()

  override fun rowStride(): Int = ScreenShareService.getInstance().rowStride()

  override fun latestScreenshot(): ByteArray? = ScreenShareService.getInstance().latestScreenshot()

  override fun latestScreenshotTimestampUs(): Long =
    ScreenShareService.getInstance().latestScreenshotTimestampUs()

  override fun setAudioListener(listener: ScreenShareService.AudioCaptureListener?) {
    ScreenShareService.audioListener = listener
  }
}
