import { electron } from '../../shared/electron'
import type { BridgeManager } from '../bridge'
import { IPC, ChatSendInput, SessionGetInput, SessionDeleteInput, ConfigUpdateInput, ProviderTestInput, ProviderUpdateInput, ChannelsUpdateInput } from '../../shared/ipc'

const { ipcMain, dialog } = electron

export function registerIpcHandlers(bridge: BridgeManager): void {
  // -----------------------------------------------------------------------
  // Runtime
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.RUNTIME_START, async () => {
    await bridge.start()
    return bridge.getStatus()
  })

  ipcMain.handle(IPC.RUNTIME_STOP, async () => {
    await bridge.stop()
    return bridge.getStatus()
  })

  ipcMain.handle(IPC.RUNTIME_STATUS, () => {
    return bridge.getStatus()
  })

  ipcMain.handle(IPC.RUNTIME_LOGS, () => {
    return bridge.getLogs()
  })

  // -----------------------------------------------------------------------
  // Chat
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CHAT_SEND, async (_event, payload: unknown) => {
    const input = ChatSendInput.parse(payload)

    const mainWindow = _event.sender
    const result = await bridge.send('chat.send', {
      content: input.content,
      session_key: input.session_key ?? 'desktop:default',
    }, (type: string, data: unknown) => {
      if (type === 'progress') {
        mainWindow.send('chat:progress', data)
      } else if (type === 'final') {
        mainWindow.send('chat:final', data)
      } else if (type === 'error') {
        mainWindow.send('chat:error', data)
      } else if (type === 'aborted') {
        mainWindow.send('chat:aborted', data)
      } else if (type === 'approval_request') {
        mainWindow.send('approval:request', data)
      }
    })

    return result
  })

  ipcMain.handle(IPC.CHAT_ABORT, async () => {
    return bridge.send('chat.abort')
  })

  // -----------------------------------------------------------------------
  // Sessions
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.SESSIONS_LIST, async () => {
    return bridge.send('sessions.list')
  })

  ipcMain.handle(IPC.SESSIONS_GET, async (_event, payload: unknown) => {
    const input = SessionGetInput.parse(payload)
    return bridge.send('sessions.get', { session_key: input.session_key })
  })

  ipcMain.handle(IPC.SESSIONS_DELETE, async (_event, payload: unknown) => {
    const input = SessionDeleteInput.parse(payload)
    return bridge.send('sessions.delete', { session_key: input.session_key })
  })

  // -----------------------------------------------------------------------
  // Config
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CONFIG_GET, async () => {
    return bridge.send('config.get')
  })

  ipcMain.handle(IPC.CONFIG_UPDATE, async (_event, payload: unknown) => {
    const input = ConfigUpdateInput.parse(payload)
    return bridge.send('config.update', { config: input.config })
  })

  // -----------------------------------------------------------------------
  // Providers
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.PROVIDERS_LIST, async () => {
    return bridge.send('providers.list')
  })

  ipcMain.handle(IPC.PROVIDERS_TEST, async (_event, payload: unknown) => {
    const input = ProviderTestInput.parse(payload)
    return bridge.send('providers.test', input as Record<string, unknown>)
  })

  ipcMain.handle(IPC.PROVIDERS_UPDATE, async (_event, payload: unknown) => {
    const input = ProviderUpdateInput.parse(payload)
    return bridge.send('providers.update', input as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Channels
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.CHANNELS_LIST, async () => {
    return bridge.send('channels.list')
  })

  ipcMain.handle(IPC.CHANNELS_UPDATE, async (_event, payload: unknown) => {
    const input = ChannelsUpdateInput.parse(payload)
    return bridge.send('channels.update', input as Record<string, unknown>)
  })

  // -----------------------------------------------------------------------
  // Python check (no bridge needed — just spawn a quick python process)
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.PYTHON_CHECK, async () => {
    return bridge.send('python.check')
  })

  // -----------------------------------------------------------------------
  // Dialog (file open for workspace)
  // -----------------------------------------------------------------------
  ipcMain.handle(IPC.DIALOG_OPEN_FILE, async () => {
    const result = await dialog.showOpenDialog({
      properties: ['openFile', 'openDirectory'],
    })
    return result.canceled ? null : result.filePaths[0] ?? null
  })

  // -----------------------------------------------------------------------
  // Approvals
  // -----------------------------------------------------------------------
  ipcMain.handle('approvals:list', async () => {
    return bridge.send('approvals.list')
  })

  ipcMain.handle('approvals:resolve', async (_event, payload: unknown) => {
    const p = payload as { approval_id: string; decision: string }
    return bridge.send('approvals.resolve', p as Record<string, unknown>)
  })

  ipcMain.handle('approvals:clear_permanent', async (_event, payload: unknown) => {
    const p = (payload ?? {}) as { pattern?: string }
    return bridge.send('approvals.clear_permanent', p as Record<string, unknown>)
  })
}
