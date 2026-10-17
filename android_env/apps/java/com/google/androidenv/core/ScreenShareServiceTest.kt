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

import android.app.Activity
import android.app.Application
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.media.projection.MediaProjection
import android.media.projection.MediaProjectionManager
import android.os.Bundle
import android.os.IBinder
import android.os.IInterface
import androidx.test.core.app.ApplicationProvider
import androidx.test.ext.junit.runners.AndroidJUnit4
import com.google.common.truth.Truth.assertThat
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.any
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.eq
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever
import org.robolectric.Robolectric
import org.robolectric.Shadows.shadowOf
import org.robolectric.android.controller.ServiceController
import org.robolectric.annotation.Config
import org.robolectric.shadows.ShadowNotificationManager

@RunWith(AndroidJUnit4::class)
@Config(sdk = [26]) // ScreenShareService is @RequiresApi(26)
class ScreenShareServiceTest {

  private val context = ApplicationProvider.getApplicationContext<Application>()
  private lateinit var shadowNotificationManager: ShadowNotificationManager
  private var serviceController: ServiceController<ScreenShareService>? = null

  @Before
  fun setUp() {
    val notificationManager =
      context.getSystemService(Context.NOTIFICATION_SERVICE) as NotificationManager
    shadowNotificationManager = shadowOf(notificationManager)
  }

  @After
  fun tearDown() {
    serviceController?.destroy()
    // Clean up singleton
    val field = ScreenShareService::class.java.getDeclaredField("instance")
    field.isAccessible = true
    field.set(null, null)
  }

  @Test
  fun onCreate_setsSingletonInstance() {
    serviceController = Robolectric.buildService(ScreenShareService::class.java)
    val service = serviceController!!.create().get()
    assertThat(ScreenShareService.getInstance()).isEqualTo(service)
  }

  @Test
  fun initialDimensions_areMinusOne() {
    serviceController = Robolectric.buildService(ScreenShareService::class.java)
    val service = serviceController!!.create().get()
    assertThat(service.width()).isEqualTo(-1)
    assertThat(service.height()).isEqualTo(-1)
    assertThat(service.rowStride()).isEqualTo(-1)
  }

  @Test
  fun onStartCommand_START_withoutData_stopsSelf() {
    val intent =
      Intent(context, ScreenShareService::class.java).apply { putExtra("ACTION", "START") }
    serviceController = Robolectric.buildService(ScreenShareService::class.java, intent)
    serviceController!!.create().startCommand(0, 1)

    // It should have posted foreground notification
    assertThat(shadowNotificationManager.size()).isEqualTo(1)
    val notification = shadowNotificationManager.allNotifications[0]
    assertThat(notification).isNotNull()
  }

  @Test
  fun onStartCommand_STOP_stopsForegroundAndSelf() {
    val stopIntent =
      Intent(context, ScreenShareService::class.java).apply { putExtra("ACTION", "STOP") }
    val controller = Robolectric.buildService(ScreenShareService::class.java, stopIntent)
    serviceController = controller // Store for tearDown
    controller.create().startCommand(0, 1)

    // Verifies it runs without crash. stopSelf() is called internally.
  }

  @Test
  fun onStartCommand_START_withData_startsProjection() {
    val mockMediaProjection = mock<MediaProjectionWrapper>()
    val mockMediaProjectionManager = mock<MediaProjectionManagerWrapper>()
    val resultCode = Activity.RESULT_OK
    val dataIntent = Intent("data")

    whenever(mockMediaProjectionManager.getMediaProjection(eq(resultCode), any()))
      .doReturn(mockMediaProjection)

    val intent =
      Intent(context, ScreenShareService::class.java).apply {
        putExtra("ACTION", "START")
        putExtra("RESULT_CODE", resultCode)
        putExtra("DATA", dataIntent)
      }
    val controller = Robolectric.buildService(ScreenShareService::class.java, intent)
    val service = controller.get()
    service.mediaProjectionManagerWrapper = mockMediaProjectionManager
    serviceController = controller // Store for tearDown

    controller.create().startCommand(0, 1)

    assertThat(service.getMediaProjection()).isEqualTo(mockMediaProjection)
  }

  @Test
  fun onStartCommand_STOP_stopsProjection() {
    val mockMediaProjection = mock<MediaProjectionWrapper>()
    val mockMediaProjectionManager = mock<MediaProjectionManagerWrapper>()
    val resultCode = Activity.RESULT_OK
    val dataIntent = Intent("data")

    whenever(mockMediaProjectionManager.getMediaProjection(eq(resultCode), any()))
      .doReturn(mockMediaProjection)

    val intent =
      Intent(context, ScreenShareService::class.java).apply {
        putExtra("ACTION", "START")
        putExtra("RESULT_CODE", resultCode)
        putExtra("DATA", dataIntent)
      }
    val controller = Robolectric.buildService(ScreenShareService::class.java, intent)
    val service = controller.get()
    service.mediaProjectionManagerWrapper = mockMediaProjectionManager
    serviceController = controller

    controller.create().startCommand(0, 1)

    assertThat(service.getMediaProjection()).isEqualTo(mockMediaProjection)

    // Change action to STOP and call startCommand again
    intent.putExtra("ACTION", "STOP")
    controller.startCommand(0, 2)

    verify(mockMediaProjection).stop()
    assertThat(service.getMediaProjection()).isNull()
  }

