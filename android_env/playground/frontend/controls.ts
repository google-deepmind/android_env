import {setAnchorHref} from 'safevalues/dom';
import {SocketHandler} from './socket';

interface Point {
  x: number;
  y: number;
}

const KEY_CODES: Readonly<Record<string, number>> = {
  'ArrowUp': 19,
  'ArrowDown': 20,
  'ArrowLeft': 21,
  'ArrowRight': 22,
  'Enter': 66,
  'Backspace': 67,
  'Delete': 112,
  'Tab': 61,
  'Escape': 4,
  'Home': 122,
  'End': 123,
  'PageUp': 92,
  'PageDown': 93,
};

/**
 * Custom Web Component for handling mouse, touch, and keyboard controls for AndroidEnv.
 */
export class ScreenControlsElement extends HTMLElement {
  private screenImg: HTMLImageElement | null = null;
  private socket: SocketHandler | null = null;
  private isDown = false;
  private lastMoveTime = 0;
  private readonly throttleMs = 16; // ~60 Hz

  private readonly boundMouseMove: (e: MouseEvent) => void;
  private readonly boundMouseUp: (e: MouseEvent) => void;
  private readonly boundTouchMove: (e: TouchEvent) => void;
  private readonly boundTouchEnd: (e: TouchEvent) => void;
  private readonly boundKeyDown: (e: KeyboardEvent) => void;

  constructor() {
    super();
    this.boundMouseMove = this.onMouseMove.bind(this);
    this.boundMouseUp = this.onMouseUp.bind(this);
    this.boundTouchMove = this.onTouchMove.bind(this);
    this.boundTouchEnd = this.onTouchEnd.bind(this);
    this.boundKeyDown = this.onKeyDown.bind(this);
  }

  /** @export */
  connectedCallback(): void {
    if (!this.screenImg) {
      const container = document.createElement('div');
      container.id = 'container';
      const img = document.createElement('img');
      img.id = 'screen';
      container.appendChild(img);
      this.appendChild(container);
      this.screenImg = img;
      this.initEventListeners();
    }

    window.addEventListener('mouseup', this.boundMouseUp);
    window.addEventListener('touchend', this.boundTouchEnd);
    window.addEventListener('keydown', this.boundKeyDown);
  }

  /** @export */
  disconnectedCallback(): void {
    window.removeEventListener('mouseup', this.boundMouseUp);
    window.removeEventListener('touchend', this.boundTouchEnd);
    window.removeEventListener('keydown', this.boundKeyDown);
  }

  /** @export */
  setSocket(socket: SocketHandler): void {
    this.socket = socket;
  }

  /** @export */
  getScreenImage(): HTMLImageElement | null {
    return this.screenImg;
  }

  private getCoords(clientX: number, clientY: number): Point {
    const rect = this.screenImg!.getBoundingClientRect();
    const x = (clientX - rect.left) / rect.width;
    const y = (clientY - rect.top) / rect.height;
    return {
      x: Math.max(0, Math.min(1, x)),
      y: Math.max(0, Math.min(1, y)),
    };
  }

  private initEventListeners(): void {
    this.screenImg!.addEventListener('mousedown', (e: MouseEvent) => {
      this.isDown = true;
      const {x, y} = this.getCoords(e.clientX, e.clientY);
      this.socket?.sendAction('touch_down', x, y);
    });

    this.screenImg!.addEventListener('mousemove', this.boundMouseMove);
    this.screenImg!.addEventListener('dragstart', (e: Event) =>
      e.preventDefault()
    );

    this.screenImg!.addEventListener('touchstart', (e: TouchEvent) => {
      this.isDown = true;
      if (e.touches.length > 0) {
        const touch = e.touches[0];
        const {x, y} = this.getCoords(touch.clientX, touch.clientY);
        this.socket?.sendAction('touch_down', x, y);
      }
      e.preventDefault();
    });

    this.screenImg!.addEventListener('touchmove', this.boundTouchMove);
  }

  private onMouseMove(e: MouseEvent): void {
    if (!this.isDown) return;
    const now = Date.now();
    if (now - this.lastMoveTime < this.throttleMs) return;
    this.lastMoveTime = now;
    const {x, y} = this.getCoords(e.clientX, e.clientY);
    this.socket?.sendAction('touch_move', x, y);
  }

  private onMouseUp(e: MouseEvent): void {
    if (!this.isDown) return;
    this.isDown = false;
    const {x, y} = this.getCoords(e.clientX, e.clientY);
    this.socket?.sendAction('touch_up', x, y);
  }

