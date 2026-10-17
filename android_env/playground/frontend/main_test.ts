import 'jasmine';
import {initPlayground, setupAutoInit} from './main';

describe('main', () => {
  let result: ReturnType<typeof initPlayground> | null = null;

  beforeEach(() => {
    document.body.innerHTML = `
      <div id="status">Connecting...</div>
      <div id="conn-dot"></div>
      <button class="tab-btn active" data-tab="tab-logs">Logs</button>
      <button class="tab-btn" data-tab="tab-adb">ADB</button>
      <button class="tab-btn" id="btn-no-target">No Target</button>
      <div id="tab-logs" class="tab-content active">Logs Content</div>
      <div id="tab-adb" class="tab-content">ADB Content</div>
      <button id="logs-open-btn" style="display: inline-block;">Console Logs</button>
      <button id="stats-toggle">Stats</button>
      <task-loader id="task-loader"></task-loader>
      <stats-viewer id="stats-viewer"></stats-viewer>
      <screen-controls id="screen-controls"></screen-controls>
      <adb-console id="adb-console"></adb-console>
      <log-viewer id="logs-viewer"></log-viewer>
    `;

    spyOn(window, 'WebSocket').and.returnValue({
      readyState: 1,
      send: jasmine.createSpy('send'),
      binaryType: '',
      onopen: null,
      onclose: null,
      onmessage: null,
    } as unknown as WebSocket);
  });

  afterEach(() => {
    document.body.innerHTML = '';
    result = null;
  });

  it('initializes playground components successfully and handles socket callbacks and bindings', () => {
    const holder: {
      cb: ((event: {data: string}) => void) | null;
      sendSpy: jasmine.Spy;
    } = {cb: null, sendSpy: jasmine.createSpy('send')};

    const ws = {
      readyState: 1,
      send: holder.sendSpy,
      binaryType: '',
      onopen: null,
      onclose: null,
      onmessage: null,
    };
    Object.defineProperty(ws, 'onmessage', {
      set: (fn: (event: {data: string}) => void) => {
        holder.cb = fn;
      },
      get: () => holder.cb,
    });
    // `returnValue` (unlike an arrow `callFake`) supports `new WebSocket(...)`.
    (window.WebSocket as unknown as jasmine.Spy).and.returnValue(
      ws as unknown as WebSocket,
    );

    result = initPlayground();
    expect(result.controlsHandler).toBeTruthy();
    expect(result.taskLoaderHandler).toBeTruthy();
    expect(result.statsViewer).toBeTruthy();
    expect(result.logViewer).toBeTruthy();
    expect(result.adbConsole).toBeTruthy();
    expect(result.socketHandler).toBeTruthy();

    if (holder.cb) {
      holder.cb({
        data: JSON.stringify({type: 'stats', stats: {ack_latency: 12.34}}),
      });
      const statAck = document.getElementById('stat-ack') as HTMLElement;
      expect(statAck.innerText).toBe('12.34');

      holder.cb({
        data: JSON.stringify({
          type: 'logs',
          logs: [{message: 'hello', level: 'INFO', timestamp: 1}],
        }),
      });
      expect(result.logViewer!.getLogCount()).toBe(1);

      // Verify adb response callback
      spyOn(result.adbConsole!, 'handleAdbResponse');
      holder.cb({
        data: JSON.stringify({
          type: 'adb_response',
          command: 'shell pm list packages',
          output: 'package:com.google.android.gms',
          status: 'OK',
        }),
      });
      expect(result.adbConsole!.handleAdbResponse).toHaveBeenCalledWith(
        jasmine.objectContaining({command: 'shell pm list packages'})
      );

      // Verify status change updates conn-dot
      const connDot = document.getElementById('conn-dot') as HTMLElement;
      holder.cb({
        data: JSON.stringify({type: 'status', message: 'Connected to emulator'}),
      });
      expect(connDot.style.background).toBe('var(--success)');

      holder.cb({
        data: JSON.stringify({type: 'status', message: 'Disconnected from emulator'}),
      });
      expect(connDot.style.background).toBe('var(--warning)');
    }

    // Verify screenControls.setSocket(socketHandler) was bound
    const screenImg = document.getElementById('screen') as HTMLImageElement;
    screenImg.dispatchEvent(
      new MouseEvent('mousedown', {clientX: 10, clientY: 10})
    );
    expect(holder.sendSpy).toHaveBeenCalled();
    holder.sendSpy.calls.reset();

    // Verify taskLoader.setSocket(socketHandler) was bound
    const taskInput = document.getElementById('task-name') as HTMLInputElement;
    const loadBtn = document.getElementById(
      'load-task-btn'
    ) as HTMLButtonElement;
    taskInput.value = 'classic_2048';
    loadBtn.click();
    expect(holder.sendSpy).toHaveBeenCalledWith('load_task,classic_2048');
  });

  it('handles initPlayground gracefully when optional elements are absent', () => {
    document.body.innerHTML = '';
    const emptyResult = initPlayground();
    expect(emptyResult.controlsHandler).toBeNull();
    expect(emptyResult.taskLoaderHandler).toBeNull();
    expect(emptyResult.statsViewer).toBeNull();
    expect(emptyResult.logViewer).toBeNull();
    expect(emptyResult.adbConsole).toBeNull();

    // Verify callbacks with absent elements do not throw
    const callbacks = (emptyResult.socketHandler as unknown as {
      callbacks: {
        onStatsReceived: (s: unknown) => void;
        onLogsReceived: (l: unknown) => void;
        onAdbResponseReceived: (r: unknown) => void;
        onStatusChange: (msg: string) => void;
      };
    }).callbacks;
    expect(() => {
      callbacks.onStatsReceived({});
      callbacks.onLogsReceived([]);
      callbacks.onAdbResponseReceived({command: 'test', status: 'OK', output: ''});
      callbacks.onStatusChange('Connected');
    }).not.toThrow();
  });

  it('switches tabs on tab button click', () => {
    result = initPlayground();
    const tabLogs = document.getElementById('tab-logs') as HTMLElement;
    const tabAdb = document.getElementById('tab-adb') as HTMLElement;
    const tabBtns = document.querySelectorAll('.tab-btn');
    const logsBtn = tabBtns[0] as HTMLButtonElement;
    const adbBtn = tabBtns[1] as HTMLButtonElement;
    const noTargetBtn = document.getElementById(
      'btn-no-target'
    ) as HTMLButtonElement;

    expect(tabLogs.classList.contains('active')).toBeTrue();
    expect(tabAdb.classList.contains('active')).toBeFalse();

    adbBtn.click();
    expect(adbBtn.classList.contains('active')).toBeTrue();
    expect(logsBtn.classList.contains('active')).toBeFalse();
    expect(tabLogs.classList.contains('active')).toBeFalse();
    expect(tabAdb.classList.contains('active')).toBeTrue();

    // Clicking a button without a target attribute should not throw and still update active button
    noTargetBtn.click();
    expect(noTargetBtn.classList.contains('active')).toBeTrue();
    expect(adbBtn.classList.contains('active')).toBeFalse();
  });

  it('opens log viewer panel when logs-open-btn is clicked', () => {
    result = initPlayground();
    const openLogsBtn = document.getElementById(
      'logs-open-btn'
    ) as HTMLButtonElement;
    spyOn(result.logViewer!, 'showPanel');
    expect(openLogsBtn.style.display).toBe('inline-block');
    openLogsBtn.click();
    expect(result.logViewer!.showPanel).toHaveBeenCalled();
    expect(openLogsBtn.style.display).toBe('none');
  });

  it('toggles stats viewer panel when stats-toggle is clicked', () => {
    result = initPlayground();
    const openStatsBtn = document.getElementById(
      'stats-toggle'
    ) as HTMLButtonElement;
    const statsPanel = document.getElementById(
      'stats-panel'
    ) as HTMLDialogElement;
    spyOn(statsPanel, 'show');
    spyOn(statsPanel, 'close');
    openStatsBtn.click();
    expect(statsPanel.show).toHaveBeenCalledTimes(1);
    openStatsBtn.click();
    expect(statsPanel.close).toHaveBeenCalledTimes(1);
  });

  it('handles setupAutoInit when document.readyState is loading', () => {
    Object.defineProperty(document, 'readyState', {
      value: 'loading',
      configurable: true,
    });

    const wsSpy = window.WebSocket as unknown as jasmine.Spy;
    wsSpy.calls.reset();

    setupAutoInit();

    expect(wsSpy).not.toHaveBeenCalled();

    document.dispatchEvent(new Event('DOMContentLoaded'));

    expect(wsSpy).toHaveBeenCalled();
  });

  it('does not initialize on DOMContentLoaded if screen element is missing', () => {
    document.body.innerHTML = '';
    Object.defineProperty(document, 'readyState', {
      value: 'loading',
      configurable: true,
    });

    const wsSpy = window.WebSocket as unknown as jasmine.Spy;
    wsSpy.calls.reset();

    setupAutoInit();
    document.dispatchEvent(new Event('DOMContentLoaded'));

    expect(wsSpy).not.toHaveBeenCalled();
  });

  it('handles setupAutoInit when document.readyState is complete', () => {
    Object.defineProperty(document, 'readyState', {
      value: 'complete',
      configurable: true,
    });

    const wsSpy = window.WebSocket as unknown as jasmine.Spy;
    wsSpy.calls.reset();

    setupAutoInit();

    expect(wsSpy).toHaveBeenCalled();
  });

  it('handles setupAutoInit when screen element does not exist and readyState is complete', () => {
    document.body.innerHTML = '';
    Object.defineProperty(document, 'readyState', {
      value: 'complete',
      configurable: true,
    });
    const wsSpy = window.WebSocket as unknown as jasmine.Spy;
    wsSpy.calls.reset();

    setupAutoInit();

    expect(wsSpy).not.toHaveBeenCalled();
  });

  it('returns false when document is null or undefined', () => {
    expect(setupAutoInit(null)).toBeFalse();
  });
});


