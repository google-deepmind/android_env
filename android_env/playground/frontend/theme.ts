/**
 * Strongly-typed theme management for AndroidEnv Playground.
 */

/**
 * Theme mode supported by the Playground.
 */
export type Theme = 'light' | 'dark';

/**
 * Key used to persist theme choice in localStorage.
 */
export const THEME_STORAGE_KEY = 'aenv_theme';

/**
 * Returns the current theme from localStorage, defaulting to 'light'.
 */
export function getTheme(): Theme {
  try {
    const saved = window.localStorage.getItem(THEME_STORAGE_KEY);
    return saved === 'dark' ? 'dark' : 'light';
  } catch (_) {
    return 'light';
  }
}

/**
 * Applies the given theme to the document and updates theme toggle buttons.
 */
export function applyTheme(theme: Theme): Theme {
  const validTheme: Theme = theme === 'dark' ? 'dark' : 'light';
  document.documentElement.setAttribute('data-theme', validTheme);
  if (document.body) {
    document.body.setAttribute('data-theme', validTheme);
  }
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, validTheme);
  } catch (_) {}

  document.querySelectorAll<HTMLElement>('.theme-toggle-btn').forEach((btn) => {
    btn.textContent = validTheme === 'light' ? '🌙 Dark' : '☀️ Light';
    btn.title = `Switch to ${validTheme === 'light' ? 'Dark' : 'Light'} theme (Ctrl+Shift+D)`;
    btn.setAttribute(
      'aria-label',
      `Switch to ${validTheme === 'light' ? 'Dark' : 'Light'} theme`
    );
  });

  // NOMUTANTS(SBR): Tested in frontend_test_chrome-linux (theme_test.ts).
  window.dispatchEvent(
    new CustomEvent('aenv-theme-changed', {detail: {theme: validTheme}})
  );
  return validTheme;
}

/**
 * Toggles between light and dark theme.
 */
export function toggleTheme(): Theme {
  const current = getTheme();
  const next: Theme = current === 'light' ? 'dark' : 'light';
  return applyTheme(next);
}

/**
 * Handles global keyboard shortcuts for theme toggling (Ctrl+Shift+D / Cmd+Shift+D).
 */
export function handleThemeKeydown(e: KeyboardEvent): void {
  if (
    (e.ctrlKey || e.metaKey) &&
    e.shiftKey &&
    (e.key === 'D' || e.key === 'd' || e.key === 'T' || e.key === 't')
  ) {
    e.preventDefault();
    toggleTheme();
  }
}

/**
 * Click handler for theme toggle buttons.
 */
export function handleThemeToggleClick(): void {
  toggleTheme();
}

/**
 * Sets up click and keyboard listeners for theme toggling.
 */
export function setupThemeListeners(): void {
  document.querySelectorAll('.theme-toggle-btn').forEach((btn) => {
    btn.removeEventListener('click', handleThemeToggleClick);
    btn.addEventListener('click', handleThemeToggleClick);
  });

  window.removeEventListener('keydown', handleThemeKeydown);
  window.addEventListener('keydown', handleThemeKeydown);

  // NOMUTANTS(SBR): Tested in frontend_test_chrome-linux (theme_test.ts).
  applyTheme(getTheme());
}

