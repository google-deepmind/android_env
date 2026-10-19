import {SocketHandler} from './socket';

/**
 * Custom Web Component for loading tasks in AndroidEnv Playground.
 */
export class TaskLoaderElement extends HTMLElement {
  private taskInput: HTMLInputElement | null = null;
  private loadTaskBtn: HTMLButtonElement | null = null;
  private socket: SocketHandler | null = null;

  constructor() {
    super();
  }

  /** @export */
  connectedCallback(): void {
    if (!this.taskInput) {
      const container = document.createElement('div');
      container.style.cssText = 'display: flex; gap: 10px; align-items: center;';

      const input = document.createElement('input');
      input.type = 'text';
      input.id = 'task-name';
      input.placeholder = 'Task ID (e.g. classic_2048)';
      input.style.cssText =
        'background: var(--bg-input, #12151b); color: var(--text-main, #e6edf3); border: 1px solid var(--border, #2a2f3a); padding: 6px 10px; border-radius: 6px; font-size: 12px; font-family: var(--font-sans); outline: none;';

      const button = document.createElement('button');
      button.id = 'load-task-btn';
      button.className = 'btn btn-primary';
      button.textContent = 'Load Task';
      button.style.cssText =
        'padding: 6px 11px; border-radius: 6px; font-size: 12px; font-weight: 600; cursor: pointer;';

      container.appendChild(input);
      container.appendChild(button);
      this.appendChild(container);

      this.taskInput = input;
      this.loadTaskBtn = button;
      this.initEventListeners();
    }
  }

  /** @export */
  setSocket(socket: SocketHandler): void {
    this.socket = socket;
  }

  private initEventListeners(): void {
    this.loadTaskBtn!.addEventListener('click', () => {
      this.triggerLoadTask();
    });

    this.taskInput!.addEventListener('keydown', (e: KeyboardEvent) => {
      if (e.key === 'Enter') {
        this.triggerLoadTask();
      }
    });
  }

  /** @export */
  triggerLoadTask(): void {
    const taskId = this.taskInput!.value.trim();
    if (taskId) {
      this.socket?.loadTask(taskId);
      this.dispatchEvent(
        new CustomEvent('load-task', {
          bubbles: true,
          composed: true,
          detail: {taskId},
        })
      );
    }
  }
}

if (!customElements.get('task-loader')) {
  customElements.define('task-loader', TaskLoaderElement);
}

/**
 * Helper factory function to instantiate and upgrade a TaskLoaderElement.
 */
export function createTaskLoader(socket?: SocketHandler): TaskLoaderElement {
  const el = document.createElement('task-loader') as TaskLoaderElement;
  if (socket) {
    el.setSocket(socket);
  }
  return el;
}
