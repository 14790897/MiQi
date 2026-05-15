import { z } from 'zod'

// ---------------------------------------------------------------------------
// IPC channel names (invoke)
// ---------------------------------------------------------------------------

export const IPC = {
  // Runtime
  RUNTIME_START: 'runtime:start',
  RUNTIME_STOP: 'runtime:stop',
  RUNTIME_STATUS: 'runtime:status',
  RUNTIME_LOGS: 'runtime:logs',

  // Chat
  CHAT_SEND: 'chat:send',
  CHAT_ABORT: 'chat:abort',

  // Sessions
  SESSIONS_LIST: 'sessions:list',
  SESSIONS_GET: 'sessions:get',
  SESSIONS_DELETE: 'sessions:delete',

  // Config
  CONFIG_GET: 'config:get',
  CONFIG_UPDATE: 'config:update',

  // Providers
  PROVIDERS_LIST: 'providers:list',
  PROVIDERS_TEST: 'providers:test',
  PROVIDERS_UPDATE: 'providers:update',
  CHANNELS_LIST: 'channels:list',
  CHANNELS_UPDATE: 'channels:update',
  APPROVALS_LIST: 'approvals:list',
  APPROVALS_RESOLVE: 'approvals:resolve',
  APPROVALS_CLEAR_PERMANENT: 'approvals:clear_permanent',
  APPROVALS_ADD_PERMANENT: 'approvals:add_permanent',
  APPROVALS_HISTORY: 'approvals:history',
  CRON_LIST: 'cron:list',
  CRON_CREATE: 'cron:create',
  CRON_UPDATE: 'cron:update',
  CRON_DELETE: 'cron:delete',
  CRON_TOGGLE: 'cron:toggle',
  CRON_RUN: 'cron:run',
  CRON_RUNS: 'cron:runs',
  MEMORY_LIST: 'memory:list',
  MEMORY_GET: 'memory:get',
  MEMORY_UPDATE: 'memory:update',
  MEMORY_DELETE: 'memory:delete',
  MEMORY_LESSONS: 'memory:lessons',
  SKILLS_LIST: 'skills:list',
  SKILLS_GET: 'skills:get',
  SKILLS_OPEN_FOLDER: 'skills:open_folder',
  FILES_TREE: 'files:tree',
  FILES_READ: 'files:read',
  FILES_WRITE: 'files:write',
  FILES_DELETE: 'files:delete',
  FILES_DIFF: 'files:diff',
  FILES_REVERT: 'files:revert',

  // Python check
  PYTHON_CHECK: 'python:check',

  // Write initial config (no bridge needed — used by Setup Wizard)
  CONFIG_WRITE_INITIAL: 'config:write_initial',

  // Dialog
  DIALOG_OPEN_FILE: 'dialog:openFile',
} as const

// ---------------------------------------------------------------------------
// IPC event channels (main → renderer)
// ---------------------------------------------------------------------------

export const IPC_EVENTS = {
  RUNTIME_STATE: 'runtime:state',
  RUNTIME_LOG: 'runtime:log',
  CHAT_DELTA: 'chat:delta',
  CHAT_PROGRESS: 'chat:progress',
  CHAT_FINAL: 'chat:final',
  CHAT_ERROR: 'chat:error',
  CHAT_ABORTED: 'chat:aborted',
  APPROVAL_REQUEST: 'approval:request',
  APPROVAL_CLEARED: 'approval:cleared',
} as const

// ---------------------------------------------------------------------------
// Zod schemas for IPC payload validation
// ---------------------------------------------------------------------------

export const ChatSendInput = z.object({
  content: z.string().min(1),
  session_key: z.string().optional(),
})

export const SessionGetInput = z.object({
  session_key: z.string().min(1),
})

export const SessionDeleteInput = z.object({
  session_key: z.string().min(1),
})

export const ConfigUpdateInput = z.object({
  config: z.record(z.unknown()),
})

export const ProviderTestInput = z.object({
  provider_name: z.string().min(1),
  api_key: z.string().optional(),
  api_base: z.string().nullable().optional(),
})

