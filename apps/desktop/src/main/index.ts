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
  mainWindow.webContents.on('did-fail-load', (_event, errorCode, errorDescription, validatedURL) => {
    console.error(`[main] did-fail-load: code=${errorCode} desc=${errorDescription} url=${validatedURL}`)
  })

  mainWindow.webContents.on('render-process-gone', (_event, details) => {
    console.error(`[main] render-process-gone: reason=${details.reason} exitCode=${details.exitCode}`)
  })

  mainWindow.webContents.on('console-message', (_event, level, message) => {
    // Level 3 = error; surface to terminal for post-mortem diagnosis
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
    bridgeManager.on('state', (status) => {
      mainWindow?.webContents.send('runtime:state', status)
    })
    bridgeManager.on('log', (msg: string) => {
      mainWindow?.webContents.send('runtime:log', msg)
    })

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
