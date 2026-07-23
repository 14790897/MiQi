import { join } from 'path';
import { inspect } from 'util';
import { electron } from '../shared/electron';
import { registerIpcHandlers } from './ipc';
import { BridgeManager } from './bridge';
import { GrokBridgeManager } from './grok/grok-bridge';
import { writeMainProcessLog } from './electron-log';
import { createSplash, closeSplash } from './splash';

const originalConsoleLog = console.log.bind(console);
const originalConsoleWarn = console.warn.bind(console);
const originalConsoleError = console.error.bind(console);

const { app, BrowserWindow, shell, Menu } = electron;

let mainWindow: typeof BrowserWindow.prototype | null = null;
let bridgeManager: BridgeManager | null = null;
let grokBridgeManager: GrokBridgeManager | null = null;

/** Resolve the app icon path for both dev (source) and packaged (resources) modes. */
function getIconPath(): string {
  if (app.isPackaged) {
    return join(process.resourcesPath, 'icon.ico');
  }
  return join(__dirname, '../../src/renderer/assets/icon.ico');
}

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 760,
    title: 'MiQi Desktop',
    icon: getIconPath(),
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: join(__dirname, '../preload/index.js'),
    },
  });

  // Remove native menu bar — app has its own navigation
  mainWindow.removeMenu();

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url);
    return { action: 'deny' };
  });

  // Diagnostics: surface preload / renderer failures to the terminal
  mainWindow.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL) => {
      // console.error is globally overridden to call writeMainProcessLog,
      // so we only call it once here to avoid double-logging.
      console.error(
        `[main] did-fail-load: code=${errorCode} desc=${errorDescription} url=${validatedURL}`
      );
    }
  );

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error(
      `[main] render-process-gone: reason=${details.reason} exitCode=${details.exitCode}`
    );
  });

  mainWindow.webContents.on('console-message', (_event: unknown, ...args: unknown[]) => {
    // Support both old API (level, message, ...) and new API (event params object)
    const first = args[0];
    let level = 0;
    let message = '';
    if (typeof first === 'object' && first !== null && 'level' in first) {
      const params = first as { level: number; message: string };
      level = params.level;
      message = params.message;
    } else {
      level = (first as number) ?? 0;
      message = (args[1] as string) ?? '';
    }
    // Map Electron console-message level to log level string
    // 0=verbose, 1=info(log), 2=warning, 3=error
    const levelStr = level >= 3 ? 'ERROR' : level >= 2 ? 'WARN' : 'INFO';
    writeMainProcessLog(levelStr, message, bridgeManager?.getProjectRoot(), 'renderer');
  });

  // 添加右键菜单，支持打开开发者工具
  mainWindow.webContents.on('context-menu', (_event, props) => {
    const { x, y } = props;
    const win = mainWindow;
    if (!win) return;
    Menu.buildFromTemplate([
      {
        label: '开发者工具',
        click: () => {
          win.webContents.openDevTools();
        },
      },
    ]).popup({ window: win, x, y });
  });

  if (process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL']);
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'));
  }
}

export function main(): void {
  const formatLogArgs = (args: unknown[]) =>
    args.map((arg) => (typeof arg === 'string' ? arg : inspect(arg, { depth: 4 }))).join(' ');

  console.log = (...args: unknown[]) => {
    writeMainProcessLog('INFO', formatLogArgs(args), bridgeManager?.getProjectRoot());
    return originalConsoleLog(...args);
  };
  console.warn = (...args: unknown[]) => {
    writeMainProcessLog('WARN', formatLogArgs(args), bridgeManager?.getProjectRoot());
    return originalConsoleWarn(...args);
  };
  console.error = (...args: unknown[]) => {
    writeMainProcessLog('ERROR', formatLogArgs(args), bridgeManager?.getProjectRoot());
    return originalConsoleError(...args);
  };

  app.whenReady().then(() => {
    bridgeManager = new BridgeManager();
    grokBridgeManager = new GrokBridgeManager();
    registerIpcHandlers(bridgeManager, grokBridgeManager);
    grokBridgeManager.start().catch((err) => {
      console.error(`[grok] bridge start failed:`, err);
      console.warn(`[grok] backend unavailable`);
    });

    // Forward bridge events to renderer
    const onState = (status: unknown) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('runtime:state', status);
      }
    };
    const onLog = (msg: string) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('runtime:log', msg);
      }
    };
    bridgeManager.on('state', onState);
    bridgeManager.on('log', onLog);
    // Forward grok bridge events too (prefixed so renderer can distinguish)
    grokBridgeManager.on('state', (status: unknown) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('runtime:grok-state', status);
      }
    });
    grokBridgeManager.on('log', (msg: string) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('runtime:grok-log', msg);
      }
    });

    createSplash(() => {
      closeSplash();
    });
    createWindow();

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow();
      }
    });
  });

  app.on('window-all-closed', () => {
    bridgeManager?.stop();
    grokBridgeManager?.stop();
    if (process.platform !== 'darwin') {
      app.quit();
    }
  });

  app.on('before-quit', () => {
    bridgeManager?.stop();
    grokBridgeManager?.stop();
  });
}
