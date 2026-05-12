import { contextBridge, ipcRenderer } from 'electron'
import { IPC, IPC_EVENTS } from '../shared/ipc'
import type {
  RuntimeStatus,
  SessionInfo,
  SessionDetail,
  ProviderInfo,
  ChatProgress,
  ChatFinal,
  ChatError,
  PythonCheckResult,
} from '../shared/ipc'

// ---------------------------------------------------------------------------
// Typed API exposed to the renderer via contextBridge
// ---------------------------------------------------------------------------

const api = {
  // -- Runtime ----------------------------------------------------------------
  runtime: {
    start: (): Promise<RuntimeStatus> =>
      ipcRenderer.invoke(IPC.RUNTIME_START),
    stop: (): Promise<RuntimeStatus> =>
      ipcRenderer.invoke(IPC.RUNTIME_STOP),
    status: (): Promise<RuntimeStatus> =>
      ipcRenderer.invoke(IPC.RUNTIME_STATUS),
    logs: (): Promise<string[]> =>
      ipcRenderer.invoke(IPC.RUNTIME_LOGS),
    onStateChange: (callback: (status: RuntimeStatus) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, status: RuntimeStatus) => callback(status)
      ipcRenderer.on(IPC_EVENTS.RUNTIME_STATE, handler)
      return () => ipcRenderer.removeListener(IPC_EVENTS.RUNTIME_STATE, handler)
    },
    onLog: (callback: (message: string) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, message: string) => callback(message)
      ipcRenderer.on(IPC_EVENTS.RUNTIME_LOG, handler)
      return () => ipcRenderer.removeListener(IPC_EVENTS.RUNTIME_LOG, handler)
    },
  },

  // -- Chat -------------------------------------------------------------------
  chat: {
    send: (content: string, sessionKey?: string): Promise<unknown> =>
      ipcRenderer.invoke(IPC.CHAT_SEND, { content, session_key: sessionKey }),
    abort: (): Promise<unknown> =>
      ipcRenderer.invoke(IPC.CHAT_ABORT),
    onProgress: (callback: (data: ChatProgress) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatProgress) => callback(data)
      ipcRenderer.on(IPC_EVENTS.CHAT_PROGRESS, handler)
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_PROGRESS, handler)
    },
    onFinal: (callback: (data: ChatFinal) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatFinal) => callback(data)
      ipcRenderer.on(IPC_EVENTS.CHAT_FINAL, handler)
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_FINAL, handler)
    },
    onError: (callback: (data: ChatError) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatError) => callback(data)
      ipcRenderer.on(IPC_EVENTS.CHAT_ERROR, handler)
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_ERROR, handler)
    },
  },

  // -- Sessions ---------------------------------------------------------------
  sessions: {
    list: (): Promise<{ sessions: SessionInfo[] }> =>
      ipcRenderer.invoke(IPC.SESSIONS_LIST),
    get: (sessionKey: string): Promise<SessionDetail> =>
      ipcRenderer.invoke(IPC.SESSIONS_GET, { session_key: sessionKey }),
    delete: (sessionKey: string): Promise<{ deleted: boolean }> =>
      ipcRenderer.invoke(IPC.SESSIONS_DELETE, { session_key: sessionKey }),
  },

  // -- Config -----------------------------------------------------------------
  config: {
    get: (): Promise<Record<string, unknown>> =>
      ipcRenderer.invoke(IPC.CONFIG_GET),
    update: (config: Record<string, unknown>): Promise<unknown> =>
      ipcRenderer.invoke(IPC.CONFIG_UPDATE, { config }),
  },

  // -- Providers --------------------------------------------------------------
  providers: {
    list: (): Promise<{ providers: ProviderInfo[] }> =>
      ipcRenderer.invoke(IPC.PROVIDERS_LIST),
    test: (providerName: string, apiKey: string, apiBase?: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.PROVIDERS_TEST, { provider_name: providerName, api_key: apiKey, api_base: apiBase ?? null }),
  },

  // -- Python check -----------------------------------------------------------
  python: {
    check: (): Promise<PythonCheckResult> =>
      ipcRenderer.invoke(IPC.PYTHON_CHECK),
  },

  // -- Dialog -----------------------------------------------------------------
  dialog: {
    openFile: (): Promise<string | null> =>
      ipcRenderer.invoke(IPC.DIALOG_OPEN_FILE),
  },
}

contextBridge.exposeInMainWorld('miqi', api)

// Type declaration for renderer
export type MiQiAPI = typeof api
