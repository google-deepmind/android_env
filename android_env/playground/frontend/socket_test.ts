import 'jasmine';
import {getWebSocketUrl, SocketHandler} from './socket';

interface FakeWebSocket {
  readyState: number;
  send: jasmine.Spy;
  binaryType: string;
  onopen: (() => void) | null;
  onclose: (() => void) | null;
  onmessage: ((event: {data: unknown}) => void) | null;
}

describe('SocketHandler', () => {
  let screenImg: HTMLImageElement;
  let statusDiv: HTMLElement;
  let fakeWs: FakeWebSocket;

  beforeEach(() => {
    document.body.innerHTML = `
      <img id="screen" />
      <div id="status">Connecting...</div>
    `;
    screenImg = document.getElementById('screen') as HTMLImageElement;
    statusDiv = document.getElementById('status') as HTMLElement;

    fakeWs = {
      readyState: 1, // WebSocket.OPEN
      send: jasmine.createSpy('send'),
      binaryType: '',
      onopen: null,
      onclose: null,
      onmessage: null,
    };

    spyOn(window, 'WebSocket').and.returnValue(fakeWs as unknown as WebSocket);
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('connects WebSocket and updates status on open', () => {
    expect(screenImg).toBeTruthy();
    const handler = new SocketHandler('screen', 'status');
    expect(handler).toBeTruthy();

    expect(fakeWs.binaryType).toBe('blob');
    if (fakeWs.onopen) {
      fakeWs.onopen();
    }
    expect(statusDiv.innerText).toBe('Connected. Waiting for emulator...');
  });

  it('generates correct WebSocket URL for http and https protocols', () => {
    expect(getWebSocketUrl('http:', 'localhost:8080')).toBe('ws://localhost:8080/ws');
    expect(getWebSocketUrl('https:', 'localhost:8080')).toBe('wss://localhost:8080/ws');
  });


  it('updates status on close', () => {
    const handler = new SocketHandler('screen', 'status');
    expect(handler).toBeTruthy();

    if (fakeWs.onclose) {
      fakeWs.onclose();
    }
    expect(statusDiv.innerText).toBe('Disconnected');
  });

  it('sends action string over WebSocket', () => {
    const handler = new SocketHandler('screen', 'status');
    handler.sendAction('touch_down', 0.5, 0.25);

    expect(fakeWs.send).toHaveBeenCalled();
    const sentData: string = fakeWs.send.calls.mostRecent().args[0];
    expect(sentData.startsWith('touch_down,0.5,0.25,')).toBeTrue();
  });

  it('sends load_task string over WebSocket', () => {
    const handler = new SocketHandler('screen', 'status');
    handler.loadTask('classic_2048');

    expect(fakeWs.send).toHaveBeenCalledWith('load_task,classic_2048');
  });

  it('sends text string over WebSocket', () => {
    const handler = new SocketHandler('screen', 'status');
    handler.sendText('hello');

    expect(fakeWs.send).toHaveBeenCalled();
    const sentData: string = fakeWs.send.calls.mostRecent().args[0];
    expect(sentData.startsWith('text,hello,')).toBeTrue();
  });

  it('sends keydown string over WebSocket', () => {
    const handler = new SocketHandler('screen', 'status');
    handler.sendKeydown(66);

    expect(fakeWs.send).toHaveBeenCalled();
    const sentData: string = fakeWs.send.calls.mostRecent().args[0];
    expect(sentData.startsWith('keydown,66,')).toBeTrue();
  });

  it('sends set_selection string over WebSocket', () => {
    const handler = new SocketHandler('screen', 'status');
    handler.sendSelection(2, 5);

    expect(fakeWs.send).toHaveBeenCalled();
    const sentData: string = fakeWs.send.calls.mostRecent().args[0];
    expect(sentData.startsWith('set_selection,2,5,')).toBeTrue();
  });

  it('sends clipboard string over WebSocket', () => {
    const handler = new SocketHandler('screen', 'status');
    handler.sendClipboard('copy');

    expect(fakeWs.send).toHaveBeenCalled();
    const sentData: string = fakeWs.send.calls.mostRecent().args[0];
    expect(sentData.startsWith('copy,')).toBeTrue();
  });

  it('handles status JSON text messages', () => {
    let statusReceived = '';
    const handler = new SocketHandler('screen', 'status', {
      onStatusChange: (status) => {
        statusReceived = status;
      },
    });
    expect(handler).toBeTruthy();

    if (fakeWs.onmessage) {
      fakeWs.onmessage({
        data: JSON.stringify({type: 'status', message: 'Emulator Running'}),
      });
    }

    expect(statusDiv.innerText).toBe('Emulator Running');
    expect(statusReceived).toBe('Emulator Running');
  });

  it('handles stats JSON text messages', () => {
    let statsReceived: unknown = null;
    const handler = new SocketHandler('screen', 'status', {
      onStatsReceived: (stats) => {
        statsReceived = stats;
      },
    });
    expect(handler).toBeTruthy();

    if (fakeWs.onmessage) {
      fakeWs.onmessage({
        data: JSON.stringify({type: 'stats', stats: {ack_latency: 15.0}}),
      });
    }

    expect(statsReceived).toEqual({ack_latency: 15.0});
  });

  it('handles binary Blob frame message and cleans up old blob URL', async () => {
    screenImg.src = 'blob:http://localhost/old-blob';
    const handler = new SocketHandler('screen', 'status');
    expect(handler).toBeTruthy();

    spyOn(URL, 'createObjectURL').and.returnValue('blob:http://localhost/new-blob');
    const revokeSpy = spyOn(URL, 'revokeObjectURL');

    let srcSetBeforeDecode = false;
    spyOn(Image.prototype, 'decode').and.callFake(function (this: HTMLImageElement) {
      if (this.src && this.src.includes('blob:http://localhost/new-blob')) {
        srcSetBeforeDecode = true;
      }
      return Promise.resolve();
    });

    // Mock requestAnimationFrame to execute immediately
    spyOn(window, 'requestAnimationFrame').and.callFake((cb: FrameRequestCallback) => {
      cb(0);
      return 0;
    });

    const fakeBlob = new Blob(['fake image data']); // No type specified (empty type)

    if (fakeWs.onmessage) {
      fakeWs.onmessage({data: fakeBlob});
    }

    // Wait for promise resolution
    await Promise.resolve();

    expect(URL.createObjectURL).toHaveBeenCalled();
    expect(srcSetBeforeDecode).toBeTrue();
    expect(screenImg.src).toContain('blob:http://localhost/new-blob');
    expect(revokeSpy).toHaveBeenCalledWith('blob:http://localhost/old-blob');
    expect(fakeWs.send).toHaveBeenCalledWith('ack');
  });

  it('does not revoke URL when oldUrl is not a blob URL', async () => {
    screenImg.src = 'http://localhost/static/screen.png';
    const handler = new SocketHandler('screen', 'status');
    expect(handler).toBeTruthy();

    spyOn(URL, 'createObjectURL').and.returnValue('blob:http://localhost/new-blob');
    const revokeSpy = spyOn(URL, 'revokeObjectURL');
    spyOn(Image.prototype, 'decode').and.returnValue(Promise.resolve());

    if (fakeWs.onmessage) {
      fakeWs.onmessage({data: new Blob(['data'], {type: 'image/png'})});
    }

    await Promise.resolve();

    expect(revokeSpy).not.toHaveBeenCalled();
    expect(screenImg.src).toContain('blob:http://localhost/new-blob');
  });

  it('handles image decode failure gracefully in handleBlobFrame', async () => {
    const handler = new SocketHandler('screen', 'status');
    expect(handler).toBeTruthy();

    spyOn(URL, 'createObjectURL').and.returnValue('blob:http://localhost/new-blob');
    spyOn(Image.prototype, 'decode').and.rejectWith(new Error('Decode error'));
    spyOn(console, 'error');

    const fakeBlob = new Blob(['corrupt image data'], {type: 'image/png'});

    if (fakeWs.onmessage) {
      fakeWs.onmessage({data: fakeBlob});
    }

    await new Promise((resolve) => setTimeout(resolve, 10));

    expect(console.error).toHaveBeenCalledWith('Decode failed:', jasmine.any(Error));
    expect(screenImg.src).toContain('blob:http://localhost/new-blob');
  });



  it('handles invalid JSON text messages gracefully', () => {
    const handler = new SocketHandler('screen', 'status');
    expect(handler).toBeTruthy();
    spyOn(console, 'error');

    if (fakeWs.onmessage) {
      fakeWs.onmessage({data: 'invalid json {'});
    }

    expect(console.error).toHaveBeenCalledWith('Failed to parse message:', jasmine.any(Error));
  });

  it('does not send actions, ack, or loadTask when socket is not OPEN', () => {
    fakeWs.readyState = 3; // CLOSED
    const handler = new SocketHandler('screen', 'status');

    handler.sendAck();
    handler.sendAction('touch_down', 0.5, 0.5);
    handler.sendText('hello');
    handler.sendKeydown(66);
    handler.sendSelection(2, 5);
    handler.sendClipboard('copy');
    handler.loadTask('task1');
    handler.sendAdbCommand('shell wm size');
    handler.sendReset();

    expect(fakeWs.send).not.toHaveBeenCalled();
  });

  it('handles missing screenImg and statusDiv elements gracefully', () => {
    let statusReceived = '';
    const handler = new SocketHandler('missing-screen', 'missing-status', {
      onStatusChange: (status) => {
        statusReceived = status;
      },
    });
    expect(handler).toBeTruthy();

    if (fakeWs.onopen) {
      fakeWs.onopen();
    }
    expect(statusReceived).toBe('Connected. Waiting for emulator...');

    const createUrlSpy = spyOn(URL, 'createObjectURL');
    if (fakeWs.onmessage) {
      fakeWs.onmessage({data: new Blob(['data'], {type: 'image/jpeg'})});
    }
    expect(createUrlSpy).not.toHaveBeenCalled();
  });

  it('sends adb and reset commands over WebSocket', () => {
    const handler = new SocketHandler('screen', 'status');
    handler.sendAdbCommand('shell wm size');
    expect(fakeWs.send).toHaveBeenCalledWith('adb,shell wm size');

    handler.sendReset();
    expect(fakeWs.send).toHaveBeenCalledWith('reset');
  });

  it('handles adb_response JSON text messages', () => {
    let adbReceived: unknown = null;
    const handler = new SocketHandler('screen', 'status', {
      onAdbResponseReceived: (resp) => {
        adbReceived = resp;
      },
    });
    expect(handler).toBeTruthy();

    if (fakeWs.onmessage) {
      fakeWs.onmessage({
        data: JSON.stringify({
          type: 'adb_response',
          command: 'shell wm size',
          status: 'OK',
          output: 'Physical size: 1080x1920',
          duration_ms: 4.2,
        }),
      });
    }

    expect(adbReceived).toEqual({
      command: 'shell wm size',
      status: 'OK',
      output: 'Physical size: 1080x1920',
      error: undefined,
      duration_ms: 4.2,
    });
  });
});



