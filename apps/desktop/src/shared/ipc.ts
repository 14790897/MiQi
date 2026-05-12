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

  // Python check
  PYTHON_CHECK: 'python:check',

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
})

// ---------------------------------------------------------------------------
// Runtime state
// ---------------------------------------------------------------------------

export type RuntimeState = 'stopped' | 'starting' | 'running' | 'stopping' | 'error'

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

export interface ApprovalsListResult {
  pending_ids: string[]
  permanent_allowlist: string[]
  enabled: boolean
  timeout: number
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
