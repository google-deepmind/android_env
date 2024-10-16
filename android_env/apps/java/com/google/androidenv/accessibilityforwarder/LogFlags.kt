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

/**
 * Controls global settings in AccessibilityForwarder.
 *
 * Please note that this class is not thread safe.
 */
object LogFlags {
  // Whether to log the accessibility tree.
  var logAccessibilityTree: Boolean = false
  // How frequent to emit a11y trees (in milliseconds).
  var a11yTreePeriodMs: Long = 100

  // The gRPC server to connect to. (Only available if grpcPort>0).
  var grpcHost: String = ""
  // If >0 this represents the gRPC port number to connect to.
  var grpcPort: Int = 0
}
