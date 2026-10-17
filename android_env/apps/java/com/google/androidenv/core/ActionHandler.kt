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

import android.accessibilityservice.AccessibilityService
import android.accessibilityservice.GestureDescription
import android.graphics.Path
import android.util.Log
import android.view.accessibility.AccessibilityNodeInfo

/**
 * Handles touch gestures, key events, and accessibility actions for AndroidEnv.
 *
 * Note on WebContents / Chrome HTML inputs: Native Android View text controls (e.g. EditText, URL
 * bar) fully support text manipulation via ACTION_SET_TEXT, ACTION_SET_SELECTION, and clipboard
 * actions. WebContents rendered inside Chrome / WebViews use Chromium's virtual DOM accessibility
 * tree, which may not consistently receive or process AccessibilityNodeInfo text actions across all
 * web pages.
 */
class ActionHandler(private val gestureInjector: GestureInjector) {

  private val gestureLock = Any()
  private var latestStrokeDescription: GestureDescription.StrokeDescription? = null
  private var isTouching: Boolean = false
  private var latestX: Float = 0f
  private var latestY: Float = 0f

  fun injectAction(action: Action, width: Int, height: Int) {
    try {
      if (action.actionType == ActionType.KEY_EVENT) {
        action.keycode?.let { keycode ->
          when (keycode) {
            android.view.KeyEvent.KEYCODE_BACK -> {
              gestureInjector.performGlobalAction(AccessibilityService.GLOBAL_ACTION_BACK)
            }
            android.view.KeyEvent.KEYCODE_HOME -> {
              gestureInjector.performGlobalAction(AccessibilityService.GLOBAL_ACTION_HOME)
            }
            android.view.KeyEvent.KEYCODE_DEL,
            android.view.KeyEvent.KEYCODE_FORWARD_DEL -> {
              val targetNode = getTargetNode()
              if (targetNode != null) {
                val currentText = getActualNodeText(targetNode)
                if (currentText.isNotEmpty()) {
                  val selStart = targetNode.textSelectionStart
                  val selEnd = targetNode.textSelectionEnd
                  val newText =
                    if (selStart in 0..selEnd && selStart != selEnd) {
                      currentText.removeRange(
                        selStart.coerceAtMost(currentText.length),
                        selEnd.coerceAtMost(currentText.length),
                      )
                    } else if (keycode == android.view.KeyEvent.KEYCODE_DEL) {
                      val pos =
                        if (selStart > 0 && selStart <= currentText.length) selStart
                        else currentText.length
                      if (pos > 0) currentText.removeRange(pos - 1, pos) else currentText
                    } else {
                      val pos = if (selStart >= 0) selStart else 0
                      if (pos < currentText.length) currentText.removeRange(pos, pos + 1)
                      else currentText
                    }
                  val arguments = android.os.Bundle()
                  arguments.putCharSequence(
                    AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
                    newText,
                  )
                  targetNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
                }
              }
            }
            android.view.KeyEvent.KEYCODE_ENTER -> {
              val targetNode = getTargetNode()
              if (targetNode != null) {
                var handled = false
                if (android.os.Build.VERSION.SDK_INT >= android.os.Build.VERSION_CODES.R) {
                  handled =
                    targetNode.performAction(
                      AccessibilityNodeInfo.AccessibilityAction.ACTION_IME_ENTER.id
                    )
                }
                if (!handled) {
                  targetNode.performAction(AccessibilityNodeInfo.ACTION_CLICK)
                }
              }
            }
            android.view.KeyEvent.KEYCODE_DPAD_LEFT -> {
              val targetNode = getTargetNode()
              if (targetNode != null) {
                val start = targetNode.textSelectionStart
                val newPos = (start - 1).coerceAtLeast(0)
                val args =
                  android.os.Bundle().apply {
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, newPos)
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, newPos)
                  }
                targetNode.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, args)
              }
            }
            android.view.KeyEvent.KEYCODE_DPAD_RIGHT -> {
              val targetNode = getTargetNode()
              if (targetNode != null) {
                val start = targetNode.textSelectionStart
                val textLen = getActualNodeText(targetNode).length
                val newPos = (start + 1).coerceAtMost(textLen)
                val args =
                  android.os.Bundle().apply {
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, newPos)
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, newPos)
                  }
                targetNode.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, args)
              }
            }
            android.view.KeyEvent.KEYCODE_MOVE_HOME -> {
              val targetNode = getTargetNode()
              targetNode?.performAction(
                AccessibilityNodeInfo.ACTION_SET_SELECTION,
                android.os.Bundle().apply {
                  putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, 0)
                  putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, 0)
                },
              )
            }
            android.view.KeyEvent.KEYCODE_MOVE_END -> {
              val targetNode = getTargetNode()
              if (targetNode != null) {
                val len = getActualNodeText(targetNode).length
                targetNode.performAction(
                  AccessibilityNodeInfo.ACTION_SET_SELECTION,
                  android.os.Bundle().apply {
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, len)
                    putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, len)
                  },
                )
              }
            }
            android.view.KeyEvent.KEYCODE_PAGE_UP -> {
              val targetNode = getTargetNode()
              targetNode?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_BACKWARD)
            }
            android.view.KeyEvent.KEYCODE_PAGE_DOWN -> {
              val targetNode = getTargetNode()
              targetNode?.performAction(AccessibilityNodeInfo.ACTION_SCROLL_FORWARD)
            }
            else -> {
              Log.w(TAG, "Keycode $keycode injection not supported on-device without root.")
            }
          }
        }
      } else if (action.actionType == ActionType.SET_TEXT) {
        action.text?.let { textToSet ->
          val targetNode = getTargetNode()
          if (targetNode != null) {
            val currentText = getActualNodeText(targetNode)
            val newText = currentText + textToSet
            val arguments = android.os.Bundle()
            arguments.putCharSequence(
              AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE,
              newText,
            )
            targetNode.performAction(AccessibilityNodeInfo.ACTION_SET_TEXT, arguments)
          } else {
            Log.w(TAG, "Could not find active focus node for SET_TEXT action.")
          }
        }
      } else if (action.actionType == ActionType.SET_SELECTION) {
        val targetNode = getTargetNode()
        if (targetNode != null) {
          val textLen = getActualNodeText(targetNode).length
          val selStart = action.selectionStart ?: 0
          val rawEnd = action.selectionEnd ?: selStart
          val selEnd = if (rawEnd < 0) textLen else rawEnd.coerceAtMost(textLen)
          val args =
            android.os.Bundle().apply {
              putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_START_INT, selStart)
              putInt(AccessibilityNodeInfo.ACTION_ARGUMENT_SELECTION_END_INT, selEnd)
            }
          targetNode.performAction(AccessibilityNodeInfo.ACTION_SET_SELECTION, args)
        }
      } else if (
        action.actionType == ActionType.CUT ||
          action.actionType == ActionType.COPY ||
          action.actionType == ActionType.PASTE
      ) {
        val targetNode = getTargetNode()
        if (targetNode != null) {
          val a11yAction =
            when (action.actionType) {
              ActionType.CUT -> AccessibilityNodeInfo.ACTION_CUT
              ActionType.COPY -> AccessibilityNodeInfo.ACTION_COPY
              else -> AccessibilityNodeInfo.ACTION_PASTE
            }
          targetNode.performAction(a11yAction)
        }
      } else {
        // Touch action
        val gesture = buildGesture(action, width, height)
        if (gesture != null) {
          gestureInjector.injectGesture(
            gesture,
            object : AccessibilityService.GestureResultCallback() {
              override fun onCompleted(gestureDescription: GestureDescription?) {
                Log.i(TAG, "Gesture completed successfully")
              }

              override fun onCancelled(gestureDescription: GestureDescription?) {
                Log.w(TAG, "Gesture cancelled")
              }
            },
          )
        }
      }
    } catch (e: Exception) {
      Log.e(TAG, "Failed to inject action: ${e.message}", e)
    }
  }

  private fun buildGesture(action: Action, width: Int, height: Int): GestureDescription? {
    synchronized(gestureLock) {
      val pos = action.touchPosition ?: return null
      if (pos.size < 2) return null
      val x = pos[0] * width
      val y = pos[1] * height

      val builder = GestureDescription.Builder()
      val segmentDuration: Long = 20
      val path = Path()

      when (action.actionType) {
        ActionType.TOUCH_DOWN -> {
          path.moveTo(x, y)
          path.lineTo(x, y)
          val stroke = GestureDescription.StrokeDescription(path, 0, segmentDuration, true)
          builder.addStroke(stroke)
          latestStrokeDescription = stroke
          isTouching = true
        }
        ActionType.TOUCH_MOVE -> {
          if (isTouching && latestStrokeDescription != null) {
            path.moveTo(latestX, latestY)
            path.lineTo(x, y)
            val stroke = latestStrokeDescription!!.continueStroke(path, 0, segmentDuration, true)
            builder.addStroke(stroke)
            latestStrokeDescription = stroke
          } else {
            path.moveTo(x, y)
            val stroke = GestureDescription.StrokeDescription(path, 0, segmentDuration, true)
            builder.addStroke(stroke)
            latestStrokeDescription = stroke
            isTouching = true
          }
        }
        ActionType.TOUCH_UP -> {
          if (isTouching && latestStrokeDescription != null) {
            path.moveTo(latestX, latestY)
            path.lineTo(x, y)
            val stroke = latestStrokeDescription!!.continueStroke(path, 0, segmentDuration, false)
            builder.addStroke(stroke)
          }
          latestStrokeDescription = null
          isTouching = false
        }
        else -> return null
      }
      latestX = x
      latestY = y
      if (path.isEmpty) return null
      return builder.build()
    }
  }

  private fun getActiveRootNode(): AccessibilityNodeInfo? {
    return gestureInjector.getRootNode()
      ?: try {
        InputService.getInstance().getRootNode()
      } catch (e: Exception) {
        null
      }
  }

  private fun getAllRootNodes(): List<AccessibilityNodeInfo> {
    val roots = gestureInjector.getRootNodes()
    if (roots.isNotEmpty()) return roots
    val singleRoot = gestureInjector.getRootNode()
    if (singleRoot != null) return listOf(singleRoot)
    return try {
      InputService.getInstance().getRootNodes()
    } catch (e: Exception) {
      emptyList()
    }
  }

  private fun getTargetNode(): AccessibilityNodeInfo? {
    return findTargetNodeFromRoots(getActiveRootNode(), getAllRootNodes())
  }

  companion object {
    private const val TAG = "ActionHandler"

    private fun findTargetNodeFromRoots(
      activeRoot: AccessibilityNodeInfo?,
      allRoots: List<AccessibilityNodeInfo>,
    ): AccessibilityNodeInfo? {
      // 1. Try input focus in active window first (e.g. Chrome URL bar or native EditText)
      val activeInputFocused = activeRoot?.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
      if (activeInputFocused != null) return activeInputFocused

      // 2. Try accessibility focus in active window
      val activeA11yFocused = activeRoot?.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)
      if (
        activeA11yFocused != null && (activeA11yFocused.isEditable || activeA11yFocused.isFocused)
      ) {
        return activeA11yFocused
      }

      // 3. Try input focus across all windows
      for (root in allRoots) {
        val inputFocused = root.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)
        if (inputFocused != null) return inputFocused
      }

      // 4. Try accessibility focus across all windows
      for (root in allRoots) {
        val a11yFocused = root.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)
        if (a11yFocused != null && (a11yFocused.isEditable || a11yFocused.isFocused)) {
          return a11yFocused
        }
      }

      // 5. Search for a node that is explicitly focused AND editable (e.g. focused HTML input)
      for (root in allRoots) {
        val focusedEditable = findFocusedEditableNode(root)
        if (focusedEditable != null) return focusedEditable
      }

      // 6. Search for any editable node in all roots
      for (root in allRoots) {
        val editable = findAnyEditableNode(root)
        if (editable != null) return editable
      }

      return activeRoot ?: allRoots.firstOrNull()
    }

    private fun findFocusedEditableNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
      if (node == null) return null
      if (node.isEditable && (node.isFocused || node.isAccessibilityFocused)) {
        return node
      }
      for (i in 0 until node.childCount) {
        val found = findFocusedEditableNode(node.getChild(i))
        if (found != null) return found
      }
      return null
    }

    private fun findAnyEditableNode(node: AccessibilityNodeInfo?): AccessibilityNodeInfo? {
      if (node == null) return null
      if (node.isEditable) {
        return node
      }
      for (i in 0 until node.childCount) {
        val found = findAnyEditableNode(node.getChild(i))
        if (found != null) return found
      }
      return null
    }

    private fun getActualNodeText(node: AccessibilityNodeInfo): String {
      val text = node.text?.toString() ?: return ""
      val hint = node.hintText?.toString()
      if (node.isShowingHintText || (hint != null && text == hint)) {
        return ""
      }
      return text
    }
  }
}