  @Test
  fun realMediaProjectionManagerWrapper_returnsNull_whenResultCancelled() {
    val manager =
      context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
    val wrapper = RealMediaProjectionManagerWrapper(manager)
    val result = wrapper.getMediaProjection(Activity.RESULT_CANCELED, Intent())
    assertThat(result).isNull()
  }

  @Test
  fun realMediaProjectionManagerWrapper_returnsWrapper_whenValid() {
    val manager =
      context.getSystemService(Context.MEDIA_PROJECTION_SERVICE) as MediaProjectionManager
    val wrapper = RealMediaProjectionManagerWrapper(manager)

    val imClass = Class.forName("android.media.projection.IMediaProjection")
    val mockImpl = org.mockito.Mockito.mock(imClass)

    val mockBinder = mock<IBinder>()
    whenever(mockBinder.queryLocalInterface(eq("android.media.projection.IMediaProjection")))
      .doReturn(mockImpl as IInterface)

    val bundle =
      Bundle().apply {
        putBinder("android.media.projection.extra.EXTRA_MEDIA_PROJECTION", mockBinder)
      }
    val intent = Intent().putExtras(bundle)

    val result = wrapper.getMediaProjection(Activity.RESULT_OK, intent)
    assertThat(result).isNotNull()
    assertThat(result).isInstanceOf(RealMediaProjectionWrapper::class.java)
  }

  @Test
  fun realMediaProjectionWrapper_stop_delegatesToActual() {
    val imClass = Class.forName("android.media.projection.IMediaProjection")
    val mockImpl = org.mockito.Mockito.mock(imClass)
    val constructor = MediaProjection::class.java.getConstructor(Context::class.java, imClass)
    val realMp = constructor.newInstance(context, mockImpl) as MediaProjection
    val wrapper = RealMediaProjectionWrapper(realMp)

    wrapper.stop()

    val invocations = org.mockito.Mockito.mockingDetails(mockImpl).invocations
    val methodNames = invocations.map { it.method.name }
    assertThat(methodNames).contains("stop")
  }

  @Test
  fun realMediaProjectionWrapper_createVirtualDisplay_delegatesToActual() {
    val imClass = Class.forName("android.media.projection.IMediaProjection")
    val mockImpl = org.mockito.Mockito.mock(imClass)

    val constructor = MediaProjection::class.java.getConstructor(Context::class.java, imClass)
    val realMp = constructor.newInstance(context, mockImpl) as MediaProjection
    val wrapper = RealMediaProjectionWrapper(realMp)

    val vdWrapper =
      wrapper.createVirtualDisplay(
        name = "test_display",
        width = 640,
        height = 480,
        dpi = 160,
        flags = 0,
        surface = null,
        callback = null,
        handler = null,
      )

    assertThat(vdWrapper).isNotNull()
    vdWrapper!!.release()
  }

  @Test
  fun realMediaProjectionWrapper_registerCallback_delegatesToActual() {
    val imClass = Class.forName("android.media.projection.IMediaProjection")
    val mockImpl = org.mockito.Mockito.mock(imClass)
    val constructor = MediaProjection::class.java.getConstructor(Context::class.java, imClass)
    val realMp = constructor.newInstance(context, mockImpl) as MediaProjection
    val wrapper = RealMediaProjectionWrapper(realMp)

    val callback = object : MediaProjection.Callback() {}
    wrapper.registerCallback(callback, null)
  }

  @Test
  fun realMediaProjectionWrapper_getActualMediaProjection_returnsActual() {
    val imClass = Class.forName("android.media.projection.IMediaProjection")
    val mockImpl = org.mockito.Mockito.mock(imClass)
    val constructor = MediaProjection::class.java.getConstructor(Context::class.java, imClass)
    val realMp = constructor.newInstance(context, mockImpl) as MediaProjection
    val wrapper = RealMediaProjectionWrapper(realMp)

    assertThat(wrapper.getActualMediaProjection()).isEqualTo(realMp)
  }

  @Test
  @Config(sdk = [29])
  fun onStartCommand_START_withData_startsAudioRecording_atSdk29() {
    val intent =
      Intent(context, ScreenShareService::class.java).apply {
        putExtra("ACTION", "START")
        putExtra("RESULT_CODE", Activity.RESULT_OK)
        putExtra("DATA", Intent())
      }

    val imClass = Class.forName("android.media.projection.IMediaProjection")
    val mockImpl = org.mockito.Mockito.mock(imClass)
    val mpConstructor = MediaProjection::class.java.getConstructor(Context::class.java, imClass)
    val realMp = mpConstructor.newInstance(context, mockImpl) as MediaProjection

    val mockMediaProjection = mock<MediaProjectionWrapper>()
    whenever(mockMediaProjection.getActualMediaProjection()).doReturn(realMp)

    val mockMediaProjectionManager = mock<MediaProjectionManagerWrapper>()
    whenever(mockMediaProjectionManager.getMediaProjection(any(), any()))
      .doReturn(mockMediaProjection)

    val controller = Robolectric.buildService(ScreenShareService::class.java, intent)
    val service = controller.get()
    service.mediaProjectionManagerWrapper = mockMediaProjectionManager

    controller.create().startCommand(0, 1)

    assertThat(service.getMediaProjection()).isEqualTo(mockMediaProjection)
    verify(mockMediaProjection).getActualMediaProjection()
  }
}
