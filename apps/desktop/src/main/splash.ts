import { join } from 'path';
import { electron } from '../shared/electron';

const { BrowserWindow } = electron;

let splashWindow: InstanceType<typeof BrowserWindow> | null = null;
let fallbackTimer: ReturnType<typeof setTimeout> | null = null;

export function createSplash(onDone: () => void): void {
  const splashPath = process.env['ELECTRON_RENDERER_URL']
    ? join(__dirname, '../../src/renderer/splash.html')
    : join(__dirname, '../renderer/splash.html');

  splashWindow = new BrowserWindow({
    width: 480,
    height: 100,
    frame: false,
    alwaysOnTop: true,
    center: true,
    resizable: false,
    skipTaskbar: true,
    show: false,
    backgroundColor: '#ffffff',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  const wc = splashWindow.webContents;

  // Animation completion signal
  const onTitle = (_event: unknown, title: string) => {
    if (title === 'DONE') {
      cleanup();
      onDone();
    }
  };
  splashWindow.on('page-title-updated', onTitle);

  // Fallback: if GIF never signals, close after 8s
  fallbackTimer = setTimeout(() => {
    if (splashWindow && !splashWindow.isDestroyed()) {
      cleanup();
      onDone();
    }
  }, 8000);

  // Window closed externally
  splashWindow.once('closed', () => {
    cleanup();
  });

  // Renderer failure
  wc.on('did-fail-load', (_event, code, desc) => {
    console.error(`[splash] load failed: ${code} ${desc}`);
    cleanup();
    onDone();
  });

  wc.on('render-process-gone', (_event, details) => {
    console.error(`[splash] renderer gone: ${details.reason}`);
    cleanup();
    onDone();
  });

  function cleanup() {
    if (fallbackTimer) {
      clearTimeout(fallbackTimer);
      fallbackTimer = null;
    }
    splashWindow?.off('page-title-updated', onTitle);
  }

  splashWindow.loadFile(splashPath);

  splashWindow.once('ready-to-show', () => {
    splashWindow?.show();
  });
}

export function closeSplash(): Promise<void> {
  return new Promise((resolve) => {
    if (!splashWindow || splashWindow.isDestroyed()) {
      splashWindow = null;
      resolve();
      return;
    }
    splashWindow.destroy();
    splashWindow = null;
    resolve();
  });
}
