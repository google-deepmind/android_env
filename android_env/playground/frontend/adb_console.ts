import {AdbResponseData, SocketHandler} from './socket';

/**
 * Interface representing an entry in the ADB console history.
 */
export interface AdbConsoleEntry {
  command: string;
  status: string;
  output: string;
  error?: string;
  duration_ms?: number;
  timestamp: string;
}

const PRESET_COMMANDS: ReadonlyArray<{label: string; cmd: string}> = [
  {label: 'Current Activity', cmd: 'shell dumpsys activity activities'},
  {label: 'List Packages', cmd: 'shell pm list packages'},
  {label: 'Battery State', cmd: 'shell dumpsys battery'},
  {label: 'System Props', cmd: 'shell getprop'},
  {label: 'Screen Size', cmd: 'shell wm size'},
  {label: 'Devices', cmd: 'devices -l'},
];

/**
 * Custom Web Component for ADB shell execution and history in the Playground UI.
 */
export class AdbConsoleElement extends HTMLElement {
  private socket: SocketHandler | null = null;
  private outputDiv: HTMLElement | null = null;
  private inputEl: HTMLInputElement | null = null;
  private runBtn: HTMLButtonElement | null = null;
  private readonly history: AdbConsoleEntry[] = [];
  private readonly commandHistory: string[] = [];
  private historyIndex = -1;

  constructor() {
    super();
  }

  /** @export */
  connectedCallback(): void {
    if (!this.outputDiv) {
      this.classList.add('adb-console-root');

      const presetChips = document.createElement('div');
      presetChips.className = 'preset-chips';
      for (const preset of PRESET_COMMANDS) {
        const btn = document.createElement('button');
        btn.className = 'chip';
        btn.setAttribute('data-adb', preset.cmd);
        btn.textContent = preset.label;
        presetChips.appendChild(btn);
      }
      this.appendChild(presetChips);

      const output = document.createElement('div');
      output.id = 'adb-output';
      output.className = 'adb-output';
      this.appendChild(output);
      this.outputDiv = output;

      const inputRow = document.createElement('div');
      inputRow.className = 'adb-input-row';

      const prompt = document.createElement('span');
      prompt.className = 'adb-prompt';
      prompt.textContent = '$ adb';
      inputRow.appendChild(prompt);

      const input = document.createElement('input');
      input.type = 'text';
      input.id = 'adb-input';
      input.placeholder =
        'shell pm list packages -3 (Press Enter to run)';
      inputRow.appendChild(input);
      this.inputEl = input;

      const runBtn = document.createElement('button');
      runBtn.id = 'adb-run-btn';
      runBtn.className = 'btn btn-primary';
      runBtn.textContent = 'Run';
      inputRow.appendChild(runBtn);
      this.runBtn = runBtn;

      this.appendChild(inputRow);
      this.initEventListeners();
    }
  }

  /** @export */
  setSocket(socket: SocketHandler): void {
    this.socket = socket;
  }

  private initEventListeners(): void {
    this.runBtn?.addEventListener('click', () => {
      this.runInput();
    });

    this.inputEl?.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        this.runInput();
      } else if (e.key === 'ArrowUp') {
        this.navigateHistory(-1);
        e.preventDefault();
      } else if (e.key === 'ArrowDown') {
        this.navigateHistory(1);
        e.preventDefault();
      }
    });

    this.querySelectorAll('.chip[data-adb]').forEach((chip) => {
      chip.addEventListener('click', () => {
        const cmd = chip.getAttribute('data-adb');
        if (cmd) {
          this.executeCommand(cmd);
        }
      });
    });
  }

  /** @export */
  executeCommand(command: string): void {
    const clean = command.trim();
    if (!clean) return;
    this.commandHistory.push(clean);
    this.historyIndex = this.commandHistory.length;
    this.socket?.sendAdbCommand(clean);
  }

  /** @export */
  handleAdbResponse(resp: AdbResponseData): void {
    const entry: AdbConsoleEntry = {
      command: resp.command,
      status: resp.status,
      output: resp.output,
      error: resp.error,
      duration_ms: resp.duration_ms,
      timestamp: new Date().toLocaleTimeString(),
    };
    this.history.push(entry);
    this.renderEntry(entry);
  }

  private renderEntry(entry: AdbConsoleEntry): void {
    if (!this.outputDiv) return;
    const div = document.createElement('div');
    div.className = 'adb-entry';
    const statusColor =
      entry.status === 'OK' ? 'var(--success)' : 'var(--danger)';
    const duration =
      entry.duration_ms !== undefined
        ? ` (${entry.duration_ms.toFixed(1)}ms)`
        : '';

    const cmdHeader = document.createElement('div');
    cmdHeader.className = 'adb-cmd-line';

    const cmdSpan = document.createElement('span');
    cmdSpan.textContent = `$ adb ${entry.command}`;

    const statusSpan = document.createElement('span');
    statusSpan.style.color = statusColor;
    statusSpan.style.fontSize = '11px';
    statusSpan.textContent = `${entry.status}${duration}`;

    cmdHeader.appendChild(cmdSpan);
    cmdHeader.appendChild(statusSpan);

    const body = document.createElement('div');
    body.className = 'adb-body';
    body.textContent = entry.output || entry.error || '(no output)';

    div.appendChild(cmdHeader);
    div.appendChild(body);
    this.outputDiv.appendChild(div);
    this.outputDiv.scrollTop = this.outputDiv.scrollHeight;
  }

  private runInput(): void {
    if (!this.inputEl) return;
    const val = this.inputEl.value.trim();
    if (val) {
      this.executeCommand(val);
      this.inputEl.value = '';
    }
  }

  private navigateHistory(direction: number): void {
    if (this.commandHistory.length === 0 || !this.inputEl) return;
    this.historyIndex += direction;
    if (this.historyIndex < 0) this.historyIndex = 0;
    if (this.historyIndex > this.commandHistory.length) {
      this.historyIndex = this.commandHistory.length;
    }
    if (this.historyIndex === this.commandHistory.length) {
      this.inputEl.value = '';
    } else {
      this.inputEl.value = this.commandHistory[this.historyIndex];
    }
  }

  /** @export */
  getHistory(): AdbConsoleEntry[] {
    return [...this.history];
  }

  /** @export */
  clear(): void {
    this.history.length = 0;
    if (this.outputDiv) {
      this.outputDiv.replaceChildren();
    }
  }
}

if (!customElements.get('adb-console')) {
  customElements.define('adb-console', AdbConsoleElement);
}

/**
 * Helper factory function to instantiate and upgrade an AdbConsoleElement.
 */
export function createAdbConsole(socket?: SocketHandler): AdbConsoleElement {
  const el = document.createElement('adb-console') as AdbConsoleElement;
  if (socket) {
    el.setSocket(socket);
  }
  return el;
}
