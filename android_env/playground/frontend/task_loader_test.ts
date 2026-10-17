import 'jasmine';
import {SocketHandler} from './socket';
import {createTaskLoader, TaskLoaderElement} from './task_loader';

describe('TaskLoaderElement', () => {
  let taskInput: HTMLInputElement;
  let loadTaskBtn: HTMLButtonElement;
  let socketMock: jasmine.SpyObj<SocketHandler>;
  let element: TaskLoaderElement;

  beforeEach(() => {
    socketMock = jasmine.createSpyObj<SocketHandler>('SocketHandler', [
      'loadTask',
    ]);

    element = createTaskLoader(socketMock);
    element.id = 'task-loader';
    document.body.appendChild(element);

    taskInput = element.querySelector('#task-name') as HTMLInputElement;
    loadTaskBtn = element.querySelector('#load-task-btn') as HTMLButtonElement;
  });

  afterEach(() => {
    document.body.innerHTML = '';
  });

  it('initializes custom element successfully with expected DOM and styles', () => {
    expect(element).toBeTruthy();
    expect(element.tagName.toLowerCase()).toBe('task-loader');
    expect(taskInput).toBeTruthy();
    expect(taskInput.type).toBe('text');
    expect(taskInput.placeholder).toBe('Task ID (e.g. classic_2048)');
    expect(taskInput.style.padding).toBe('6px 10px');
    expect(taskInput.style.background).toContain('var(--bg-input');
    expect(loadTaskBtn).toBeTruthy();
    expect(loadTaskBtn.className).toBe('btn btn-primary');
    expect(loadTaskBtn.textContent).toBe('Load Task');
    expect(loadTaskBtn.style.fontWeight).toBe('600');
    const container = element.firstElementChild as HTMLElement;
    expect(container.style.display).toBe('flex');

    // Calling connectedCallback again is idempotent
    element.connectedCallback();
    expect(element.children.length).toBe(1);
  });

  it('triggers socket.loadTask on button click with trimmed text', () => {
    taskInput.value = '  classic_2048  ';
    loadTaskBtn.click();

    expect(socketMock.loadTask).toHaveBeenCalledWith('classic_2048');
  });

  it('triggers socket.loadTask on Enter keydown in input', () => {
    taskInput.value = 'snake';
    const event = new KeyboardEvent('keydown', {key: 'Enter'});
    taskInput.dispatchEvent(event);

    expect(socketMock.loadTask).toHaveBeenCalledWith('snake');
  });

  it('does not trigger socket.loadTask on non-Enter keydown in input', () => {
    taskInput.value = 'snake';
    const event = new KeyboardEvent('keydown', {key: 'Escape'});
    taskInput.dispatchEvent(event);

    expect(socketMock.loadTask).not.toHaveBeenCalled();
  });

  it('does not trigger socket.loadTask if input is empty', () => {
    taskInput.value = '   ';
    loadTaskBtn.click();

    expect(socketMock.loadTask).not.toHaveBeenCalled();
  });

  it('dispatches load-task event when task is loaded', () => {
    let capturedEvent: CustomEvent<{taskId: string}> | null = null;
    element.addEventListener('load-task', (e: Event) => {
      capturedEvent = e as CustomEvent<{taskId: string}>;
    });

    taskInput.value = 'classic_2048';
    loadTaskBtn.click();

    expect(capturedEvent).not.toBeNull();
    expect(capturedEvent!.detail.taskId).toBe('classic_2048');
    expect(capturedEvent!.bubbles).toBeTrue();
    expect(capturedEvent!.composed).toBeTrue();
  });
});

