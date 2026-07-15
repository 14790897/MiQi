import { contextBridge, ipcRenderer } from 'electron';
import { IPC, IPC_EVENTS } from '../shared/ipc';
import type {
  RuntimeStatus,
  SessionInfo,
  SessionDetail,
  SessionClaimLegacyResult,
  ProvidersListResult,
  ProviderUpdateResult,
  ChannelsConfig,
  PendingApproval,
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
  FilesOpenExternalResult,
  FilesOpenContainingFolderResult,
  TrackedFileInfo,
  ChatProgress,
  ChatFinal,
  ChatError,
  ChatAborted,
  ChatSubagentResult,
  PythonCheckResult,
  WslCheckResult,
  LiveAgentInfo,
  AgentSpawnedEvent,
  AgentCompletedEvent,
  Plan,
  PlanUpdatedEvent,
  ThreadStartResult,
  ThreadListResult,
  ThreadReadResult,
  ThreadStartedEvent,
  TurnStartResult,
  TurnInterruptResult,
  SandboxSetEnabledResult,
  FeedbackEntry,
  FeedbackListResult,
  FeedbackSubmitResult,
} from '../shared/ipc';

// ---------------------------------------------------------------------------
// Typed API exposed to the renderer via contextBridge
// ---------------------------------------------------------------------------

