// Copyright 2024 DeepMind Technologies Limited.
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

package com.google.androidenv.accessibilityforwarder

import android.view.accessibility.AccessibilityNodeInfo
import com.google.auto.value.AutoValue

/** Parent and child [AccessibilityNodeInfo] relationship. */
@AutoValue
internal abstract class ParentChildNodePair {
  abstract fun parent(): AccessibilityNodeInfo?

  abstract fun child(): AccessibilityNodeInfo

  /** [ParentChildNodePair] builder. */
  @AutoValue.Builder
  abstract class Builder {
    abstract fun parent(parent: AccessibilityNodeInfo?): Builder

    abstract fun child(child: AccessibilityNodeInfo): Builder

    abstract fun build(): ParentChildNodePair
  }

  companion object {
    @JvmStatic fun builder(): Builder = AutoValue_ParentChildNodePair.Builder()
  }
}
