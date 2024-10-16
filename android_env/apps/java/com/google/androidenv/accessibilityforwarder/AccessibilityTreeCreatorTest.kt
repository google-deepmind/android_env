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
import android.view.accessibility.AccessibilityWindowInfo
import kotlin.test.assertEquals
import org.junit.Test
import org.junit.runner.RunWith
import org.robolectric.RobolectricTestRunner
import org.robolectric.Shadows.shadowOf

@RunWith(RobolectricTestRunner::class)
class AccessibilityTreeCreatorTest {

  @Test
  fun buildForest_buildsAccessibilityForestCorrectly() {
    val creator = AccessibilityTreeCreator()

    val forest = creator.buildForest(mutableListOf(createWindowInfo()))

    assertEquals(forest.windowsCount, 1)
    assertEquals(forest.getWindows(0).tree.nodesCount, 3)
    var rootNode: AndroidAccessibilityNodeInfo? = null
    var checkableNode: AndroidAccessibilityNodeInfo? = null
    val nodes = forest.getWindows(0).tree.nodesList
    for (i in nodes.size - 1 downTo 0) {
      if (nodes[i].text == "root node") {
        rootNode = nodes[i]
      }
      if (nodes[i].isCheckable == true) {
        checkableNode = nodes[i]
      }
    }
    assertEquals(rootNode?.childIdsCount, 2)
    assertEquals(checkableNode?.text, "Check box")
  }

  @Test
  fun buildForest_noRootInWindow_returnsEmptyTree() {
    val creator = AccessibilityTreeCreator()
    val windowInfo = AccessibilityWindowInfo.obtain()
    shadowOf(windowInfo).setType(AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY)

    val forest = creator.buildForest(mutableListOf(windowInfo))

    assertEquals(0, forest.getWindows(0).tree.nodesList.size)
  }

  private fun createAccessibilityNodeInfo(): AccessibilityNodeInfo {
    val root = AccessibilityNodeInfo.obtain()
    root.text = "root node"
    root.isClickable = true
    val accessibilityNodeInfo = AccessibilityNodeInfo.obtain()
    accessibilityNodeInfo.viewIdResourceName = "test"
    accessibilityNodeInfo.isClickable = true
    accessibilityNodeInfo.isEditable = true
    accessibilityNodeInfo.hintText = "Please enter your address"
    shadowOf(root).addChild(accessibilityNodeInfo)
    val anotherChildNode = AccessibilityNodeInfo.obtain()
    anotherChildNode.isCheckable = true
    anotherChildNode.text = "Check box"
    shadowOf(root).addChild(anotherChildNode)
    return root
  }

  private fun createWindowInfo(): AccessibilityWindowInfo {
    val windowInfo = AccessibilityWindowInfo.obtain()
    shadowOf(windowInfo).setType(AccessibilityWindowInfo.TYPE_ACCESSIBILITY_OVERLAY)
    shadowOf(windowInfo).setRoot(createAccessibilityNodeInfo())
    return windowInfo
  }
}