const api = {
  // -- Runtime ----------------------------------------------------------------
  runtime: {
    start: (): Promise<RuntimeStatus> => ipcRenderer.invoke(IPC.RUNTIME_START),
    stop: (): Promise<RuntimeStatus> => ipcRenderer.invoke(IPC.RUNTIME_STOP),
    status: (): Promise<RuntimeStatus> => ipcRenderer.invoke(IPC.RUNTIME_STATUS),
    logs: (): Promise<string[]> => ipcRenderer.invoke(IPC.RUNTIME_LOGS),
    fileLogs: (): Promise<string[]> => ipcRenderer.invoke(IPC.RUNTIME_FILE_LOGS),
    backendLogs: (): Promise<string[]> => ipcRenderer.invoke(IPC.RUNTIME_BACKEND_LOGS),
    onStateChange: (callback: (status: RuntimeStatus) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, status: RuntimeStatus) =>
        callback(status);
      ipcRenderer.on(IPC_EVENTS.RUNTIME_STATE, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.RUNTIME_STATE, handler);
    },
    onLog: (callback: (message: string) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, message: string) => callback(message);
      ipcRenderer.on(IPC_EVENTS.RUNTIME_LOG, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.RUNTIME_LOG, handler);
    },
    reportRendererLog: (entry: {
      level: string;
      message: string;
      source?: string;
      sessionKey?: string;
    }) => {
      ipcRenderer.send('runtime:renderer-log', entry);
    },
  },

  // -- Chat -------------------------------------------------------------------
  chat: {
    send: (content: string, sessionKey?: string, threadId?: string): Promise<unknown> =>
      ipcRenderer.invoke(IPC.CHAT_SEND, { content, session_key: sessionKey, thread_id: threadId }),
    abort: (sessionKey?: string): Promise<unknown> =>
      ipcRenderer.invoke(IPC.CHAT_ABORT, { session_key: sessionKey }),
    onProgress: (callback: (data: ChatProgress) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatProgress) => callback(data);
      ipcRenderer.on(IPC_EVENTS.CHAT_PROGRESS, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_PROGRESS, handler);
    },
    onFinal: (callback: (data: ChatFinal) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatFinal) => callback(data);
      ipcRenderer.on(IPC_EVENTS.CHAT_FINAL, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_FINAL, handler);
    },
    onError: (callback: (data: ChatError) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatError) => callback(data);
      ipcRenderer.on(IPC_EVENTS.CHAT_ERROR, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_ERROR, handler);
    },
    onAborted: (callback: (data: ChatAborted) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatAborted) => callback(data);
      ipcRenderer.on(IPC_EVENTS.CHAT_ABORTED, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_ABORTED, handler);
    },
    onSubagentResult: (callback: (data: ChatSubagentResult) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ChatSubagentResult) =>
        callback(data);
      ipcRenderer.on(IPC_EVENTS.CHAT_SUBAGENT_RESULT, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.CHAT_SUBAGENT_RESULT, handler);
    },
  },

  // -- Sessions ---------------------------------------------------------------
  sessions: {
    list: (): Promise<{ sessions: SessionInfo[] }> => ipcRenderer.invoke(IPC.SESSIONS_LIST),
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
    claimLegacy: (sessionKey: string): Promise<SessionClaimLegacyResult> =>
      ipcRenderer.invoke(IPC.SESSIONS_CLAIM_LEGACY, { session_key: sessionKey }),
  },

  // -- Config -----------------------------------------------------------------
  config: {
    get: (): Promise<Record<string, unknown>> => ipcRenderer.invoke(IPC.CONFIG_GET),
    update: (config: Record<string, unknown>): Promise<unknown> =>
      ipcRenderer.invoke(IPC.CONFIG_UPDATE, { config }),
  },

  // -- Providers --------------------------------------------------------------
  providers: {
    list: (): Promise<ProvidersListResult> => ipcRenderer.invoke(IPC.PROVIDERS_LIST),
    test: (
      providerName: string,
      apiKey?: string,
      apiBase?: string,
      model?: string
    ): Promise<{ ok: boolean; model?: string }> =>
      ipcRenderer.invoke(IPC.PROVIDERS_TEST, {
        provider_name: providerName,
        api_key: apiKey,
        api_base: apiBase ?? null,
        model,
      }),
    update: (
      providerName: string,
      apiKey?: string,
      apiBase?: string | null,
      extraHeaders?: Record<string, string> | null,
      model?: string
    ): Promise<ProviderUpdateResult> =>
      ipcRenderer.invoke(IPC.PROVIDERS_UPDATE, {
        provider_name: providerName,
        api_key: apiKey,
        api_base: apiBase ?? null,
        extra_headers: extraHeaders ?? null,
        model: model ?? undefined,
      }),
    activate: (
      providerName: string,
      activationCode: string
    ): Promise<{ activated: boolean; provider_name: string; error?: string }> =>
      ipcRenderer.invoke(IPC.PROVIDERS_ACTIVATE, {
        provider_name: providerName,
        activation_code: activationCode,
      }),
  },

  // -- Channels ---------------------------------------------------------------
  channels: {
    list: (): Promise<{ channels: ChannelsConfig }> => ipcRenderer.invoke(IPC.CHANNELS_LIST),
    update: (channels: Partial<Record<string, unknown>>): Promise<{ saved: boolean }> =>
      ipcRenderer.invoke(IPC.CHANNELS_UPDATE, { channels }),
  },

  // -- Approvals --------------------------------------------------------------
  approvals: {
    list: (): Promise<ApprovalsListResult> => ipcRenderer.invoke(IPC.APPROVALS_LIST),
    resolve: (approvalId: string, decision: string): Promise<{ resolved: boolean }> =>
      ipcRenderer.invoke(IPC.APPROVALS_RESOLVE, { approval_id: approvalId, decision }),
    clearPermanent: (pattern?: string): Promise<{ cleared: boolean }> =>
      ipcRenderer.invoke(IPC.APPROVALS_CLEAR_PERMANENT, pattern ? { pattern } : {}),
    addPermanent: (pattern: string): Promise<ApprovalsAddPermanentResult> =>
      ipcRenderer.invoke(IPC.APPROVALS_ADD_PERMANENT, { pattern }),
    history: (limit?: number): Promise<ApprovalsHistoryResult> =>
      ipcRenderer.invoke(IPC.APPROVALS_HISTORY, limit ? { limit } : {}),
    onRequest: (callback: (data: PendingApproval) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: PendingApproval) => callback(data);
      ipcRenderer.on(IPC_EVENTS.APPROVAL_REQUEST, handler);
      return () => {
        ipcRenderer.removeListener(IPC_EVENTS.APPROVAL_REQUEST, handler);
      };
    },
    onCleared: (callback: (data: ApprovalCleared) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ApprovalCleared) => callback(data);
      ipcRenderer.on(IPC_EVENTS.APPROVAL_CLEARED, handler);
      return () => {
        ipcRenderer.removeListener(IPC_EVENTS.APPROVAL_CLEARED, handler);
      };
    },
  },

  // -- Cron --------------------------------------------------------------------
  cron: {
    list: (): Promise<CronListResult> => ipcRenderer.invoke(IPC.CRON_LIST),
    create: (payload: Record<string, unknown>): Promise<CronCreateResult> =>
      ipcRenderer.invoke(IPC.CRON_CREATE, payload),
    update: (payload: Record<string, unknown>): Promise<CronUpdateResult> =>
      ipcRenderer.invoke(IPC.CRON_UPDATE, payload),
    delete: (jobId: string): Promise<{ deleted: boolean }> =>
      ipcRenderer.invoke(IPC.CRON_DELETE, { jobId }),
    toggle: (jobId: string, enabled: boolean): Promise<CronUpdateResult> =>
      ipcRenderer.invoke(IPC.CRON_TOGGLE, { jobId, enabled }),
    run: (jobId: string): Promise<CronUpdateResult> => ipcRenderer.invoke(IPC.CRON_RUN, { jobId }),
    runs: (jobId?: string): Promise<CronRunsResult> =>
      ipcRenderer.invoke(IPC.CRON_RUNS, jobId ? { jobId } : {}),
  },

  // -- Memory ------------------------------------------------------------------
  memory: {
    list: (): Promise<MemoryListResult> => ipcRenderer.invoke(IPC.MEMORY_LIST),
    get: (path: string): Promise<MemoryGetResult> => ipcRenderer.invoke(IPC.MEMORY_GET, { path }),
    update: (path: string, content: string): Promise<{ saved: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.MEMORY_UPDATE, { path, content }),
    delete: (path: string): Promise<{ deleted: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.MEMORY_DELETE, { path }),
    lessons: (): Promise<MemoryLessonsResult> => ipcRenderer.invoke(IPC.MEMORY_LESSONS),
    lessonUnlearn: (lesson_id: string): Promise<MemoryLessonUnlearnResult> =>
      ipcRenderer.invoke(IPC.MEMORY_LESSON_UNLEARN, { lesson_id }),
  },

  // -- Experience ---------------------------------------------------------------
  experience: {
    list: (params?: {
      type?: string;
      scope?: string;
      session_key?: string;
      limit?: number;
    }): Promise<{ entries: ExperienceEntry[] }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_LIST, params ?? {}),
    delete: (type: string, id: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_DELETE, { type, id }),
    toggle: (type: string, id: string, enabled: boolean): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_TOGGLE, { type, id, enabled }),
    search: (
      query: string,
      type?: string,
      limit?: number
    ): Promise<{ entries: ExperienceEntry[] }> =>
      ipcRenderer.invoke(IPC.EXPERIENCE_SEARCH, { query, type, limit }),
  },

  // -- Skills ------------------------------------------------------------------
  skills: {
    list: (): Promise<SkillsListResult> => ipcRenderer.invoke(IPC.SKILLS_LIST),
    get: (name: string): Promise<SkillDetail> => ipcRenderer.invoke(IPC.SKILLS_GET, { name }),
    openFolder: (name: string): Promise<{ opened: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_OPEN_FOLDER, { name }),
    create: (
      name: string,
      description: string
    ): Promise<{ ok: boolean; error?: string; path?: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_CREATE, { name, description }),
    upload: (name: string, content: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_UPLOAD, { name, content }),
    delete: (name: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.SKILLS_DELETE, { name }),
  },

  // -- MCP --------------------------------------------------------------------
  mcps: {
    list: (): Promise<{ servers: McpServerInfo[] }> => ipcRenderer.invoke(IPC.MCP_LIST),
    upsert: (name: string, config: McpServerConfig): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.MCP_UPSERT, { name, ...config }),
    delete: (name: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.MCP_DELETE, { name }),
  },

  // -- Files (Workspace Editor) ------------------------------------------------
  files: {
    tree: (): Promise<FilesTreeResult> => ipcRenderer.invoke(IPC.FILES_TREE),
    read: (path: string): Promise<FilesReadResult> => ipcRenderer.invoke(IPC.FILES_READ, { path }),
    write: (
      path: string,
      content: string,
      sessionKey?: string,
      dataBase64?: string
    ): Promise<FilesWriteResult> =>
      ipcRenderer.invoke(IPC.FILES_WRITE, {
        path,
        content,
        session_key: sessionKey,
        data_base64: dataBase64,
      }),
    delete: (path: string): Promise<{ deleted: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.FILES_DELETE, { path }),
    diff: (path: string, sessionKey?: string): Promise<FilesDiffResult> =>
      ipcRenderer.invoke(IPC.FILES_DIFF, { path, session_key: sessionKey }),
    revert: (path: string, sessionKey?: string): Promise<FilesRevertResult> =>
      ipcRenderer.invoke(IPC.FILES_REVERT, { path, session_key: sessionKey }),
    accept: (path: string, sessionKey?: string): Promise<{ accepted: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.FILES_ACCEPT, { path, session_key: sessionKey }),
    openExternal: (path: string): Promise<FilesOpenExternalResult> =>
      ipcRenderer.invoke(IPC.FILES_OPEN_EXTERNAL, { path }),
    openContainingFolder: (path: string): Promise<FilesOpenContainingFolderResult> =>
      ipcRenderer.invoke(IPC.FILES_OPEN_CONTAINING_FOLDER, { path }),
  },

  // -- Python check -----------------------------------------------------------
  python: {
    check: (): Promise<PythonCheckResult> => ipcRenderer.invoke(IPC.PYTHON_CHECK),
  },

  // -- WSL2 check & install (Windows only) ------------------------------------
  wsl: {
    check: (): Promise<WslCheckResult> => ipcRenderer.invoke(IPC.WSL_CHECK),
    install: (): Promise<{ launched: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.WSL_INSTALL),
    exportDistro: (distroName: string): Promise<WslExportDistroResult> =>
      ipcRenderer.invoke(IPC.WSL_EXPORT_DISTRO, distroName),
    importDistro: (options: {
      tarPath: string;
      distroName: string;
    }): Promise<WslImportDistroResult> => ipcRenderer.invoke(IPC.WSL_IMPORT_DISTRO, options),
    getStats: (distroName?: string): Promise<WslStatsResult> =>
      ipcRenderer.invoke(IPC.WSL_GET_STATS, distroName ?? undefined),
  },

  // -- Sandbox runtime toggle -----------------------------------------------
  sandbox: {
    setEnabled: (enabled: boolean): Promise<SandboxSetEnabledResult> =>
      ipcRenderer.invoke(IPC.SANDBOX_SET_ENABLED, enabled),
  },

  // -- Initial config write (no bridge needed) --------------------------------
  setup: {
    writeInitialConfig: (
      config: Record<string, unknown>
    ): Promise<{ saved: boolean; path: string }> =>
      ipcRenderer.invoke(IPC.CONFIG_WRITE_INITIAL, config),
  },

  // -- Dialog -----------------------------------------------------------------
  dialog: {
    openFile: (): Promise<string | null> => ipcRenderer.invoke(IPC.DIALOG_OPEN_FILE),
  },

  // -- Agents (Phase 1) --------------------------------------------------------
  agents: {
    list: (sessionKey?: string): Promise<{ agents: LiveAgentInfo[] }> =>
      ipcRenderer.invoke(IPC.AGENT_LIST, { session_key: sessionKey }),
    spawn: (agentType: string, task: string, label?: string): Promise<{ agent: LiveAgentInfo }> =>
      ipcRenderer.invoke(IPC.AGENT_SPAWN, { agent_type: agentType, task, label }),
    kill: (agentId: string): Promise<{ killed: boolean }> =>
      ipcRenderer.invoke(IPC.AGENT_KILL, { agent_id: agentId }),
    onSpawned: (callback: (data: AgentSpawnedEvent) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: AgentSpawnedEvent) =>
        callback(data);
      ipcRenderer.on(IPC_EVENTS.AGENT_SPAWNED, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.AGENT_SPAWNED, handler);
    },
    onCompleted: (callback: (data: AgentCompletedEvent) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: AgentCompletedEvent) =>
        callback(data);
      ipcRenderer.on(IPC_EVENTS.AGENT_COMPLETED, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.AGENT_COMPLETED, handler);
    },
  },

  // -- Plan (Phase 2) ----------------------------------------------------------
  plan: {
    get: (threadId: string): Promise<{ plan: Plan | null }> =>
      ipcRenderer.invoke(IPC.PLAN_GET, { thread_id: threadId }),
    onUpdated: (callback: (data: PlanUpdatedEvent) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: PlanUpdatedEvent) => callback(data);
      ipcRenderer.on(IPC_EVENTS.PLAN_UPDATED, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.PLAN_UPDATED, handler);
    },
  },

  // -- Permissions (Phase 1) ---------------------------------------------------
  permissions: {
    get: (): Promise<Record<string, unknown>> => ipcRenderer.invoke(IPC.PERMISSIONS_GET),
    update: (config: Record<string, unknown>): Promise<{ saved: boolean }> =>
      ipcRenderer.invoke(IPC.PERMISSIONS_UPDATE, { config }),
    addPermanent: (pattern: string): Promise<{ added: boolean }> =>
      ipcRenderer.invoke(IPC.PERMISSIONS_PERMANENT_ADD, { pattern }),
    removePermanent: (pattern: string): Promise<{ removed: boolean }> =>
      ipcRenderer.invoke(IPC.PERMISSIONS_PERMANENT_REMOVE, { pattern }),
  },

  // -- Plugins (Phase 4) -------------------------------------------------------
  plugins: {
    list: (): Promise<{ plugins: Record<string, unknown>[] }> =>
      ipcRenderer.invoke(IPC.PLUGINS_LIST),
    install: (name: string): Promise<{ ok: boolean; error?: string }> =>
      ipcRenderer.invoke(IPC.PLUGINS_INSTALL, { name }),
    uninstall: (name: string): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.PLUGINS_UNINSTALL, { name }),
    toggle: (name: string, enabled: boolean): Promise<{ ok: boolean }> =>
      ipcRenderer.invoke(IPC.PLUGINS_TOGGLE, { name, enabled }),
  },

  // -- Threads (Phase 36+) -----------------------------------------------------
  threads: {
    start: (params: {
      title?: string;
      session_key?: string;
      thread_id?: string;
    }): Promise<ThreadStartResult> => ipcRenderer.invoke(IPC.THREAD_START, params),
    list: (params?: { session_key?: string }): Promise<ThreadListResult> =>
      ipcRenderer.invoke(IPC.THREAD_LIST, params ?? {}),
    read: (threadId: string, sessionKey?: string): Promise<ThreadReadResult> =>
      ipcRenderer.invoke(IPC.THREAD_READ, { thread_id: threadId, session_key: sessionKey }),
    nameSet: (
      threadId: string,
      name: string,
      sessionKey?: string
    ): Promise<{ thread: Record<string, unknown> }> =>
      ipcRenderer.invoke(IPC.THREAD_NAME_SET, {
        thread_id: threadId,
        name,
        session_key: sessionKey,
      }),
    onStarted: (callback: (data: ThreadStartedEvent) => void) => {
      const handler = (_event: Electron.IpcRendererEvent, data: ThreadStartedEvent) =>
        callback(data);
      ipcRenderer.on(IPC_EVENTS.THREAD_STARTED, handler);
      return () => ipcRenderer.removeListener(IPC_EVENTS.THREAD_STARTED, handler);
    },
  },

  // -- Turns (Phase 37+) --------------------------------------------------------
  turns: {
    start: (params: {
      thread_id: string;
      content: string;
      session_key?: string;
      model?: string;
      effort?: string;
    }): Promise<TurnStartResult> => ipcRenderer.invoke(IPC.TURN_START, params),
    interrupt: (
      threadId: string,
      turnId: string,
      sessionKey?: string
    ): Promise<TurnInterruptResult> =>
      ipcRenderer.invoke(IPC.TURN_INTERRUPT, {
        thread_id: threadId,
        turn_id: turnId,
        session_key: sessionKey,
      }),
  },

  // -- Feedback ---------------------------------------------------------------
  feedback: {
    submit: (params: {
      category: string;
      title: string;
      content: string;
      contact?: string;
      app_version?: string;
    }): Promise<FeedbackSubmitResult> =>
      ipcRenderer.invoke(IPC.FEEDBACK_SUBMIT, params),
    list: (params?: { limit?: number }): Promise<FeedbackListResult> =>
      ipcRenderer.invoke(IPC.FEEDBACK_LIST, params ?? {}),
  },
};

contextBridge.exposeInMainWorld('miqi', api);

// Type declaration for renderer
export type MiQiAPI = typeof api;
