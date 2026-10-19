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

/**
 * Wraps a signal with its own metadata, acknowledging it is optional and has independent frequency.
 */
data class StreamedSignal<T>(
  // The raw value. Null if unavailable, restricted, or permission denied.
  val value: T?,
  // The exact epoch timestamp when this specific value was captured.
  val timestampUs: Long,
  // Monotonically increasing ID to easily track updates.
  val sequenceId: Long,
) {
  companion object {
    fun <T> empty(): StreamedSignal<T> = StreamedSignal(null, 0, 0)
  }
}
