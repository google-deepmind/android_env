
/**
 * Interface representing a log entry received from the server.
 */
export interface LogData {
  message: string;
  level: string;
  timestamp: number;
}

/**
 * Custom Web Component for rendering and managing console log messages in the Playground UI.
 */
export class LogViewerElement extends HTMLElement {
  private panel: HTMLElement | null = null;
  private contentDiv: HTMLElement | null = null;
  private toggleBtn: HTMLElement | null = null;
  private clearBtn: HTMLElement | null = null;
  private levelFilter: HTMLSelectElement | null = null;
  private autoscrollCheck: HTMLInputElement | null = null;
  private readonly logs: LogData[] = [];
  private readonly maxLogs: number = 10000;

  constructor() {
    super();
  }

  /** @export */
  connectedCallback(): void {
    if (!this.panel) {
      this.panel = document.createElement('div');
      this.panel.id = 'logs-panel';

      const header = document.createElement('div');
      header.className = 'logs-header';

      const title = document.createElement('span');
      title.textContent = 'Console Logs';

      const controls = document.createElement('div');
      controls.className = 'logs-controls';

      const levelLabel = document.createElement('label');
      levelLabel.setAttribute('for', 'logs-level-filter');
      levelLabel.textContent = 'Level: ';

      this.levelFilter = document.createElement('select');
      this.levelFilter.id = 'logs-level-filter';
      [
        {val: 'ALL', label: 'All Levels'},
        {val: 'INFO', label: 'INFO+'},
        {val: 'WARNING', label: 'WARNING+'},
        {val: 'ERROR', label: 'ERROR'},
      ].forEach((item) => {
        const opt = document.createElement('option');
        opt.value = item.val;
        opt.textContent = item.label;
        this.levelFilter!.appendChild(opt);
      });

      const autoScrollLabel = document.createElement('label');
      this.autoscrollCheck = document.createElement('input');
      this.autoscrollCheck.type = 'checkbox';
      this.autoscrollCheck.id = 'logs-autoscroll';
      this.autoscrollCheck.checked = true;
      autoScrollLabel.appendChild(this.autoscrollCheck);
      autoScrollLabel.appendChild(document.createTextNode(' Auto-scroll'));

      this.clearBtn = document.createElement('button');
      this.clearBtn.id = 'logs-clear-btn';
      this.clearBtn.textContent = 'Clear';

      this.toggleBtn = document.createElement('button');
      this.toggleBtn.id = 'logs-toggle-btn';
      this.toggleBtn.textContent = 'Hide';

      controls.appendChild(levelLabel);
      controls.appendChild(this.levelFilter);
      controls.appendChild(autoScrollLabel);
      controls.appendChild(this.clearBtn);
      controls.appendChild(this.toggleBtn);

      header.appendChild(title);
      header.appendChild(controls);

      this.contentDiv = document.createElement('div');
      this.contentDiv.id = 'logs-content';

      this.panel.appendChild(header);
      this.panel.appendChild(this.contentDiv);

      this.appendChild(this.panel);
      this.initEventListeners();
    }
  }

  private initEventListeners(): void {
    if (this.toggleBtn) {
      this.toggleBtn.addEventListener('click', () => {
        this.hidePanel();
      });
    }

    if (this.clearBtn) {
      this.clearBtn.addEventListener('click', () => {
        this.clearLogs();
      });
    }

    if (this.levelFilter) {
      this.levelFilter.addEventListener('change', () => {
        this.renderAll();
      });
    }
  }

  /** @export */
  showPanel(): void {
    if (this.panel) {
      this.panel.style.display = 'flex';
      this.scrollToBottom();
    }
    const openBtn = document.getElementById('logs-open-btn');
    if (openBtn) {
      openBtn.style.display = 'none';
    }
  }

  /** @export */
  hidePanel(): void {
    if (this.panel) {
      this.panel.style.display = 'none';
    }
    const openBtn = document.getElementById('logs-open-btn');
    if (openBtn) {
      openBtn.style.display = 'inline-block';
    }
  }

  /** @export */
  addLog(log: LogData): void {
    this.logs.push(log);
    if (this.logs.length > this.maxLogs) {
      this.logs.shift();
    }
    if (this.shouldDisplayLog(log)) {
      this.appendLogElement(log);
    }
  }

  /** @export */
  addLogs(logs: LogData[]): void {
    for (const log of logs) {
      this.logs.push(log);
      if (this.logs.length > this.maxLogs) {
        this.logs.shift();
      }
    }
    this.renderAll();
  }

  /** @export */
  clearLogs(): void {
    this.logs.length = 0;
    if (this.contentDiv) {
      this.contentDiv.replaceChildren();
    }
  }

  private shouldDisplayLog(log: LogData): boolean {
    if (!this.levelFilter) return true;
    const filter = this.levelFilter.value;
    if (filter === 'ALL') return true;
    const levels = ['DEBUG', 'INFO', 'WARNING', 'ERROR', 'FATAL', 'CRITICAL'];
    const minIndex = levels.indexOf(filter);
    const logIndex = levels.indexOf(log.level.toUpperCase());
    if (minIndex === -1 || logIndex === -1) return true;
    return logIndex >= minIndex;
  }

  private renderAll(): void {
    if (!this.contentDiv) return;
    this.contentDiv.replaceChildren();
    for (const log of this.logs) {
      if (this.shouldDisplayLog(log)) {
        this.appendLogElement(log);
      }
    }
    this.scrollToBottom();
  }

  private appendLogElement(log: LogData): void {
    if (!this.contentDiv) return;
    const line = document.createElement('div');
    line.className = `log-line log-${log.level.toLowerCase()}`;
    line.textContent = log.message;
    this.contentDiv.appendChild(line);
    this.scrollToBottom();
  }

  private scrollToBottom(): void {
    if (
      this.contentDiv &&
      (!this.autoscrollCheck || this.autoscrollCheck.checked)
    ) {
      this.contentDiv.scrollTop = this.contentDiv.scrollHeight;
    }
  }

  /** @export */
  getLogCount(): number {
    return this.logs.length;
  }
}

if (!customElements.get('log-viewer')) {
  customElements.define('log-viewer', LogViewerElement);
}

/**
 * Helper factory function to instantiate and upgrade a LogViewerElement.
 */
export function createLogViewer(): LogViewerElement {
  return document.createElement('log-viewer') as LogViewerElement;
}
