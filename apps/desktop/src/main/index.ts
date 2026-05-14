import { join } from 'path'
import { electron } from '../shared/electron'
import { registerIpcHandlers } from './ipc'
import { BridgeManager } from './bridge'

const { app, BrowserWindow, shell } = electron

let mainWindow: typeof BrowserWindow.prototype | null = null
let bridgeManager: BridgeManager | null = null

function createWindow(): void {
  mainWindow = new BrowserWindow({
    width: 1280,
    height: 860,
    minWidth: 900,
    minHeight: 760,
    show: false,
    title: 'MiQi Desktop',
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
      preload: join(__dirname, '../preload/index.js'),
    },
  })

  // Remove native menu bar — app has its own navigation
  mainWindow.removeMenu()

  mainWindow.on('ready-to-show', () => {
    mainWindow?.show()
  })

  mainWindow.webContents.setWindowOpenHandler((details) => {
    shell.openExternal(details.url)
    return { action: 'deny' }
  })

  // Diagnostics: surface preload / renderer failures to the terminal
  mainWindow.webContents.on(
    'did-fail-load',
    (_event, errorCode, errorDescription, validatedURL) => {
      console.error(
        `[main] did-fail-load: code=${errorCode} desc=${errorDescription} url=${validatedURL}`,
      )
    },
  )

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error(
      `[main] render-process-gone: reason=${details.reason} exitCode=${details.exitCode}`,
    )
  })

  mainWindow.webContents.on('console-message', (_event: unknown, ...args: unknown[]) => {
    // Support both old API (level, message, ...) and new API (event params object)
    const first = args[0]
    let level = 0
    let message = ''
    if (typeof first === 'object' && first !== null && 'level' in first) {
      const params = first as { level: number; message: string }
      level = params.level
      message = params.message
    } else {
      level = (first as number) ?? 0
      message = (args[1] as string) ?? ''
    }
    if (level >= 3) {
      console.error(`[renderer] ${message}`)
    }
  })

  if (process.env['ELECTRON_RENDERER_URL']) {
    mainWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
  } else {
    mainWindow.loadFile(join(__dirname, '../renderer/index.html'))
  }
}

export function main(): void {
  app.whenReady().then(() => {
    bridgeManager = new BridgeManager()
    registerIpcHandlers(bridgeManager)

    // Forward bridge events to renderer
    const onState = (status: unknown) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('runtime:state', status)
      }
    }
    const onLog = (msg: string) => {
      if (mainWindow && !mainWindow.isDestroyed()) {
        mainWindow.webContents.send('runtime:log', msg)
      }
    }
    bridgeManager.on('state', onState)
    bridgeManager.on('log', onLog)

    createWindow()

    app.on('activate', () => {
      if (BrowserWindow.getAllWindows().length === 0) {
        createWindow()
      }
    })
  })

  app.on('window-all-closed', () => {
    bridgeManager?.stop()
    if (process.platform !== 'darwin') {
      app.quit()
    }
  })

  app.on('before-quit', () => {
    bridgeManager?.stop()
  })
}
