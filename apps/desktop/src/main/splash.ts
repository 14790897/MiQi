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
    backgroundColor: '#ffffff',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      backgroundThrottling: false,
      offscreen: false,
    },
  });

  splashWindow.loadFile(splashPath);

  splashWindow.once('ready-to-show', () => {
    splashReady = true;
    splashWindow?.show();
  });
}

export function closeSplash(minDisplayMs = 0): Promise<void> {
  return new Promise((resolve) => {
    const destroy = () => {
      if (splashWindow && !splashWindow.isDestroyed()) {
        splashWindow.destroy();
      }
      splashWindow = null;
      resolve();
    };

    if (!splashWindow || splashWindow.isDestroyed()) {
      splashWindow = null;
      resolve();
      return;
    }

    const doClose = () => {
      if (minDisplayMs > 0) {
        setTimeout(destroy, minDisplayMs);
      } else {
        destroy();
      }
    };

    if (!splashReady) {
      splashWindow.once('ready-to-show', () => {
        splashReady = true;
        splashWindow?.show();
        doClose();
      });
    } else {
      doClose();
    }
  });
}
