import './adb_console';
import './controls';
import './logs_viewer';
import './stats';
import './task_loader';
import './theme';
import {AdbConsoleElement} from './adb_console';
import {initHardwareControls, ScreenControlsElement} from './controls';
import {LogViewerElement} from './logs_viewer';
import {SocketHandler} from './socket';
import {StatsViewerElement} from './stats';
import {TaskLoaderElement} from './task_loader';
import {setupThemeListeners} from './theme';

/**
 * Interface representing all initialized playground components.
 */
export interface PlaygroundComponents {
  controlsHandler: ScreenControlsElement | null;
  logViewer: LogViewerElement | null;
  statsViewer: StatsViewerElement | null;
  taskLoaderHandler: TaskLoaderElement | null;
  adbConsole: AdbConsoleElement | null;
  socketHandler: SocketHandler;
}

/**
 * Initializes the playground frontend components and event handlers.
 */
export function initPlayground(): PlaygroundComponents {
  const statsViewer = document.getElementById(
    'stats-viewer'
  ) as StatsViewerElement | null;
  const logViewer = document.getElementById(
    'logs-viewer'
  ) as LogViewerElement | null;
  const taskLoader = document.getElementById(
    'task-loader'
  ) as TaskLoaderElement | null;
  const screenControls = document.getElementById(
    'screen-controls'
  ) as ScreenControlsElement | null;
  const adbConsole = document.getElementById(
    'adb-console'
  ) as AdbConsoleElement | null;

  const openLogsBtn = document.getElementById('logs-open-btn');
  if (openLogsBtn && logViewer) {
    openLogsBtn.addEventListener('click', () => {
      logViewer.showPanel();
      openLogsBtn.style.display = 'none';
    });
  }

  const openStatsBtn = document.getElementById('stats-toggle');
  if (openStatsBtn && statsViewer) {
    openStatsBtn.addEventListener('click', () => {
      statsViewer.togglePanel();
    });
  }

  // Bind tab switching
  document.querySelectorAll('.tab-btn').forEach((btn) => {
    btn.addEventListener('click', () => {
      document
        .querySelectorAll('.tab-btn')
        .forEach((b) => b.classList.remove('active'));
      document
        .querySelectorAll('.tab-content')
        .forEach((c) => c.classList.remove('active'));
      btn.classList.add('active');
      const targetId = btn.getAttribute('data-tab');
      if (targetId) {
        document.getElementById(targetId)?.classList.add('active');
      }
    });
  });

  const socketHandler = new SocketHandler('screen', 'status', {
    onStatsReceived: (stats) => statsViewer?.handleStats(stats),
    onLogsReceived: (logs) => logViewer?.addLogs(logs),
    onAdbResponseReceived: (resp) => adbConsole?.handleAdbResponse(resp),
    onStatusChange: (status) => {
      const connDot = document.getElementById('conn-dot');
      if (connDot) {
        connDot.style.background = status.startsWith('Connected')
          ? 'var(--success)'
          : 'var(--warning)';
      }
    },
  });

  screenControls?.setSocket(socketHandler);
  taskLoader?.setSocket(socketHandler);
  adbConsole?.setSocket(socketHandler);

  initHardwareControls(socketHandler, screenControls);
  setupThemeListeners();

  return {
    controlsHandler: screenControls,
    logViewer,
    statsViewer,
    taskLoaderHandler: taskLoader,
    adbConsole,
    socketHandler,
  };
}

/**
 * Auto-initializes the playground when the DOM is ready.
 */
export function setupAutoInit(
  targetDoc: Document | null = typeof document !== 'undefined' ? document : null
): boolean {
  if (!targetDoc) {
    return false;
  }
  if (targetDoc.readyState === 'loading') {
    targetDoc.addEventListener(
      'DOMContentLoaded',
      () => {
        if (
          targetDoc.getElementById('screen') ||
          targetDoc.getElementById('screen-controls')
        ) {
          initPlayground();
        }
      },
      {once: true}
    );
  } else if (
    targetDoc.getElementById('screen') ||
    targetDoc.getElementById('screen-controls')
  ) {
    initPlayground();
  }
  return true;
}

// Unconditionally execute setupAutoInit on module load
setupAutoInit();