export const ProviderUpdateInput = z.object({
  provider_name: z.string().min(1),
  api_key: z.string().optional(),
  api_base: z.string().nullable().optional(),
  extra_headers: z.record(z.string()).nullable().optional(),
  model: z.string().optional(),
})

// ---------------------------------------------------------------------------
// Runtime state
// ---------------------------------------------------------------------------

export type RuntimeState =
  | 'stopped'
  | 'starting'
  | 'running'
  | 'stopping'
  | 'error'

export interface RuntimeStatus {
  state: RuntimeState
  configured: boolean
  python_version?: string
  error?: string
}

// ---------------------------------------------------------------------------
// Session types
// ---------------------------------------------------------------------------

export interface SessionInfo {
  key: string
  created_at?: string
  updated_at?: string
  path?: string
}

export interface SessionDetail {
  key: string
  messages: Record<string, unknown>[]
  created_at: string
  updated_at: string
  metadata: Record<string, unknown>
}

// ---------------------------------------------------------------------------
// Provider types
// ---------------------------------------------------------------------------

export interface ProviderInfo {
  name: string
  display_name: string
  env_key: string
  provider_type: string
  is_gateway: boolean
  is_local: boolean
  default_api_base: string
  configured: boolean
  api_base: string | null
  configured_model?: string
}

export interface ProviderUpdateResult {
  saved: boolean
  provider_name: string
}

export interface FeishuChannelConfig {
  enabled: boolean
  app_id: string
  app_secret: string
  allow_from: string[]
  reply_delay_ms: number
  require_mention_in_groups: boolean
}

export interface ChannelsConfig {
  send_progress: boolean
  send_tool_hints: boolean
  send_queue_notifications: boolean
  feishu: FeishuChannelConfig
}

export const ChannelsUpdateInput = z.object({
  channels: z.record(z.unknown()),
})

export interface ApprovalRequest {
  approval_id: string
  command: string
  description: string
  allow_permanent: boolean
}

export interface PendingApproval {
  approval_id: string
  command: string
  description: string
  allow_permanent: boolean
  created_at: number
  age_seconds: number
}

export interface PermanentEntry {
  pattern: string
  added_at: number
}

export interface ApprovalHistoryEntry {
  id: string
  pattern_key: string
  description: string
  command: string
  decision: string
  timestamp: number
  session_key: string
}

export interface ApprovalsListResult {
  pending: PendingApproval[]
  pending_ids: string[]
  permanent_allowlist: string[]
  permanent_entries: PermanentEntry[]
  enabled: boolean
  timeout: number
}

export interface ApprovalsAddPermanentResult {
  added: boolean
  pattern: string
}

export interface ApprovalsHistoryResult {
  history: ApprovalHistoryEntry[]
}

export const ApprovalsAddPermanentInput = z.object({
  pattern: z.string().min(1),
})

export interface ApprovalCleared {
  reason: 'abort' | 'resolved' | 'timeout'
}

// ---------------------------------------------------------------------------
// Cron schemas
// ---------------------------------------------------------------------------

export const CronCreateInput = z.object({
  name: z.string().min(1),
  scheduleKind: z.enum(['at', 'every', 'cron']),
  atMs: z.number().optional(),
  everyMs: z.number().optional(),
  expr: z.string().optional(),
  tz: z.string().optional(),
  message: z.string().optional(),
  deliver: z.boolean().optional(),
  channel: z.string().nullable().optional(),
  to: z.string().nullable().optional(),
})

export const CronUpdateInput = z.object({
  jobId: z.string().min(1),
  name: z.string().optional(),
  scheduleKind: z.enum(['at', 'every', 'cron']).optional(),
  atMs: z.number().optional(),
  everyMs: z.number().optional(),
  expr: z.string().optional(),
  tz: z.string().nullable().optional(),
  message: z.string().optional(),
  deliver: z.boolean().optional(),
  channel: z.string().nullable().optional(),
  to: z.string().nullable().optional(),
})

export const CronToggleInput = z.object({
  jobId: z.string().min(1),
  enabled: z.boolean(),
})

export const CronDeleteInput = z.object({
  jobId: z.string().min(1),
})

export const CronRunInput = z.object({
  jobId: z.string().min(1),
})

