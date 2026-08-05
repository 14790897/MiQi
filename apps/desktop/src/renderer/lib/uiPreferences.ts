export type ThemeMode = 'light' | 'dark' | 'system';
export type FontScale = 'sm' | 'md' | 'lg' | 'xl';
export type FontFamilyOption = 'system' | 'inter' | 'source';

const THEME_KEY = 'miqi-theme';
const FONT_SCALE_KEY = 'miqi-font-scale';
const FONT_FAMILY_KEY = 'miqi-font-family';

function readStored<T extends string>(key: string, fallback: T): T {
  try {
    return (localStorage.getItem(key) as T | null) ?? fallback;
  } catch {
    return fallback;
  }
}

export function applyTheme(mode: ThemeMode) {
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

export function applyFontPreferences(scale: FontScale, family: FontFamilyOption) {
  const root = document.documentElement;
  root.dataset.fontScale = scale;
  root.dataset.fontFamily = family;
}

export function applyStoredUiPreferences() {
  applyTheme(readStored<ThemeMode>(THEME_KEY, 'system'));
  applyFontPreferences(
    readStored<FontScale>(FONT_SCALE_KEY, 'md'),
    readStored<FontFamilyOption>(FONT_FAMILY_KEY, 'system')
  );
}
