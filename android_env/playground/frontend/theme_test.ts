import 'jasmine';
import {
  applyTheme,
  getTheme,
  handleThemeKeydown,
  handleThemeToggleClick,
  setupThemeListeners,
  THEME_STORAGE_KEY,
  toggleTheme,
} from './theme';

describe('theme', () => {
  beforeEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    document.body.innerHTML = `
      <button class="theme-toggle-btn">Toggle</button>
    `;
  });

  afterEach(() => {
    window.localStorage.clear();
    document.documentElement.removeAttribute('data-theme');
    document.body.innerHTML = '';
  });

  it('defaults to light theme when nothing is in localStorage', () => {
    expect(getTheme()).toBe('light');
  });

  it('retrieves saved dark theme from localStorage', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(getTheme()).toBe('dark');
  });

  it('falls back to light theme if localStorage throws', () => {
    spyOn(window.localStorage, 'getItem').and.throwError('SecurityError');
    expect(getTheme()).toBe('light');
  });

  it('applies theme and updates DOM attributes and toggle buttons', () => {
    let receivedTheme: string | null = null;
    const listener = (e: Event) => {
      receivedTheme = (e as CustomEvent<{theme: string}>).detail.theme;
    };
    window.addEventListener('aenv-theme-changed', listener);

    try {
      const applied = applyTheme('dark');
      expect(applied).toBe('dark');
      expect(receivedTheme as string | null).toBe('dark');
      expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
      expect(document.body.getAttribute('data-theme')).toBe('dark');
      expect(window.localStorage.getItem(THEME_STORAGE_KEY)).toBe('dark');

      const btn = document.querySelector('.theme-toggle-btn') as HTMLElement;
      expect(btn.textContent).toBe('☀️ Light');
      expect(btn.title).toBe('Switch to Light theme (Ctrl+Shift+D)');
      expect(btn.getAttribute('aria-label')).toBe('Switch to Light theme');

      const appliedLight = applyTheme('light');
      expect(appliedLight).toBe('light');
      expect(receivedTheme as string | null).toBe('light');
      expect(document.documentElement.getAttribute('data-theme')).toBe('light');
      expect(btn.textContent).toBe('🌙 Dark');
      expect(btn.title).toBe('Switch to Dark theme (Ctrl+Shift+D)');
      expect(btn.getAttribute('aria-label')).toBe('Switch to Dark theme');
    } finally {
      window.removeEventListener('aenv-theme-changed', listener);
    }
  });

  it('does not throw when localStorage.setItem throws during applyTheme', () => {
    spyOn(window.localStorage, 'setItem').and.throwError('QuotaExceeded');
    expect(() => applyTheme('dark')).not.toThrow();
    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });

  it('toggles theme between light and dark', () => {
    applyTheme('light');
    expect(getTheme()).toBe('light');

    const next = toggleTheme();
    expect(next).toBe('dark');
    expect(getTheme()).toBe('dark');

    const nextAgain = toggleTheme();
    expect(nextAgain).toBe('light');
    expect(getTheme()).toBe('light');
  });

  it('handles keyboard shortcuts in handleThemeKeydown', () => {
    applyTheme('light');

    // Ctrl+Shift+D triggers toggle to dark
    const eventCtrlD = new KeyboardEvent('keydown', {
      key: 'D',
      ctrlKey: true,
      shiftKey: true,
      cancelable: true,
    });
    handleThemeKeydown(eventCtrlD);
    expect(eventCtrlD.defaultPrevented).toBeTrue();
    expect(getTheme()).toBe('dark');

    // Meta+Shift+T triggers toggle to light
    const eventMetaT = new KeyboardEvent('keydown', {
      key: 'T',
      metaKey: true,
      shiftKey: true,
      cancelable: true,
    });
    handleThemeKeydown(eventMetaT);
    expect(eventMetaT.defaultPrevented).toBeTrue();
    expect(getTheme()).toBe('light');

    // Lowercase 'd' with Ctrl+Shift
    const eventLowerD = new KeyboardEvent('keydown', {
      key: 'd',
      ctrlKey: true,
      shiftKey: true,
      cancelable: true,
    });
    handleThemeKeydown(eventLowerD);
    expect(eventLowerD.defaultPrevented).toBeTrue();
    expect(getTheme()).toBe('dark');

    // Negative case: key D without Ctrl/Meta does not toggle
    const eventNoMod = new KeyboardEvent('keydown', {
      key: 'D',
      ctrlKey: false,
      metaKey: false,
      shiftKey: true,
      cancelable: true,
    });
    handleThemeKeydown(eventNoMod);
    expect(eventNoMod.defaultPrevented).toBeFalse();
    expect(getTheme()).toBe('dark');

    // Negative case: Ctrl+D without Shift does not toggle
    const eventNoShift = new KeyboardEvent('keydown', {
      key: 'D',
      ctrlKey: true,
      shiftKey: false,
      cancelable: true,
    });
    handleThemeKeydown(eventNoShift);
    expect(eventNoShift.defaultPrevented).toBeFalse();
    expect(getTheme()).toBe('dark');

    // Negative case: Unrelated key (Ctrl+Shift+X) does not toggle
    const eventOtherKey = new KeyboardEvent('keydown', {
      key: 'X',
      ctrlKey: true,
      shiftKey: true,
      cancelable: true,
    });
    handleThemeKeydown(eventOtherKey);
    expect(eventOtherKey.defaultPrevented).toBeFalse();
    expect(getTheme()).toBe('dark');
  });

  it('handles click events via handleThemeToggleClick', () => {
    applyTheme('light');
    handleThemeToggleClick();
    expect(getTheme()).toBe('dark');
    handleThemeToggleClick();
    expect(getTheme()).toBe('light');
  });

  it('binds click and window keydown listeners in setupThemeListeners idempotently', () => {
    // Calling setupThemeListeners twice should not attach duplicate listeners.
    setupThemeListeners();
    setupThemeListeners();
    const btn = document.querySelector('.theme-toggle-btn') as HTMLElement;

    // A single click should toggle once to dark (not toggle twice back to light)
    btn.click();
    expect(getTheme()).toBe('dark');

    const keyEvent = new KeyboardEvent('keydown', {
      key: 'D',
      ctrlKey: true,
      shiftKey: true,
      cancelable: true,
    });
    window.dispatchEvent(keyEvent);
    expect(keyEvent.defaultPrevented).toBeTrue();
    expect(getTheme()).toBe('light');

    spyOn(window, 'removeEventListener').and.callThrough();
    setupThemeListeners();
    expect(window.removeEventListener).toHaveBeenCalledWith(
      'keydown',
      handleThemeKeydown
    );
  });

  it('applies saved theme during setupThemeListeners', () => {
    window.localStorage.setItem(THEME_STORAGE_KEY, 'dark');
    expect(document.documentElement.getAttribute('data-theme')).toBeNull();

    setupThemeListeners();

    expect(document.documentElement.getAttribute('data-theme')).toBe('dark');
  });
});