export const CronRunsInput = z.object({
  jobId: z.string().optional(),
})

export interface CronSchedule {
  kind: 'at' | 'every' | 'cron'
  atMs: number | null
  everyMs: number | null
  expr: string | null
  tz: string | null
}

export interface CronPayload {
  kind: 'system_event' | 'agent_turn'
  message: string
  deliver: boolean
  channel: string | null
  to: string | null
}

export interface CronState {
  nextRunAtMs: number | null
  lastRunAtMs: number | null
  lastStatus: 'ok' | 'error' | 'skipped' | null
  lastError: string | null
}

export interface CronJob {
  id: string
  name: string
  enabled: boolean
  schedule: CronSchedule
  payload: CronPayload
  state: CronState
  createdAtMs: number
  updatedAtMs: number
  deleteAfterRun: boolean
}

export interface CronRunEntry {
  jobId: string
  jobName: string
  startedAtMs: number
  status: 'ok' | 'error' | 'skipped' | null
  error: string | null
}

export interface CronListResult {
  jobs: CronJob[]
}

export interface CronCreateResult {
  job: CronJob
}

export interface CronUpdateResult {
  job: CronJob
}

export interface CronRunsResult {
  runs: CronRunEntry[]
}

// ---------------------------------------------------------------------------
// Memory schemas
// ---------------------------------------------------------------------------

export const MemoryGetInput = z.object({
  path: z.string().min(1),
})

export const MemoryUpdateInput = z.object({
  path: z.string().min(1),
  content: z.string(),
})

export interface MemoryFileInfo {
  path: string
  scope: 'workspace' | 'agent'
  size: number
  updatedAtMs: number
}

export interface MemoryListResult {
  files: MemoryFileInfo[]
}

export interface MemoryGetResult {
  path: string
  content: string
  size: number
}

export interface MemoryLessonEntry {
  id: string
  trigger: string
  badAction: string
  betterAction: string
  scope: string
  sessionKey: string | null
  confidence: number
  effectiveConfidence: number
  hits: number
  enabled: boolean
  source: string
  createdAt: string
  updatedAt: string
}

export interface MemoryLessonsResult {
  lessons: MemoryLessonEntry[]
}

// ---------------------------------------------------------------------------
// Skills schemas
// ---------------------------------------------------------------------------

export const SkillsGetInput = z.object({
  name: z.string().min(1),
})

export interface SkillSummary {
  name: string
  source: 'builtin' | 'workspace'
  path: string
  description: string
  available: boolean
  missingRequirements: string | null
}

export interface SkillsListResult {
  skills: SkillSummary[]
}

export interface SkillDetail {
  name: string
  source: 'builtin' | 'workspace'
  path: string
  description: string
  available: boolean
  missingRequirements: string | null
  content: string
  metadata: Record<string, unknown> | null
}

// ---------------------------------------------------------------------------
// Files schemas
// ---------------------------------------------------------------------------

export const FilesReadInput = z.object({
  path: z.string().min(1),
})

export const FilesWriteInput = z.object({
  path: z.string().min(1),
  content: z.string(),
})

export interface FileNode {
  name: string
  path: string
  is_dir: boolean
  children?: FileNode[]
}

export interface FilesTreeResult {
  root: FileNode
  workspace_path: string
}

export interface FilesReadResult {
  path: string
  content: string
  size: number
}

export interface FilesWriteResult {
  saved: boolean
  path: string
}

export interface FilesDiffResult {
  path: string
  diff: string | null
  has_diff: boolean
  original_content: string | null
  current_content: string | null
  error?: string
}

export interface FilesRevertResult {
  reverted: boolean
  path: string
}

// ---------------------------------------------------------------------------
// Chat types
// ---------------------------------------------------------------------------

export interface ChatProgress {
  text: string
  tool_hint: boolean
}

export interface ChatFinal {
  content: string
  aborted?: boolean
}

export interface ChatError {
  message: string
}

export interface ChatAborted {
  message: string
}

// ---------------------------------------------------------------------------
// Python check result
// ---------------------------------------------------------------------------

export interface PythonCheckResult {
  ok: boolean
  python_version: string
  issues: string[]
  config_exists: boolean
}
