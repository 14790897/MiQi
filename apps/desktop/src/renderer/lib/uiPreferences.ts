export type ThemeMode = 'light' | 'dark' | 'system';
export type FontScale = 'sm' | 'md' | 'lg' | 'xl';
export type FontFamilyOption = 'system' | 'inter' | 'source';
export type EmojiMode = 'color' | 'mono';

const THEME_KEY = 'miqi-theme';
const FONT_SCALE_KEY = 'miqi-font-scale';
const FONT_FAMILY_KEY = 'miqi-font-family';
export const EMOJI_MODE_KEY = 'miqi-emoji-mode';

let systemThemeMedia: MediaQueryList | null = null;
let systemThemeHandler: ((event: MediaQueryListEvent) => void) | null = null;

/** Read a stored preference with a safe fallback when localStorage is unavailable. */
function readStored<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T | null) ?? fallback;
  } catch {
    return fallback;
  }
}

/** Apply the selected theme to the document root. */
export function applyTheme(mode: ThemeMode) {
  if (typeof window === 'undefined') return;
  const root = document.documentElement;
  if (mode === 'dark') {
    root.classList.add('dark');
  } else if (mode === 'light') {
    root.classList.remove('dark');
  } else {
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    root.classList.toggle('dark', prefersDark);
  }
}

/** Keep the system theme in sync while the user stays in `system` mode. */
export function initSystemThemeListener() {
  if (typeof window === 'undefined') return;
  const media = window.matchMedia('(prefers-color-scheme: dark)');
  const handler = (event: MediaQueryListEvent) => {
    if (readStored<ThemeMode>(THEME_KEY, 'system') === 'system') {
      document.documentElement.classList.toggle('dark', event.matches);
    }
  };
  if (systemThemeMedia && systemThemeHandler) {
    systemThemeMedia.removeEventListener('change', systemThemeHandler);
  }
  systemThemeMedia = media;
  systemThemeHandler = handler;
  media.addEventListener('change', handler);
}

/** Apply scale and family font preferences to the document root. */
export function applyFontPreferences(scale: FontScale, family: FontFamilyOption) {
  if (typeof document === 'undefined') return;
  const root = document.documentElement;
  root.dataset.fontScale = scale;
  root.dataset.fontFamily = family;
}

/** Apply color or monochrome emoji presentation. */
export function applyEmojiPreference(mode: EmojiMode) {
  if (typeof document === 'undefined') return;
  document.documentElement.dataset.emojiMode = mode;
}

/** Restore all persisted UI preferences before the first render. */
export function applyStoredUiPreferences() {
  const theme = readStored<ThemeMode>(THEME_KEY, 'system');
  applyTheme(theme);
  applyFontPreferences(
    readStored<FontScale>(FONT_SCALE_KEY, 'md'),
    readStored<FontFamilyOption>(FONT_FAMILY_KEY, 'system')
  );
  applyEmojiPreference(readStored<EmojiMode>(EMOJI_MODE_KEY, 'color'));
  initSystemThemeListener();
}
