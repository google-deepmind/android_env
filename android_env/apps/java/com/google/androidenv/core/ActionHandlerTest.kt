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

import android.accessibilityservice.GestureDescription
import android.view.accessibility.AccessibilityNodeInfo
import com.google.common.truth.Truth.assertThat
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.any
import org.mockito.kotlin.argumentCaptor
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

@RunWith(androidx.test.ext.junit.runners.AndroidJUnit4::class)
class ActionHandlerTest {

  private val mockGestureInjector = mock<GestureInjector>()
  private lateinit var handler: ActionHandler

  @Before
  fun setUp() {
    handler = ActionHandler(mockGestureInjector)
  }

  @Test
  fun injectAction_touch_callsInputServiceWithScaledCoordinates() {
    val action =
      Action(
        actionType = ActionType.TOUCH_DOWN,
        touchPosition = listOf(0.5f, 0.25f),
        keycode = null,
      )

    handler.injectAction(action, 1000, 2000)

    val gestureCaptor = argumentCaptor<GestureDescription>()
    verify(mockGestureInjector).injectGesture(gestureCaptor.capture(), any())

    val gesture = gestureCaptor.firstValue
    assertThat(gesture).isNotNull()
  }

  @Test
  fun injectAction_keyEvent_callsPerformGlobalAction() {
    val action =
      Action(
        actionType = ActionType.KEY_EVENT,
        touchPosition = null,
        keycode = 4, // BACK -> GLOBAL_ACTION_BACK = 1
      )

    handler.injectAction(action, 1000, 2000)

    verify(mockGestureInjector).performGlobalAction(1)
  }

  @Test
  fun injectAction_setText_appendsToExistingNodeText() {
    val mockNode = mock<AccessibilityNodeInfo>()
    whenever(mockNode.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)).doReturn(mockNode)
    whenever(mockNode.text).doReturn("hello ")
    whenever(mockGestureInjector.getRootNode()).doReturn(mockNode)

    val action =
      Action(actionType = ActionType.SET_TEXT, touchPosition = null, keycode = null, text = "world")

    handler.injectAction(action, 1000, 2000)

    val argsCaptor = argumentCaptor<android.os.Bundle>()
    verify(mockNode)
      .performAction(
        org.mockito.kotlin.eq(AccessibilityNodeInfo.ACTION_SET_TEXT),
        argsCaptor.capture(),
      )
    val charSeq =
      argsCaptor.firstValue.getCharSequence(
        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE
      )
    assertThat(charSeq.toString()).isEqualTo("hello world")
  }

  @Test
  fun injectAction_setText_ignoresHintText() {
    val mockNode = mock<AccessibilityNodeInfo>()
    whenever(mockNode.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)).doReturn(mockNode)
    whenever(mockNode.text).doReturn("Search or type URL")
    whenever(mockNode.hintText).doReturn("Search or type URL")
    whenever(mockGestureInjector.getRootNode()).doReturn(mockNode)

    val action =
      Action(actionType = ActionType.SET_TEXT, touchPosition = null, keycode = null, text = "g")

    handler.injectAction(action, 1000, 2000)

    val argsCaptor = argumentCaptor<android.os.Bundle>()
    verify(mockNode)
      .performAction(
        org.mockito.kotlin.eq(AccessibilityNodeInfo.ACTION_SET_TEXT),
        argsCaptor.capture(),
      )
    val charSeq =
      argsCaptor.firstValue.getCharSequence(
        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE
      )
    assertThat(charSeq.toString()).isEqualTo("g")
  }

  @Test
  fun injectAction_keyEvent_del_removesLastChar() {
    val mockNode = mock<AccessibilityNodeInfo>()
    whenever(mockNode.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)).doReturn(mockNode)
    whenever(mockNode.text).doReturn("hello")
    whenever(mockGestureInjector.getRootNode()).doReturn(mockNode)

    val action =
      Action(
        actionType = ActionType.KEY_EVENT,
        touchPosition = null,
        keycode = 67, // KEYCODE_DEL
      )

    handler.injectAction(action, 1000, 2000)

    val argsCaptor = argumentCaptor<android.os.Bundle>()
    verify(mockNode)
      .performAction(
        org.mockito.kotlin.eq(AccessibilityNodeInfo.ACTION_SET_TEXT),
        argsCaptor.capture(),
      )
    val charSeq =
      argsCaptor.firstValue.getCharSequence(
        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE
      )
    assertThat(charSeq.toString()).isEqualTo("hell")
  }

  @Test
  fun injectAction_setText_targetsEditableHtmlNodeInChrome() {
    val mockRoot = mock<AccessibilityNodeInfo>()
    val mockHtmlInput = mock<AccessibilityNodeInfo>()
    whenever(mockRoot.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)).doReturn(null)
    whenever(mockRoot.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)).doReturn(null)
    whenever(mockRoot.childCount).doReturn(1)
    whenever(mockRoot.getChild(0)).doReturn(mockHtmlInput)
    whenever(mockHtmlInput.isEditable).doReturn(true)
    whenever(mockHtmlInput.text).doReturn("test")
    whenever(mockGestureInjector.getRootNode()).doReturn(mockRoot)

    val action =
      Action(actionType = ActionType.SET_TEXT, touchPosition = null, keycode = null, text = "ing")

    handler.injectAction(action, 1000, 2000)

    val argsCaptor = argumentCaptor<android.os.Bundle>()
    verify(mockHtmlInput)
      .performAction(
        org.mockito.kotlin.eq(AccessibilityNodeInfo.ACTION_SET_TEXT),
        argsCaptor.capture(),
      )
    val charSeq =
      argsCaptor.firstValue.getCharSequence(
        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE
      )
    assertThat(charSeq.toString()).isEqualTo("testing")
  }

  @Test
  fun injectAction_setText_findsEditableNodeInMultiWindowAppWhenKeyboardIsUp() {
    val keyboardRoot = mock<AccessibilityNodeInfo>()
    whenever(keyboardRoot.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)).doReturn(null)
    whenever(keyboardRoot.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)).doReturn(null)

    val chromeAppRoot = mock<AccessibilityNodeInfo>()
    val htmlInputNode = mock<AccessibilityNodeInfo>()
    whenever(chromeAppRoot.findFocus(AccessibilityNodeInfo.FOCUS_INPUT)).doReturn(null)
    whenever(chromeAppRoot.findFocus(AccessibilityNodeInfo.FOCUS_ACCESSIBILITY)).doReturn(null)
    whenever(chromeAppRoot.childCount).doReturn(1)
    whenever(chromeAppRoot.getChild(0)).doReturn(htmlInputNode)
    whenever(htmlInputNode.isEditable).doReturn(true)
    whenever(htmlInputNode.text).doReturn("google")

    whenever(mockGestureInjector.getRootNodes()).doReturn(listOf(keyboardRoot, chromeAppRoot))

    val action =
      Action(actionType = ActionType.SET_TEXT, touchPosition = null, keycode = null, text = ".com")

    handler.injectAction(action, 1000, 2000)

    val argsCaptor = argumentCaptor<android.os.Bundle>()
    verify(htmlInputNode)
      .performAction(
        org.mockito.kotlin.eq(AccessibilityNodeInfo.ACTION_SET_TEXT),
        argsCaptor.capture(),
      )
    val charSeq =
      argsCaptor.firstValue.getCharSequence(
        AccessibilityNodeInfo.ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE
      )
    assertThat(charSeq.toString()).isEqualTo("google.com")
  }
}
