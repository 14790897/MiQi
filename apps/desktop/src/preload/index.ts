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
  ExperienceEntry,
  SkillSummary,
  WslExportDistroResult,
  WslImportDistroResult,
  WslStatsResult,
  SkillsListResult,
  SkillDetail,
  McpServerConfig,
  McpServerInfo,
  FileNode,
  FilesTreeResult,
  FilesReadResult,
  FilesWriteResult,
  FilesDiffResult,
  FilesRevertResult,
  TrackedFileInfo,
  ChatProgress,
  ChatFinal,
  ChatError,
  ChatAborted,
  PythonCheckResult,
  WslCheckResult,
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
    /** Send a message.  Returns ``{ accepted: true, req_id: string }``. */
    send: (content: string, sessionKey?: string, reqId?: string): Promise<{ accepted: boolean; req_id: string }> =>
      ipcRenderer.invoke(IPC.CHAT_SEND, { content, session_key: sessionKey, req_id: reqId }),
    /** Abort a specific in-flight request by req_id. */
    abort: (targetReqId?: string): Promise<{ aborted: boolean }> =>
      ipcRenderer.invoke(IPC.CHAT_ABORT, { target_req_id: targetReqId }),
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
    archive: (sessionKey: string): Promise<{ archived: boolean }> =>
      ipcRenderer.invoke(IPC.SESSIONS_ARCHIVE, { session_key: sessionKey }),
    unarchive: (sessionKey: string): Promise<{ unarchived: boolean }> =>
      ipcRenderer.invoke(IPC.SESSIONS_UNARCHIVE, { session_key: sessionKey }),
    listArchived: (): Promise<{ sessions: SessionInfo[] }> =>
      ipcRenderer.invoke(IPC.SESSIONS_LIST_ARCHIVED),
    getTrackedFiles: (sessionKey: string): Promise<{ tracked_files: TrackedFileInfo[] }> =>
      ipcRenderer.invoke(IPC.SESSIONS_GET_TRACKED_FILES, { session_key: sessionKey }),
    clearTrackedFiles: (sessionKey: string): Promise<{ cleared: boolean }> =>
      ipcRenderer.invoke(IPC.SESSIONS_CLEAR_TRACKED_FILES, { session_key: sessionKey }),
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

  // -- Experience ---------------------------------------------------------------
  experience: {
    list: (params?: { type?: string; scope?: string; session_key?: string; limit?: number }): Promise<{ entries: ExperienceEntry[] }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_LIST, params ?? {}),
    delete: (type: string, id: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_DELETE, { type, id }),
    toggle: (type: string, id: string, enabled: boolean): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_TOGGLE, { type, id, enabled }),
    search: (query: string, type?: string, limit?: number): Promise<{ entries: ExperienceEntry[] }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_SEARCH, { query, type, limit }),
  },

  // -- Skills ------------------------------------------------------------------
  skills: {
    list: (): Promise<SkillsListResult> =>
      ipcRenderer.invoke(IPC.SKILLS_LIST),
    get: (name: string): Promise<SkillDetail> =>
      ipcRenderer.invoke(IPC.SKILLS_GET, { name }),
    openFolder: (name: string): Promise<{ opened: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_OPEN_FOLDER, { name }),
    create: (name: string, description: string): Promise<{ ok: boolean; error?: string; path?: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_CREATE, { name, description }),
    upload: (name: string, content: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_UPLOAD, { name, content }),
    delete: (name: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_DELETE, { name }),
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
    write: (path: string, content: string, sessionKey?: string): Promise<FilesWriteResult> =>
      ipcRenderer.invoke(IPC.FILES_WRITE, { path, content, session_key: sessionKey }),
    delete: (path: string): Promise<{ deleted: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.FILES_DELETE, { path }),
    diff: (path: string, sessionKey?: string): Promise<FilesDiffResult> =>
      ipcRenderer.invoke(IPC.FILES_DIFF, { path, session_key: sessionKey }),
    revert: (path: string, sessionKey?: string): Promise<FilesRevertResult> =>
      ipcRenderer.invoke(IPC.FILES_REVERT, { path, session_key: sessionKey }),
    accept: (path: string, sessionKey?: string): Promise<{ accepted: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.FILES_ACCEPT, { path, session_key: sessionKey }),
  },

  // -- Python check -----------------------------------------------------------
  python: {
    check: (): Promise<PythonCheckResult> =>
      ipcRenderer.invoke(IPC.PYTHON_CHECK),
  },

  // -- WSL2 check & install (Windows only) ------------------------------------
  wsl: {
    check: (): Promise<WslCheckResult> =>
      ipcRenderer.invoke(IPC.WSL_CHECK),
    install: (): Promise<{ launched: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.WSL_INSTALL),
    exportDistro: (distroName: string): Promise<WslExportDistroResult> =>
      ipcRenderer.invoke(IPC.WSL_EXPORT_DISTRO, distroName),
    importDistro: (options: { tarPath: string; distroName: string }): Promise<WslImportDistroResult> =>
      ipcRenderer.invoke(IPC.WSL_IMPORT_DISTRO, options),
    getStats: (distroName?: string): Promise<WslStatsResult> =>
      ipcRenderer.invoke(IPC.WSL_GET_STATS, distroName ?? undefined),
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
