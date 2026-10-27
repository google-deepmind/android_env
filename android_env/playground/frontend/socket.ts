import {objectUrlFromSafeSource} from 'safevalues/dom';
import {LogData} from './logs_viewer';
import {StatsData} from './stats';

/**
 * Interface representing an ADB command execution response.
 */
export interface AdbResponseData {
  command: string;
  status: string;
  output: string;
  error?: string;
  duration_ms?: number;
}

/**
 * Interface for socket event callbacks.
 */
export interface SocketCallbacks {
  onStatusChange?: (status: string) => void;
  onStatsReceived?: (stats: StatsData) => void;
  onLogsReceived?: (logs: LogData[]) => void;
  onAdbResponseReceived?: (response: AdbResponseData) => void;
}

/**
 * Generates the WebSocket URL based on protocol and host.
 */
export function getWebSocketUrl(protocol: string, host: string): string {
  const wsProto = protocol === 'https:' ? 'wss' : 'ws';
  return `${wsProto}://${host}/ws`;
}

/**
 * Handles WebSocket communications with the AndroidEnv backend.
 */
export class SocketHandler {
  private readonly ws: WebSocket;
  private readonly screenImg: HTMLImageElement | null;
  private readonly statusDiv: HTMLElement | null;
  private readonly callbacks: SocketCallbacks;

  constructor(
    screenImgId = 'screen',
    statusDivId = 'status',
    callbacks: SocketCallbacks = {}
  ) {
    this.screenImg = document.getElementById(
      screenImgId
    ) as HTMLImageElement | null;
    this.statusDiv = document.getElementById(statusDivId) as HTMLElement | null;
    this.callbacks = callbacks;

    this.ws = new WebSocket(
      getWebSocketUrl(window.location.protocol, window.location.host)
    );
    this.ws.binaryType = 'blob';

    this.initWebSocket();
  }

  private initWebSocket(): void {
    this.ws.onopen = () => {
      console.log('WS Connected');
      this.updateStatus('Connected. Waiting for emulator...');
    };

    this.ws.onclose = () => {
      console.log('WS Closed');
      this.updateStatus('Disconnected');
    };

    this.ws.onmessage = (event: MessageEvent) => {
      if (event.data instanceof Blob) {
        this.handleBlobFrame(event.data);
      } else if (typeof event.data === 'string') {
        this.handleTextMessage(event.data);
      }
    };
  }

  private updateStatus(msg: string): void {
    if (this.statusDiv) {
      this.statusDiv.innerText = msg;
    }
    if (this.callbacks.onStatusChange) {
      this.callbacks.onStatusChange(msg);
    }
  }

  private handleBlobFrame(blob: Blob): void {
    const screenImg = this.screenImg;
    if (!screenImg) {
      return;
    }
    const safeBlob = blob.type ? blob : new Blob([blob], {type: 'image/jpeg'});
    const url = objectUrlFromSafeSource(safeBlob);
    const oldUrl = screenImg.src;

    const tempImg = new Image();
    tempImg.src = url;

    const onFinish = () => {
      screenImg.src = url;
      if (oldUrl && oldUrl.startsWith('blob:')) {
        URL.revokeObjectURL(oldUrl);
      }
      this.sendAck();
    };

    tempImg.decode().then(onFinish).catch((err) => {
      console.error('Decode failed:', err);
      onFinish();
    });
  }

  private handleTextMessage(data: string): void {
    try {
      const msg = JSON.parse(data) as {
        type?: string;
        message?: string;
        stats?: StatsData;
        logs?: LogData[];
        command?: string;
        status?: string;
        output?: string;
        error?: string;
        duration_ms?: number;
      };
      if (msg.type === 'status' && msg.message !== undefined) {
        this.updateStatus(msg.message);
      } else if (msg.type === 'stats' && msg.stats && this.callbacks.onStatsReceived) {
        this.callbacks.onStatsReceived(msg.stats);
      } else if (msg.type === 'logs' && msg.logs && this.callbacks.onLogsReceived) {
        this.callbacks.onLogsReceived(msg.logs);
      } else if (
        msg.type === 'adb_response' &&
        msg.command !== undefined &&
        this.callbacks.onAdbResponseReceived
      ) {
        this.callbacks.onAdbResponseReceived({
          command: msg.command,
          status: msg.status ?? 'OK',
          output: msg.output ?? '',
          error: msg.error,
          duration_ms: msg.duration_ms,
        });
      }
    } catch (err) {
      console.error('Failed to parse message:', err);
    }
  }


  sendAck(): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send('ack');
    }
  }

  sendAction(type: string, x: number, y: number): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(`${type},${x},${y},${Date.now()}`);
    }
  }

  sendText(text: string): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(`text,${text},${Date.now()}`);
    }
  }

  sendKeydown(keycode: number): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(`keydown,${keycode},${Date.now()}`);
    }
  }

  sendSelection(start: number, end: number): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(`set_selection,${start},${end},${Date.now()}`);
    }
  }

  sendClipboard(action: 'cut' | 'copy' | 'paste'): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(`${action},${Date.now()}`);
    }
  }

  loadTask(taskId: string): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      console.log('Sending load_task request:', taskId);
      this.ws.send(`load_task,${taskId}`);
    }
  }

  sendAdbCommand(command: string): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send(`adb,${command}`);
    }
  }

  sendReset(): void {
    if (this.ws.readyState === WebSocket.OPEN) {
      this.ws.send('reset');
    }
  }
}
