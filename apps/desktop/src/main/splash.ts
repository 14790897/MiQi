import { join } from 'path';
import { electron } from '../shared/electron';

const { BrowserWindow } = electron;

let splashWindow: InstanceType<typeof BrowserWindow> | null = null;
let splashReady = false;

export function createSplash(): void {
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
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: false,
    },
  });

  splashWindow.loadFile(splashPath);

  splashWindow.once('ready-to-show', () => {
    splashReady = true;
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

    const win = splashWindow;

    const cleanup = () => {
      if (!win.isDestroyed()) {
        win.destroy();
      }
      splashWindow = null;
      resolve();
    };

    if (!splashReady) {
      cleanup();
      return;
    }

    cleanup();
  });
}
