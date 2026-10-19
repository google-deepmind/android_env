import 'jasmine';
import {createAdbConsole, AdbConsoleElement} from './adb_console';
import {SocketHandler} from './socket';

describe('AdbConsoleElement', () => {
  let socketMock: jasmine.SpyObj<SocketHandler>;
  let element: AdbConsoleElement;

  beforeEach(() => {
    socketMock = jasmine.createSpyObj<SocketHandler>('SocketHandler', [
      'sendAdbCommand',
    ]);

    element = createAdbConsole(socketMock);
    document.body.appendChild(element);
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('renders adb console with chips, output area, and input controls', () => {
    expect(element.querySelector('.preset-chips')).toBeTruthy();
    expect(element.querySelector('#adb-output')).toBeTruthy();
    expect(element.querySelector('#adb-input')).toBeTruthy();
    expect(element.querySelector('#adb-run-btn')).toBeTruthy();
  });

  it('sends adb command on Run button click and Enter key', () => {
    const input = element.querySelector('#adb-input') as HTMLInputElement;
    const runBtn = element.querySelector('#adb-run-btn') as HTMLButtonElement;

    input.value = 'shell wm size';
    runBtn.click();
    expect(socketMock.sendAdbCommand).toHaveBeenCalledWith('shell wm size');
    expect(input.value).toBe('');

    socketMock.sendAdbCommand.calls.reset();
    input.value = 'shell getprop';
    input.dispatchEvent(new KeyboardEvent('keydown', {key: 'Enter'}));
    expect(socketMock.sendAdbCommand).toHaveBeenCalledWith('shell getprop');
    expect(input.value).toBe('');
  });

  it('sends adb command when chip is clicked', () => {
    const chip = element.querySelector(
      '.chip[data-adb="devices -l"]'
    ) as HTMLElement;
    expect(chip).toBeTruthy();
    chip.click();
    expect(socketMock.sendAdbCommand).toHaveBeenCalledWith('devices -l');
  });

  it('renders adb response and clears history', () => {
    element.handleAdbResponse({
      command: 'shell wm size',
      status: 'OK',
      output: 'Physical size: 1080x1920',
      duration_ms: 5.4,
    });

    const outputDiv = element.querySelector('#adb-output') as HTMLElement;
    expect(outputDiv.children.length).toBe(1);
    expect(outputDiv.textContent).toContain('shell wm size');
    expect(outputDiv.textContent).toContain('Physical size: 1080x1920');
    expect(element.getHistory().length).toBe(1);

    element.clear();
    expect(outputDiv.children.length).toBe(0);
    expect(element.getHistory().length).toBe(0);
  });

  it('navigates command history with ArrowUp and ArrowDown', () => {
    const input = element.querySelector('#adb-input') as HTMLInputElement;

    element.executeCommand('cmd1');
    element.executeCommand('cmd2');

    input.dispatchEvent(
      new KeyboardEvent('keydown', {key: 'ArrowUp', cancelable: true})
    );
    expect(input.value).toBe('cmd2');

    input.dispatchEvent(
      new KeyboardEvent('keydown', {key: 'ArrowUp', cancelable: true})
    );
    expect(input.value).toBe('cmd1');

    input.dispatchEvent(
      new KeyboardEvent('keydown', {key: 'ArrowDown', cancelable: true})
    );
    expect(input.value).toBe('cmd2');

    input.dispatchEvent(
      new KeyboardEvent('keydown', {key: 'ArrowDown', cancelable: true})
    );
    expect(input.value).toBe('');

    // Beyond history boundary
    input.dispatchEvent(
      new KeyboardEvent('keydown', {key: 'ArrowDown', cancelable: true})
    );
    expect(input.value).toBe('');
  });
});
