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

import androidx.test.ext.junit.runners.AndroidJUnit4
import com.androidenv.proto.ClientMessage
import com.androidenv.proto.DeviceSignal
import com.androidenv.proto.InjectActionRequest
import com.androidenv.proto.UpdateSubscriptionsRequest
import com.google.common.truth.Truth.assertThat
import java.net.URI
import org.java_websocket.client.WebSocketClient
import org.java_websocket.handshake.ServerHandshake
import org.junit.After
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith
import org.mockito.kotlin.any
import org.mockito.kotlin.doReturn
import org.mockito.kotlin.mock
import org.mockito.kotlin.verify
import org.mockito.kotlin.whenever

@RunWith(AndroidJUnit4::class)
class AndroidDeviceEnvWebSocketServerTest {

  private val mockEnv = mock<AndroidDeviceEnv>()
  private var serverPort = 0
  private var server: AndroidDeviceEnvWebSocketServer? = null

  @Before
  fun setUp() {
    val dummyState =
      DeviceState(
        screenshot = StreamedSignal.empty(),
        accessibilityRoot = StreamedSignal.empty(),
        activePackage = StreamedSignal.empty(),
        activeActivity = StreamedSignal.empty(),
        systemLogs = StreamedSignal.empty(),
        runningProcesses = StreamedSignal.empty(),
        deviceSettings = StreamedSignal.empty(),
        accelerometer = StreamedSignal.empty(),
        gyroscope = StreamedSignal.empty(),
        magnetometer = StreamedSignal.empty(),
        barometer = StreamedSignal.empty(),
        ambientTemp = StreamedSignal.empty(),
        lightLevel = StreamedSignal.empty(),
        proximity = StreamedSignal.empty(),
        locationGps = StreamedSignal.empty(),
        heartRate = StreamedSignal.empty(),
        audioOutput = StreamedSignal.empty(),
        snapshotTimestampUs = 12345L,
      )
    whenever(mockEnv.getDeviceState()).doReturn(dummyState)

    // Find an available port and start server
    val socket = java.net.ServerSocket(0)
    serverPort = socket.localPort
    socket.close()

    server = AndroidDeviceEnvWebSocketServer(mockEnv, serverPort)
    server?.start()
    // Wait for server to start
    Thread.sleep(200)
  }

  @After
  fun tearDown() {
    server?.stop()
  }

  @Test
  fun testWebSocketServer_startAndConnect() {
    var connected = false
    val client =
      object : WebSocketClient(URI("ws://127.0.0.1:$serverPort")) {
        override fun onOpen(handshakedata: ServerHandshake?) {
          connected = true
        }

        override fun onMessage(message: String?) {}

        override fun onMessage(bytes: java.nio.ByteBuffer?) {}

        override fun onClose(code: Int, reason: String?, remote: Boolean) {}

        override fun onError(ex: Exception?) {}
      }

    client.connectBlocking()
    assertThat(connected).isTrue()
    client.close()
  }

  @Test
  fun testWebSocketServer_handleUpdateSubscriptions() {
    val client =
      object : WebSocketClient(URI("ws://127.0.0.1:$serverPort")) {
        override fun onOpen(handshakedata: ServerHandshake?) {}

        override fun onMessage(message: String?) {}

        override fun onMessage(bytes: java.nio.ByteBuffer?) {}

        override fun onClose(code: Int, reason: String?, remote: Boolean) {}

        override fun onError(ex: Exception?) {}
      }

    client.connectBlocking()

    val req =
      UpdateSubscriptionsRequest.newBuilder()
        .addActiveSignals(DeviceSignal.DEVICE_SIGNAL_SCREENSHOT)
        .build()
    val msg = ClientMessage.newBuilder().setUpdateSubscriptions(req).build()
    client.send(msg.toByteArray())

    Thread.sleep(150)
    verify(mockEnv).updateSubscriptions(setOf(com.google.androidenv.core.DeviceSignal.SCREENSHOT))
    client.close()
  }

  @Test
  fun testWebSocketServer_handleInjectAction() {
    val client =
      object : WebSocketClient(URI("ws://127.0.0.1:$serverPort")) {
        override fun onOpen(handshakedata: ServerHandshake?) {}

        override fun onMessage(message: String?) {}

        override fun onMessage(bytes: java.nio.ByteBuffer?) {}

        override fun onClose(code: Int, reason: String?, remote: Boolean) {}

        override fun onError(ex: Exception?) {}
      }

    client.connectBlocking()

    val action =
      com.androidenv.proto.Action.newBuilder()
        .setActionType(com.androidenv.proto.ActionType.ACTION_TYPE_TOUCH_DOWN)
        .build()
    val req = InjectActionRequest.newBuilder().setAction(action).build()
    val msg = ClientMessage.newBuilder().setInjectAction(req).build()
    client.send(msg.toByteArray())

    Thread.sleep(150)
    verify(mockEnv).injectAction(any())
    client.close()
  }
}
