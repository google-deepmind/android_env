import 'jasmine';
import {
  captureScreenshot,
  createScreenControls,
  initHardwareControls,
  ScreenControlsElement,
} from './controls';
import {SocketHandler} from './socket';

describe('ScreenControlsElement', () => {
  let screenImg: HTMLImageElement;
  let socketMock: jasmine.SpyObj<SocketHandler>;
  let element: ScreenControlsElement;

  beforeEach(() => {
    socketMock = jasmine.createSpyObj<SocketHandler>('SocketHandler', [
      'sendAction',
      'sendText',
      'sendKeydown',
      'sendClipboard',
      'sendSelection',
    ]);

    element = createScreenControls(socketMock);
    element.id = 'screen-controls';
    document.body.appendChild(element);

    screenImg = element.querySelector('#screen') as HTMLImageElement;

    // Mock getBoundingClientRect for deterministic coordinates calculation
    spyOn(screenImg, 'getBoundingClientRect').and.returnValue({
      left: 100,
      top: 100,
      right: 300,
      bottom: 500,
      width: 200,
      height: 400,
      x: 100,
      y: 100,
      toJSON: () => {},
    });
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('initializes custom element successfully', () => {
    expect(element).toBeTruthy();
    expect(element.tagName.toLowerCase()).toBe('screen-controls');
    expect(screenImg).toBeTruthy();
    expect(element.getScreenImage()).toBe(screenImg);
    expect(element.innerHTML).toBe('<div id="container"><img id="screen"></div>');

    // Calling connectedCallback again is idempotent
    element.connectedCallback();
    expect(element.children.length).toBe(1);
  });

  it('removes window listeners on disconnectedCallback', () => {
    screenImg.dispatchEvent(
      new MouseEvent('mousedown', {clientX: 150, clientY: 200})
    );
    socketMock.sendAction.calls.reset();

    element.remove();

    window.dispatchEvent(
      new MouseEvent('mouseup', {clientX: 150, clientY: 200})
    );
    const endEvent: Event = new CustomEvent('touchend', {cancelable: true});
    Object.defineProperty(endEvent, 'changedTouches', {
      value: [{clientX: 150, clientY: 200}],
    });
    window.dispatchEvent(endEvent);
    window.dispatchEvent(new KeyboardEvent('keydown', {key: 'a'}));

    expect(socketMock.sendAction).not.toHaveBeenCalled();
    expect(socketMock.sendText).not.toHaveBeenCalled();
  });

  it('sends touch_down action on mousedown', () => {
    const event = new MouseEvent('mousedown', {
      clientX: 200, // (200-100)/200 = 0.5
      clientY: 300, // (300-100)/400 = 0.5
    });
    screenImg.dispatchEvent(event);

    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_down', 0.5, 0.5);
  });

  it('sends touch_move action when mouse move occurs while pressed', () => {
    // First press down
    screenImg.dispatchEvent(
      new MouseEvent('mousedown', {clientX: 150, clientY: 200})
    );
    socketMock.sendAction.calls.reset();

    // Now move
    const event = new MouseEvent('mousemove', {
      clientX: 200, // (200-100)/200 = 0.5
      clientY: 200, // (200-100)/400 = 0.25
    });
    screenImg.dispatchEvent(event);

    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_move', 0.5, 0.25);
  });

  it('sends touch_up action on mouseup', () => {
    screenImg.dispatchEvent(
      new MouseEvent('mousedown', {clientX: 150, clientY: 200})
    );
    socketMock.sendAction.calls.reset();

    const event = new MouseEvent('mouseup', {
      clientX: 150,
      clientY: 200,
    });
    window.dispatchEvent(event);

    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_up', 0.25, 0.25);
  });

  it('prevents default on dragstart', () => {
    const event = new Event('dragstart', {cancelable: true});
    screenImg.dispatchEvent(event);
    expect(event.defaultPrevented).toBeTrue();
  });

  it('handles touchstart, touchmove, and touchend events', () => {
    const touchObj = {clientX: 200, clientY: 300};

    const startEvent: Event = new CustomEvent('touchstart', {
      cancelable: true,
    });
    Object.defineProperty(startEvent, 'touches', {value: [touchObj]});
    screenImg.dispatchEvent(startEvent);

    expect(startEvent.defaultPrevented).toBeTrue();
    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_down', 0.5, 0.5);
    socketMock.sendAction.calls.reset();

    const moveTouchObj = {clientX: 200, clientY: 200};
    const moveEvent: Event = new CustomEvent('touchmove', {cancelable: true});
    Object.defineProperty(moveEvent, 'touches', {value: [moveTouchObj]});
    screenImg.dispatchEvent(moveEvent);

    expect(moveEvent.defaultPrevented).toBeTrue();
    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_move', 0.5, 0.25);
    socketMock.sendAction.calls.reset();

    const endTouchObj = {clientX: 150, clientY: 200};
    const endEvent: Event = new CustomEvent('touchend', {cancelable: true});
    Object.defineProperty(endEvent, 'changedTouches', {value: [endTouchObj]});
    window.dispatchEvent(endEvent);

    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_up', 0.25, 0.25);
  });

  it('ignores mousemove, mouseup, touchmove, and touchend when not down', () => {
    screenImg.dispatchEvent(
      new MouseEvent('mousemove', {clientX: 200, clientY: 200})
    );
    window.dispatchEvent(
      new MouseEvent('mouseup', {clientX: 200, clientY: 200})
    );
    const moveEvent: Event = new CustomEvent('touchmove', {cancelable: true});
    Object.defineProperty(moveEvent, 'touches', {
      value: [{clientX: 200, clientY: 200}],
    });
    screenImg.dispatchEvent(moveEvent);
    const endEvent: Event = new CustomEvent('touchend', {cancelable: true});
    Object.defineProperty(endEvent, 'changedTouches', {
      value: [{clientX: 200, clientY: 200}],
    });
    window.dispatchEvent(endEvent);
    expect(socketMock.sendAction).not.toHaveBeenCalled();
  });

  it('throttles mousemove events within throttle window', () => {
    screenImg.dispatchEvent(
      new MouseEvent('mousedown', {clientX: 150, clientY: 200})
    );
    socketMock.sendAction.calls.reset();

    screenImg.dispatchEvent(
      new MouseEvent('mousemove', {clientX: 200, clientY: 200})
    );
    expect(socketMock.sendAction).toHaveBeenCalledTimes(1);

    // Immediate second move should be throttled out
    screenImg.dispatchEvent(
      new MouseEvent('mousemove', {clientX: 220, clientY: 220})
    );
    expect(socketMock.sendAction).toHaveBeenCalledTimes(1);
  });

  it('throttles touchmove events within throttle window', () => {
    const startEvent: Event = new CustomEvent('touchstart', {
      cancelable: true,
    });
    Object.defineProperty(startEvent, 'touches', {
      value: [{clientX: 150, clientY: 200}],
    });
    screenImg.dispatchEvent(startEvent);
    socketMock.sendAction.calls.reset();

    const moveEvent1: Event = new CustomEvent('touchmove', {
      cancelable: true,
    });
    Object.defineProperty(moveEvent1, 'touches', {
      value: [{clientX: 200, clientY: 200}],
    });
    screenImg.dispatchEvent(moveEvent1);
    expect(socketMock.sendAction).toHaveBeenCalledTimes(1);

    const moveEvent2: Event = new CustomEvent('touchmove', {
      cancelable: true,
    });
    Object.defineProperty(moveEvent2, 'touches', {
      value: [{clientX: 220, clientY: 220}],
    });
    screenImg.dispatchEvent(moveEvent2);
    expect(socketMock.sendAction).toHaveBeenCalledTimes(1);
  });

  it('handles empty touches or changedTouches list gracefully', () => {
    const startEvent: Event = new CustomEvent('touchstart', {
      cancelable: true,
    });
    Object.defineProperty(startEvent, 'touches', {value: []});
    screenImg.dispatchEvent(startEvent);

    const moveEvent: Event = new CustomEvent('touchmove', {cancelable: true});
    Object.defineProperty(moveEvent, 'touches', {value: []});
    screenImg.dispatchEvent(moveEvent);

    const endEvent: Event = new CustomEvent('touchend', {cancelable: true});
    Object.defineProperty(endEvent, 'changedTouches', {value: []});
    window.dispatchEvent(endEvent);

    expect(socketMock.sendAction).not.toHaveBeenCalled();
  });

  it('clamps coordinates to [0, 1] range', () => {
    // Negative coordinates (outside top-left)
    screenImg.dispatchEvent(
      new MouseEvent('mousedown', {clientX: 50, clientY: 50})
    );
    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_down', 0, 0);

    // Over-boundary coordinates (outside bottom-right)
    screenImg.dispatchEvent(
      new MouseEvent('mousedown', {clientX: 500, clientY: 600})
    );
    expect(socketMock.sendAction).toHaveBeenCalledWith('touch_down', 1, 1);
  });

  it('sends text on printable keydown event and prevents default', () => {
    const event = new KeyboardEvent('keydown', {key: 'a', cancelable: true});
    window.dispatchEvent(event);
    expect(socketMock.sendText).toHaveBeenCalledWith('a');
    expect(event.defaultPrevented).toBeTrue();
  });

  it('sends keydown on Enter and Backspace keydown events', () => {
    const enterEvent = new KeyboardEvent('keydown', {
      key: 'Enter',
      cancelable: true,
    });
    window.dispatchEvent(enterEvent);
    expect(socketMock.sendKeydown).toHaveBeenCalledWith(66);
    expect(enterEvent.defaultPrevented).toBeTrue();

    const backspaceEvent = new KeyboardEvent('keydown', {
      key: 'Backspace',
      cancelable: true,
    });
    window.dispatchEvent(backspaceEvent);
    expect(socketMock.sendKeydown).toHaveBeenCalledWith(67);
    expect(backspaceEvent.defaultPrevented).toBeTrue();
  });

  it('sends clipboard commands on Ctrl/Meta+C, X, V, A and prevents default', () => {
    const copyEvent = new KeyboardEvent('keydown', {
      key: 'C',
      metaKey: true,
      cancelable: true,
    });
    window.dispatchEvent(copyEvent);
    expect(socketMock.sendClipboard).toHaveBeenCalledWith('copy');
    expect(copyEvent.defaultPrevented).toBeTrue();

    const cutEvent = new KeyboardEvent('keydown', {
      key: 'x',
      ctrlKey: true,
      cancelable: true,
    });
    window.dispatchEvent(cutEvent);
    expect(socketMock.sendClipboard).toHaveBeenCalledWith('cut');
    expect(cutEvent.defaultPrevented).toBeTrue();

    const pasteEvent = new KeyboardEvent('keydown', {
      key: 'v',
      ctrlKey: true,
      cancelable: true,
    });
    window.dispatchEvent(pasteEvent);
    expect(socketMock.sendClipboard).toHaveBeenCalledWith('paste');
    expect(pasteEvent.defaultPrevented).toBeTrue();

    const selectEvent = new KeyboardEvent('keydown', {
      key: 'a',
      ctrlKey: true,
      cancelable: true,
    });
    window.dispatchEvent(selectEvent);
    expect(socketMock.sendSelection).toHaveBeenCalledWith(0, -1);
    expect(selectEvent.defaultPrevented).toBeTrue();
  });

  it('ignores keydown when focused on input or textarea element', () => {
    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    window.dispatchEvent(new KeyboardEvent('keydown', {key: 'a'}));
    expect(socketMock.sendText).not.toHaveBeenCalled();

    const textarea = document.createElement('textarea');
    document.body.appendChild(textarea);
    textarea.focus();

    window.dispatchEvent(new KeyboardEvent('keydown', {key: 'b'}));
    expect(socketMock.sendText).not.toHaveBeenCalled();
  });

  it('ignores keydown when altKey is pressed', () => {
    window.dispatchEvent(
      new KeyboardEvent('keydown', {key: 'a', altKey: true})
    );
    expect(socketMock.sendText).not.toHaveBeenCalled();
    expect(socketMock.sendKeydown).not.toHaveBeenCalled();
  });

  it('sends DPAD keydown on ArrowLeft, ArrowRight, ArrowUp, and ArrowDown', () => {
    const arrowMap: Array<[string, number]> = [
      ['ArrowLeft', 21],
      ['ArrowRight', 22],
      ['ArrowUp', 19],
      ['ArrowDown', 20],
    ];
    for (const [key, code] of arrowMap) {
      const event = new KeyboardEvent('keydown', {key, cancelable: true});
      window.dispatchEvent(event);
      expect(socketMock.sendKeydown).toHaveBeenCalledWith(code);
      expect(event.defaultPrevented).toBeTrue();
    }
  });

  it('sends keydown on Delete, Tab, Escape, Home, End, PageUp, and PageDown', () => {
    const keyMap: Array<[string, number]> = [
      ['Delete', 112],
      ['Tab', 61],
      ['Escape', 4],
      ['Home', 122],
      ['End', 123],
      ['PageUp', 92],
      ['PageDown', 93],
    ];
    for (const [key, code] of keyMap) {
      const event = new KeyboardEvent('keydown', {key, cancelable: true});
      window.dispatchEvent(event);
      expect(socketMock.sendKeydown).toHaveBeenCalledWith(code);
      expect(event.defaultPrevented).toBeTrue();
    }
  });

  it('captures screenshot cleanly', () => {
    expect(captureScreenshot(null)).toBeFalse();

    const img = document.createElement('img');
    expect(captureScreenshot(img)).toBeFalse();

    img.src = 'data:image/png;base64,iVBORw0KGgo=';
    const result = captureScreenshot(img);
    expect(result).toBeTrue();
  });

  it('downloads the screenshot via an anchor with a JPEG data URL', () => {
    const clickSpy = spyOn(HTMLAnchorElement.prototype, 'click');
    const img = document.createElement('img');
    img.src = 'data:image/png;base64,iVBORw0KGgo=';

    expect(captureScreenshot(img, 'shot.jpg')).toBeTrue();

    expect(clickSpy).toHaveBeenCalledTimes(1);
    const anchor = clickSpy.calls.mostRecent().object as HTMLAnchorElement;
    expect(anchor.href).toMatch(/^data:image\/jpeg/);
    expect(anchor.download).toBe('shot.jpg');
  });

  it('binds hardware controls, shot, reset, and send text buttons', () => {
    document.body.innerHTML = `
      <button class="hw-btn" data-key="26">Power</button>
      <button id="shot-btn">Shot</button>
      <button id="reset-btn">Reset</button>
      <input type="text" id="send-text-input" value="hello world" />
      <button id="send-text-btn">Send</button>
      <img id="screen" src="data:image/png;base64,iVBORw0KGgo=" />
    `;

    const socketSpy = jasmine.createSpyObj<SocketHandler>('SocketHandler', [
      'sendKeydown',
      'sendReset',
      'sendText',
    ]);

    initHardwareControls(socketSpy);

    const hwBtn = document.querySelector('.hw-btn') as HTMLElement;
    hwBtn.click();
    expect(socketSpy.sendKeydown).toHaveBeenCalledWith(26);

    const resetBtn = document.getElementById('reset-btn') as HTMLElement;
    resetBtn.click();
    expect(socketSpy.sendReset).toHaveBeenCalled();

    const shotBtn = document.getElementById('shot-btn') as HTMLElement;
    shotBtn.click();

    const input = document.getElementById('send-text-input') as HTMLInputElement;
    input.value = 'typed text';
    input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));
    expect(socketSpy.sendText).toHaveBeenCalledWith('typed text');
  });

  it('returns false when captureScreenshot encounters an error', () => {
    const img = document.createElement('img');
    img.src = 'data:image/png;base64,iVBORw0KGgo=';
    const origCreate = document.createElement.bind(document);
    spyOn(document, 'createElement').and.callFake((tagName: string) => {
      if (tagName === 'canvas') {
        throw new Error('Canvas not supported');
      }
      return origCreate(tagName);
    });
    expect(captureScreenshot(img)).toBeFalse();
  });
});



