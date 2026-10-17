import 'jasmine';
import {createLogViewer, LogData, LogViewerElement} from './logs_viewer';

describe('LogViewerElement', () => {
  let viewer: LogViewerElement;

  beforeEach(() => {
    document.body.innerHTML = `
      <button id="logs-open-btn" style="display: none;">Console Logs</button>
    `;
    viewer = createLogViewer();
    viewer.id = 'logs-viewer';
    document.body.appendChild(viewer);
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('initializes custom element and renders internal DOM on connect', () => {
    expect(viewer).toBeTruthy();
    expect(viewer.tagName.toLowerCase()).toBe('log-viewer');
    expect(viewer.getLogCount()).toBe(0);
    const content = viewer.querySelector('#logs-content');
    expect(content).not.toBeNull();
  });

  it('adds and renders a single log line', () => {
    const log: LogData = {
      message: 'Test log line',
      level: 'INFO',
      timestamp: 1000,
    };
    viewer.addLog(log);

    expect(viewer.getLogCount()).toBe(1);
    const content = viewer.querySelector('#logs-content') as HTMLElement;
    expect(content.children.length).toBe(1);
    expect(content.children[0].textContent).toBe('Test log line');
    expect(content.children[0].className).toContain('log-info');
  });

  it('adds multiple log lines', () => {
    const logs: LogData[] = [
      {message: 'Log 1', level: 'INFO', timestamp: 1000},
      {message: 'Log 2', level: 'WARNING', timestamp: 1001},
      {message: 'Log 3', level: 'ERROR', timestamp: 1002},
    ];
    viewer.addLogs(logs);

    expect(viewer.getLogCount()).toBe(3);
    const content = viewer.querySelector('#logs-content') as HTMLElement;
    expect(content.children.length).toBe(3);
    expect(content.children[1].className).toContain('log-warning');
    expect(content.children[2].className).toContain('log-error');
  });

  it('clears logs', () => {
    viewer.addLog({message: 'Log 1', level: 'INFO', timestamp: 1000});
    expect(viewer.getLogCount()).toBe(1);

    const clearBtn = viewer.querySelector(
      '#logs-clear-btn'
    ) as HTMLButtonElement;
    clearBtn.click();

    expect(viewer.getLogCount()).toBe(0);
    const content = viewer.querySelector('#logs-content') as HTMLElement;
    expect(content.children.length).toBe(0);
  });

  it('filters logs by level', () => {
    const logs: LogData[] = [
      {message: 'Info log', level: 'INFO', timestamp: 1000},
      {message: 'Warn log', level: 'WARNING', timestamp: 1001},
      {message: 'Error log', level: 'ERROR', timestamp: 1002},
    ];
    viewer.addLogs(logs);

    const content = viewer.querySelector('#logs-content') as HTMLElement;
    expect(content.children.length).toBe(3);

    const levelFilter = viewer.querySelector(
      '#logs-level-filter'
    ) as HTMLSelectElement;
    levelFilter.value = 'WARNING';
    levelFilter.dispatchEvent(new Event('change'));

    expect(content.children.length).toBe(2);
    expect(content.children[0].textContent).toBe('Warn log');
    expect(content.children[1].textContent).toBe('Error log');
  });

  it('toggles panel visibility', () => {
    const toggleBtn = viewer.querySelector(
      '#logs-toggle-btn'
    ) as HTMLButtonElement;
    const panel = viewer.querySelector('#logs-panel') as HTMLElement;
    const openBtn = document.getElementById(
      'logs-open-btn'
    ) as HTMLButtonElement;

    toggleBtn.click();
    expect(panel.style.display).toBe('none');
    expect(openBtn.style.display).toBe('inline-block');

    viewer.showPanel();
    expect(panel.style.display).toBe('flex');
    expect(openBtn.style.display).toBe('none');
  });

  it('evicts oldest logs when maxLogs threshold is exceeded', () => {
    (viewer as unknown as {maxLogs: number}).maxLogs = 2;
    viewer.addLog({message: 'Log 1', level: 'INFO', timestamp: 1000});
    viewer.addLog({message: 'Log 2', level: 'INFO', timestamp: 1001});
    viewer.addLog({message: 'Log 3', level: 'INFO', timestamp: 1002});
    expect(viewer.getLogCount()).toBe(2);

    viewer.addLogs([
      {message: 'Log 4', level: 'INFO', timestamp: 1003},
      {message: 'Log 5', level: 'INFO', timestamp: 1004},
    ]);
    expect(viewer.getLogCount()).toBe(2);
  });
});