  private onTouchMove(e: TouchEvent): void {
    if (!this.isDown) return;
    const now = Date.now();
    if (now - this.lastMoveTime < this.throttleMs) return;
    this.lastMoveTime = now;
    if (e.touches.length > 0) {
      const touch = e.touches[0];
      const {x, y} = this.getCoords(touch.clientX, touch.clientY);
      this.socket?.sendAction('touch_move', x, y);
    }
    e.preventDefault();
  }

  private onTouchEnd(e: TouchEvent): void {
    if (!this.isDown) return;
    this.isDown = false;
    if (e.changedTouches.length > 0) {
      const touch = e.changedTouches[0];
      const {x, y} = this.getCoords(touch.clientX, touch.clientY);
      this.socket?.sendAction('touch_up', x, y);
    }
  }

  private onKeyDown(e: KeyboardEvent): void {
    const activeEl = document.activeElement;
    if (
      activeEl &&
      (activeEl.tagName === 'INPUT' || activeEl.tagName === 'TEXTAREA')
    ) {
      return;
    }

    if (e.ctrlKey || e.metaKey) {
      const keyLower = e.key.toLowerCase();
      if (keyLower === 'c') {
        this.socket?.sendClipboard('copy');
        e.preventDefault();
      } else if (keyLower === 'x') {
        this.socket?.sendClipboard('cut');
        e.preventDefault();
      } else if (keyLower === 'v') {
        this.socket?.sendClipboard('paste');
        e.preventDefault();
      } else if (keyLower === 'a') {
        this.socket?.sendSelection(0, -1);
        e.preventDefault();
      }
      return;
    }

    if (e.altKey) {
      return;
    }

    const keycode = KEY_CODES[e.key];
    if (keycode !== undefined) {
      this.socket?.sendKeydown(keycode);
      e.preventDefault();
    } else if (e.key.length === 1) {
      this.socket?.sendText(e.key);
      e.preventDefault();
    }
  }
}

if (!customElements.get('screen-controls')) {
  customElements.define('screen-controls', ScreenControlsElement);
}

/**
 * Helper factory function to instantiate and upgrade a ScreenControlsElement.
 */
export function createScreenControls(
  socket?: SocketHandler
): ScreenControlsElement {
  const el = document.createElement('screen-controls') as ScreenControlsElement;
  if (socket) {
    el.setSocket(socket);
  }
  return el;
}

/**
 * Captures screenshot from the screen <img> element and triggers download.
 */
export function captureScreenshot(
  screenImg: HTMLImageElement | null,
  filename = 'android_env_screenshot.jpg'
): boolean {
  if (!screenImg || !screenImg.src) return false;
  try {
    const canvas = document.createElement('canvas');
    canvas.width = screenImg.naturalWidth || 1080;
    canvas.height = screenImg.naturalHeight || 1920;
    const ctx = canvas.getContext('2d');
    if (!ctx) return false;
    ctx.drawImage(screenImg, 0, 0);
    const dataUrl = canvas.toDataURL('image/jpeg', 0.95);
    const a = document.createElement('a');
    // `setAnchorHref` blocks `javascript:` URLs.
    setAnchorHref(a, dataUrl);
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    setTimeout(() => a.remove(), 100);
    return true;
  } catch (err) {
    console.error('Failed to capture screenshot:', err);
    return false;
  }
}

/**
 * Initializes hardware button rail, episode reset, text input, and screenshot buttons.
 */
export function initHardwareControls(
  socket: SocketHandler,
  screenControls?: ScreenControlsElement | null
): void {
  // Bind hardware buttons
  document
    .querySelectorAll<HTMLElement>('.hw-btn[data-key]')
    .forEach((btn) => {
      btn.addEventListener('click', () => {
        const key = Number(btn.getAttribute('data-key'));
        if (!isNaN(key)) {
          socket.sendKeydown(key);
        }
      });
    });

  // Bind screenshot button
  const shotBtn = document.getElementById('shot-btn');
  if (shotBtn) {
    shotBtn.addEventListener('click', () => {
      const screenImg =
        screenControls?.getScreenImage() ||
        (document.getElementById('screen') as HTMLImageElement | null);
      captureScreenshot(screenImg);
    });
  }

  // Bind episode reset button
  const resetBtn = document.getElementById('reset-btn');
  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      socket.sendReset();
    });
  }

  // Bind send text input & button
  const sendTextBtn = document.getElementById('send-text-btn');
  const sendTextInput = document.getElementById(
    'send-text-input'
  ) as HTMLInputElement | null;
  const doSendText = () => {
    if (sendTextInput && sendTextInput.value) {
      socket.sendText(sendTextInput.value);
      sendTextInput.value = '';
    }
  };
  sendTextBtn?.addEventListener('click', doSendText);
  sendTextInput?.addEventListener('keydown', (e: KeyboardEvent) => {
    if (e.key === 'Enter') {
      doSendText();
    }
  });
}

