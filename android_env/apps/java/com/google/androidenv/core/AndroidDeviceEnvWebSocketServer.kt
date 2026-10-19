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

import android.util.Log
import com.androidenv.proto.ClientMessage
import com.androidenv.proto.ErrorResponse
import com.androidenv.proto.ServerMessage
import com.google.androidenv.core.ProtoConversions.toCore
import com.google.androidenv.core.ProtoConversions.toProto
import java.io.IOException
import java.net.InetSocketAddress
import java.nio.ByteBuffer
import org.java_websocket.WebSocket
import org.java_websocket.exceptions.WebsocketNotConnectedException
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer

/**
 * WebSocket server that exposes AndroidDeviceEnv over the network. Communicates using serialized
 * Protobuf messages and continuous background state streaming.
 */
class AndroidDeviceEnvWebSocketServer(private val env: AndroidDeviceEnv, port: Int) :
  WebSocketServer(InetSocketAddress("127.0.0.1", port)) {

  private var streamerThread: Thread? = null
  @Volatile private var isStreaming = false

  init {
    isReuseAddr = true
  }

  override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
    // We only support one active session for control, but we don't enforce it strictly here.
  }

  override fun onClose(conn: WebSocket, code: Int, reason: String, remote: Boolean) {}

  override fun onMessage(conn: WebSocket, message: String) {
    sendError(conn, "Text messages are not supported. Use binary protobuf messages.")
  }

  override fun onMessage(conn: WebSocket, message: ByteBuffer) {
    try {
      // Convert ByteBuffer to ByteString for Protobuf parsing
      val byteString = com.google.protobuf.ByteString.copyFrom(message)
      val clientMessage = ClientMessage.parseFrom(byteString)
      handleClientMessage(conn, clientMessage)
    } catch (e: Exception) {
      sendError(conn, "Failed to parse message: ${e.message}")
    }
  }

  override fun onError(conn: WebSocket?, ex: Exception) {
    // Log or handle server errors
  }

  override fun onStart() {
    startStreaming()
  }

  @Synchronized
  private fun startStreaming() {
    if (isStreaming) return
    isStreaming = true
    streamerThread =
      Thread { runStreamingLoop() }
        .apply {
          isDaemon = true
          start()
        }
  }

  private fun runStreamingLoop() {
    val frameIntervalMs = 33L // ~30 FPS
    while (isStreaming && !Thread.currentThread().isInterrupted) {
      try {
        broadcastLatestDeviceState()
        Thread.sleep(frameIntervalMs)
      } catch (e: InterruptedException) {
        break
      } catch (e: WebsocketNotConnectedException) {
        // Client disconnected during frame broadcast.
      } catch (e: IOException) {
        Log.w(TAG, "IO error streaming device state: ${e.message}")
      }
    }
  }

  private fun broadcastLatestDeviceState() {
    val activeConns = connections
    if (activeConns.isEmpty()) return

    val coreState = env.getDeviceState()
    val protoState = coreState.toProto()
    val serverMsg = ServerMessage.newBuilder().setState(protoState).build()
    val msgBytes = serverMsg.toByteArray()

    for (conn in activeConns) {
      if (conn.isOpen) {
        conn.send(msgBytes)
      }
    }
  }

  @Synchronized
  private fun stopStreaming() {
    isStreaming = false
    streamerThread?.interrupt()
    streamerThread = null
  }

  private fun handleClientMessage(conn: WebSocket, msg: ClientMessage) {
    try {
      when (msg.payloadCase) {
        ClientMessage.PayloadCase.UPDATE_SUBSCRIPTIONS -> {
          val protoSignals = msg.updateSubscriptions.activeSignalsList
          val coreSignals = protoSignals.mapNotNull { it.toCore() }.toSet()
          env.updateSubscriptions(coreSignals)
        }
        ClientMessage.PayloadCase.INJECT_ACTION -> {
          val protoAction = msg.injectAction.action
          env.injectAction(protoAction.toCore())
        }
        ClientMessage.PayloadCase.GET_STATE -> {
          val coreState = env.getDeviceState()
          val protoState = coreState.toProto()
          val serverMsg = ServerMessage.newBuilder().setState(protoState).build()
          conn.send(serverMsg.toByteArray())
        }
        else -> {
          sendError(conn, "Unsupported payload: ${msg.payloadCase}")
        }
      }
    } catch (e: Exception) {
      sendError(conn, "Error handling command: ${e.message}")
    }
  }

  private fun sendError(conn: WebSocket, errorMsg: String) {
    try {
      val serverMsg =
        ServerMessage.newBuilder().setError(ErrorResponse.newBuilder().setMessage(errorMsg)).build()
      conn.send(serverMsg.toByteArray())
    } catch (e: Exception) {
      // Connection might be closed, ignore
    }
  }

  override fun stop() {
    stopStreaming()
    super.stop()
    env.close()
  }

  companion object {
    private const val TAG = "AndroidDeviceEnvWS"
  }
}
