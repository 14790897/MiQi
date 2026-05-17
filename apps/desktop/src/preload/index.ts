import { contextBridge, ipcRenderer } from 'electron'
import { IPC, IPC_EVENTS } from '../shared/ipc'
import type {
  RuntimeStatus,
  SessionInfo,
  SessionDetail,
  ProviderInfo,
  ProviderUpdateResult,
  ChannelsConfig,
  ApprovalRequest,
  ApprovalCleared,
  ApprovalsListResult,
  ApprovalsAddPermanentResult,
  ApprovalsHistoryResult,
  CronJob,
  CronListResult,
  CronCreateResult,
  CronUpdateResult,
  CronRunEntry,
  CronRunsResult,
  MemoryFileInfo,
  MemoryListResult,
  MemoryGetResult,
  MemoryLessonEntry,
  MemoryLessonsResult,
  MemoryLessonUnlearnResult,
  SkillSummary,
  SkillDetail,
  SkillsListResult,
  McpServerConfig,
  McpServerInfo,
  FileNode,
  FilesTreeResult,
  FilesReadResult,
  FilesWriteResult,
  ChatProgress,
  ChatFinal,
  ChatError,
  ChatAborted,
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
    onAborted: (callback: (data: ChatAborted) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatAborted) => callback(data)
      ipcRenderer.on(IPC_EVENTS.CHAT_ABORTED, handler)
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_ABORTED, handler)
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
    test: (providerName: string, apiKey?: string, apiBase?: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.PROVIDERS_TEST, { provider_name: providerName, api_key: apiKey, api_base: apiBase ?? null }),
    update: (
      providerName: string,
      apiKey?: string,
      apiBase?: string | null,
      extraHeaders?: Record<string, string> | null,
      model?: string,
    ): Promise<ProviderUpdateResult> =>
      ipcRenderer.invoke(IPC.PROVIDERS_UPDATE, {
        provider_name: providerName,
        api_key: apiKey,
        api_base: apiBase ?? null,
        extra_headers: extraHeaders ?? null,
        model: model ?? undefined,
      }),
  },

  // -- Channels ---------------------------------------------------------------
  channels: {
    list: (): Promise<{ channels: ChannelsConfig }> =>
      ipcRenderer.invoke(IPC.CHANNELS_LIST),
    update: (channels: Partial<Record<string, unknown>>): Promise<{ saved: boolean }> =>
      ipcRenderer.invoke(IPC.CHANNELS_UPDATE, { channels }),
  },

  // -- Approvals --------------------------------------------------------------
  approvals: {
    list: (): Promise<ApprovalsListResult> =>
      ipcRenderer.invoke(IPC.APPROVALS_LIST),
    resolve: (approvalId: string, decision: string): Promise<{ resolved: boolean }> =>
      ipcRenderer.invoke(IPC.APPROVALS_RESOLVE, { approval_id: approvalId, decision }),
    clearPermanent: (pattern?: string): Promise<{ cleared: boolean }> =>
      ipcRenderer.invoke(IPC.APPROVALS_CLEAR_PERMANENT, pattern ? { pattern } : {}),
    addPermanent: (pattern: string): Promise<ApprovalsAddPermanentResult> =>
      ipcRenderer.invoke(IPC.APPROVALS_ADD_PERMANENT, { pattern }),
    history: (limit?: number): Promise<ApprovalsHistoryResult> =>
      ipcRenderer.invoke(IPC.APPROVALS_HISTORY, limit ? { limit } : {}),
    onRequest: (callback: (data: ApprovalRequest) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ApprovalRequest) => callback(data)
      ipcRenderer.on(IPC_EVENTS.APPROVAL_REQUEST, handler)
      return () => { ipcRenderer.removeListener(IPC_EVENTS.APPROVAL_REQUEST, handler) }
    },
    onCleared: (callback: (data: ApprovalCleared) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ApprovalCleared) => callback(data)
      ipcRenderer.on(IPC_EVENTS.APPROVAL_CLEARED, handler)
      return () => { ipcRenderer.removeListener(IPC_EVENTS.APPROVAL_CLEARED, handler) }
    },
  },

  // -- Cron --------------------------------------------------------------------
  cron: {
    list: (): Promise<CronListResult> =>
      ipcRenderer.invoke(IPC.CRON_LIST),
    create: (payload: Record<string, unknown>): Promise<CronCreateResult> =>
      ipcRenderer.invoke(IPC.CRON_CREATE, payload),
    update: (payload: Record<string, unknown>): Promise<CronUpdateResult> =>
      ipcRenderer.invoke(IPC.CRON_UPDATE, payload),
    delete: (jobId: string): Promise<{ deleted: boolean }> =>
      ipcRenderer.invoke(IPC.CRON_DELETE, { jobId }),
    toggle: (jobId: string, enabled: boolean): Promise<CronUpdateResult> =>
      ipcRenderer.invoke(IPC.CRON_TOGGLE, { jobId, enabled }),
    run: (jobId: string): Promise<CronUpdateResult> =>
      ipcRenderer.invoke(IPC.CRON_RUN, { jobId }),
    runs: (jobId?: string): Promise<CronRunsResult> =>
      ipcRenderer.invoke(IPC.CRON_RUNS, jobId ? { jobId } : {}),
  },

  // -- Memory ------------------------------------------------------------------
  memory: {
    list: (): Promise<MemoryListResult> =>
      ipcRenderer.invoke(IPC.MEMORY_LIST),
    get: (path: string): Promise<MemoryGetResult> =>
      ipcRenderer.invoke(IPC.MEMORY_GET, { path }),
    update: (path: string, content: string): Promise<{ saved: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.MEMORY_UPDATE, { path, content }),
    delete: (path: string): Promise<{ deleted: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.MEMORY_DELETE, { path }),
    lessons: (): Promise<MemoryLessonsResult> =>
      ipcRenderer.invoke(IPC.MEMORY_LESSONS),
    lessonUnlearn: (lesson_id: string): Promise<MemoryLessonUnlearnResult> =>
      ipcRenderer.invoke(IPC.MEMORY_LESSON_UNLEARN, { lesson_id }),
  },

  // -- Skills ------------------------------------------------------------------
  skills: {
    list: (): Promise<SkillsListResult> =>
      ipcRenderer.invoke(IPC.SKILLS_LIST),
    get: (name: string): Promise<SkillDetail> =>
      ipcRenderer.invoke(IPC.SKILLS_GET, { name }),
    openFolder: (name: string): Promise<{ opened: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_OPEN_FOLDER, { name }),
  },

  // -- MCP --------------------------------------------------------------------
  mcps: {
    list: (): Promise<{ servers: McpServerInfo[] }> =>
      ipcRenderer.invoke(IPC.MCP_LIST),
    upsert: (name: string, config: McpServerConfig): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.MCP_UPSERT, { name, ...config }),
    delete: (name: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.MCP_DELETE, { name }),
  },

  // -- Files (Workspace Editor) ------------------------------------------------
  files: {
    tree: (): Promise<FilesTreeResult> =>
      ipcRenderer.invoke(IPC.FILES_TREE),
    read: (path: string): Promise<FilesReadResult> =>
      ipcRenderer.invoke(IPC.FILES_READ, { path }),
    write: (path: string, content: string): Promise<FilesWriteResult> =>
      ipcRenderer.invoke(IPC.FILES_WRITE, { path, content }),
    delete: (path: string): Promise<{ deleted: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.FILES_DELETE, { path }),
  },

  // -- Python check -----------------------------------------------------------
  python: {
    check: (): Promise<PythonCheckResult> =>
      ipcRenderer.invoke(IPC.PYTHON_CHECK),
  },

  // -- Initial config write (no bridge needed) --------------------------------
  setup: {
    writeInitialConfig: (config: Record<string, unknown>): Promise<{ saved: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.CONFIG_WRITE_INITIAL, config),
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
