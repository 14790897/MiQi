import { z } from 'zod';

// ---------------------------------------------------------------------------
// IPC channel names (invoke)
// ---------------------------------------------------------------------------

export const IPC = {
  // Runtime
  RUNTIME_START: 'runtime:start',
  RUNTIME_STOP: 'runtime:stop',
  RUNTIME_STATUS: 'runtime:status',
  RUNTIME_LOGS: 'runtime:logs',
  RUNTIME_FILE_LOGS: 'runtime:file-logs',
  RUNTIME_BACKEND_LOGS: 'runtime:backend-logs',

  // Chat
  CHAT_SEND: 'chat:send',
  CHAT_ABORT: 'chat:abort',

  // Threads (Codex-style, Phase 36+)
  THREAD_START: 'thread:start',
  THREAD_LIST: 'thread:list',
  THREAD_READ: 'thread:read',
  THREAD_NAME_SET: 'thread:name:set',

  // Turns (Codex-style, Phase 37+)
  TURN_START: 'turn:start',
  TURN_INTERRUPT: 'turn:interrupt',

  // Sessions
  SESSIONS_LIST: 'sessions:list',
  SESSIONS_GET: 'sessions:get',
  SESSIONS_DELETE: 'sessions:delete',
  SESSIONS_ARCHIVE: 'sessions:archive',
  SESSIONS_UNARCHIVE: 'sessions:unarchive',
  SESSIONS_LIST_ARCHIVED: 'sessions:list_archived',
  SESSIONS_GET_TRACKED_FILES: 'sessions:get_tracked_files',
  SESSIONS_CLEAR_TRACKED_FILES: 'sessions:clear_tracked_files',
  SESSIONS_CLAIM_LEGACY: 'sessions:claim_legacy',

  // Config
  CONFIG_GET: 'config:get',
  CONFIG_UPDATE: 'config:update',

  // Providers
  PROVIDERS_LIST: 'providers:list',
  PROVIDERS_TEST: 'providers:test',
  PROVIDERS_UPDATE: 'providers:update',
  PROVIDERS_ACTIVATE: 'providers:activate',
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
  MEMORY_LESSON_UNLEARN: 'memory:lesson:unlearn',

  // Experience store
  EXPERIENCE_LIST: 'experience:list',
  EXPERIENCE_DELETE: 'experience:delete',
  EXPERIENCE_TOGGLE: 'experience:toggle',
  EXPERIENCE_SEARCH: 'experience:search',
  SKILLS_LIST: 'skills:list',
  SKILLS_GET: 'skills:get',
  SKILLS_OPEN_FOLDER: 'skills:open_folder',
  SKILLS_CREATE: 'skills:create',
  SKILLS_UPLOAD: 'skills:upload',
  SKILLS_DELETE: 'skills:delete',

  // MCP
  MCP_LIST: 'mcp:list',
  MCP_UPSERT: 'mcp:upsert',
  MCP_DELETE: 'mcp:delete',
  FILES_TREE: 'files:tree',
  FILES_READ: 'files:read',
  FILES_WRITE: 'files:write',
  FILES_DELETE: 'files:delete',
  FILES_DIFF: 'files:diff',
  FILES_REVERT: 'files:revert',
  FILES_ACCEPT: 'files:accept',
  FILES_OPEN_EXTERNAL: 'files:openExternal',
  FILES_OPEN_CONTAINING_FOLDER: 'files:openContainingFolder',

  // Python check
  PYTHON_CHECK: 'python:check',

  // WSL2 check & install (Windows only, no bridge needed)
  WSL_CHECK: 'wsl:check',
  WSL_INSTALL: 'wsl:install',
  WSL_EXPORT_DISTRO: 'wsl:export_distro',
  WSL_IMPORT_DISTRO: 'wsl:import_distro',
  WSL_GET_STATS: 'wsl:getStats',

  // Sandbox runtime toggle
  SANDBOX_SET_ENABLED: 'sandbox:setEnabled',

  // Write initial config (no bridge needed �? used by Setup Wizard)
  CONFIG_WRITE_INITIAL: 'config:write_initial',

  // Dialog
  DIALOG_OPEN_FILE: 'dialog:openFile',

  // New: Multi-Agent (Phase 1)
  AGENT_LIST: 'agent:list',
  AGENT_KILL: 'agent:kill',
  AGENT_SPAWN: 'agent:spawn',

  // New: Plan tracking (Phase 2)
  PLAN_GET: 'plan:get',

  // New: Permissions (Phase 1)
  PERMISSIONS_GET: 'permissions:get',
  PERMISSIONS_UPDATE: 'permissions:update',
  PERMISSIONS_PERMANENT_ADD: 'permissions:permanent:add',
  PERMISSIONS_PERMANENT_REMOVE: 'permissions:permanent:remove',

  // New: Plugin management (Phase 4)
  PLUGINS_LIST: 'plugins:list',
  PLUGINS_INSTALL: 'plugins:install',
  PLUGINS_UNINSTALL: 'plugins:uninstall',
  PLUGINS_TOGGLE: 'plugins:toggle',
  FEEDBACK_SUBMIT: 'feedback:submit',
  FEEDBACK_LIST: 'feedback:list',
} as const;

// ---------------------------------------------------------------------------
// IPC event channels (main �? renderer)
// ---------------------------------------------------------------------------

export const IPC_EVENTS = {
  RUNTIME_STATE: 'runtime:state',
  RUNTIME_LOG: 'runtime:log',
  CHAT_DELTA: 'chat:delta',
  CHAT_PROGRESS: 'chat:progress',
  CHAT_FINAL: 'chat:final',
  CHAT_ERROR: 'chat:error',
  CHAT_ABORTED: 'chat:aborted',
  CHAT_SUBAGENT_RESULT: 'chat:subagent_result',
  APPROVAL_REQUEST: 'approval:request',
  APPROVAL_CLEARED: 'approval:cleared',

  // New events (Phase 1)
  AGENT_SPAWNED: 'agent:spawned',
  AGENT_COMPLETED: 'agent:completed',
  PLAN_UPDATED: 'plan:updated',
  TURN_STARTED: 'turn:started',
  TURN_COMPLETED: 'turn:completed',
  THREAD_STARTED: 'thread:started',
} as const;

// ---------------------------------------------------------------------------
// Zod schemas for IPC payload validation
// ---------------------------------------------------------------------------

export const ChatSendInput = z.object({
  content: z.string().min(1),
  session_key: z.string().optional(),
  thread_id: z.string().optional(),
});

export const SessionGetInput = z.object({
  session_key: z.string().min(1),
});

export const SessionDeleteInput = z.object({
  session_key: z.string().min(1),
});

export const SessionClaimLegacyInput = z.object({
  session_key: z.string().min(1),
});

export interface SessionClaimLegacyResult {
  claimed: boolean;
  session_key: string;
  owner_client_id: string;
  error?: string;
}

export const ConfigUpdateInput = z.object({
  config: z.record(z.unknown()),
});

export const ProviderTestInput = z.object({
  provider_name: z.string().min(1),
  api_key: z.string().optional(),
  api_base: z.string().nullable().optional(),
  model: z.string().optional(),
});

export const ProviderUpdateInput = z.object({
  provider_name: z.string().min(1),
  api_key: z.string().optional(),
  api_base: z.string().nullable().optional(),
  extra_headers: z.record(z.string()).nullable().optional(),
  model: z.string().optional(),
});

export const ProviderActivateInput = z.object({
  provider_name: z.string().min(1),
  activation_code: z.string().min(1),
});

// New Phase 1 schemas
export const AgentSpawnInput = z.object({
  agent_type: z.string().min(1),
  task: z.string().min(1),
  label: z.string().optional(),
});

export const PermissionsUpdateInput = z.object({
  filesystem: z
    .object({
      rules: z.array(
        z.object({
          path: z.string(),
          mode: z.enum(['read', 'write', 'none']),
          recursive: z.boolean().optional(),
        })
      ),
      default_mode: z.enum(['read', 'write', 'none']).optional(),
    })
    .optional(),
  network: z.enum(['allow_all', 'block_all', 'allow_list']).optional(),
  exec_approval: z.enum(['never', 'dangerous', 'always']).optional(),
});

// ---------------------------------------------------------------------------
// Runtime state
// ---------------------------------------------------------------------------

export type RuntimeState = 'stopped' | 'starting' | 'running' | 'stopping' | 'error';

export interface RuntimeStatus {
  state: RuntimeState;
  configured: boolean;
  python_version?: string;
  sandbox_available?: boolean;
  error?: string;
}

// ---------------------------------------------------------------------------
// Session types
// ---------------------------------------------------------------------------

export interface SessionInfo {
  key: string;
  title?: string;
  created_at?: string;
  updated_at?: string;
  path?: string;
  message_count?: number;
}

export interface SessionDetail {
  key: string;
  messages: Record<string, unknown>[];
  created_at: string;
  updated_at: string;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Provider types
// ---------------------------------------------------------------------------

export interface ProviderInfo {
  name: string;
  display_name: string;
  env_key: string;
  provider_type: string;
  is_gateway: boolean;
  is_local: boolean;
  default_api_base: string;
  configured: boolean;
  api_key_hint?: string | null;
  api_base: string | null;
  configured_model?: string;
  verification_status?: 'missing' | 'unverified' | 'success' | 'failed';
  verified_at?: string | null;
  verification_message?: string | null;
  builtin_available?: boolean;
  builtin_activated?: boolean;
}

export interface ProvidersListResult {
  providers: ProviderInfo[];
  active_model?: string;
  active_provider?: string | null;
}

export interface ProviderUpdateResult {
  saved: boolean;
  provider_name: string;
}

export interface ProviderActivateResult {
  activated: boolean;
  provider_name: string;
  error?: string;
}

export interface FeishuChannelConfig {
  enabled: boolean;
  app_id: string;
  app_secret: string;
  allow_from: string[];
  reply_delay_ms: number;
  require_mention_in_groups: boolean;
}

export interface ChannelsConfig {
  send_progress: boolean;
  send_tool_hints: boolean;
  send_queue_notifications: boolean;
  feishu: FeishuChannelConfig;
}

export const ChannelsUpdateInput = z.object({
  channels: z.record(z.unknown()),
});

export interface ApprovalRequest {
  approval_id: string;
  command?: string; // may be empty for non-exec approvals
  description: string;
  allow_permanent: boolean;
  category?: string; // "exec" | "file_write" | "unknown_tool" | ...
  details?: Record<string, unknown>; // e.g. { command, path, operation, tool_name }
}

export interface PendingApproval {
  approval_id: string;
  command?: string; // may be empty for non-exec approvals
  description: string;
  category?: string; // "exec" | "file_write" | "network" | "patch_apply"
  details?: Record<string, unknown>; // structured approval metadata
  allow_permanent: boolean;
  created_at: number;
  age_seconds: number;
}

export interface PermanentEntry {
  pattern: string;
  added_at: number;
}

export interface ApprovalHistoryEntry {
  id: string;
  pattern_key: string;
  description: string;
  command: string;
  decision: string;
  timestamp: number;
  session_key: string;
}

export interface ApprovalsListResult {
  pending: PendingApproval[];
  pending_ids: string[];
  permanent_allowlist: string[];
  permanent_entries: PermanentEntry[];
  enabled: boolean;
  timeout: number;
}

export interface ApprovalsAddPermanentResult {
  added: boolean;
  pattern: string;
}

export interface ApprovalsHistoryResult {
  history: ApprovalHistoryEntry[];
}

export const ApprovalsAddPermanentInput = z.object({
  pattern: z.string().min(1),
});

export interface ApprovalCleared {
  reason: 'abort' | 'resolved' | 'timeout';
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
});

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
});

export const CronToggleInput = z.object({
  jobId: z.string().min(1),
  enabled: z.boolean(),
});

export const CronDeleteInput = z.object({
  jobId: z.string().min(1),
});

export const CronRunInput = z.object({
  jobId: z.string().min(1),
});

export const CronRunsInput = z.object({
  jobId: z.string().optional(),
});

export interface CronSchedule {
  kind: 'at' | 'every' | 'cron';
  atMs: number | null;
  everyMs: number | null;
  expr: string | null;
  tz: string | null;
}

export interface CronPayload {
  kind: 'system_event' | 'agent_turn';
  message: string;
  deliver: boolean;
  channel: string | null;
  to: string | null;
}

export interface CronState {
  nextRunAtMs: number | null;
  lastRunAtMs: number | null;
  lastStatus: 'ok' | 'error' | 'skipped' | null;
  lastError: string | null;
}

export interface CronJob {
  id: string;
  name: string;
  enabled: boolean;
  schedule: CronSchedule;
  payload: CronPayload;
  state: CronState;
  createdAtMs: number;
  updatedAtMs: number;
  deleteAfterRun: boolean;
}

export interface CronRunEntry {
  jobId: string;
  jobName: string;
  startedAtMs: number;
  status: 'ok' | 'error' | 'skipped' | null;
  error: string | null;
}

export interface CronListResult {
  jobs: CronJob[];
}

export interface CronCreateResult {
  job: CronJob;
}

export interface CronUpdateResult {
  job: CronJob;
}

export interface CronRunsResult {
  runs: CronRunEntry[];
}

// ---------------------------------------------------------------------------
// Memory schemas
// ---------------------------------------------------------------------------

export const MemoryGetInput = z.object({
  path: z.string().min(1),
});

export const MemoryUpdateInput = z.object({
  path: z.string().min(1),
  content: z.string(),
});

export interface MemoryFileInfo {
  path: string;
  scope: 'workspace' | 'agent';
  size: number;
  updatedAtMs: number;
}

export interface MemoryListResult {
  files: MemoryFileInfo[];
}

export interface MemoryGetResult {
  path: string;
  content: string;
  size: number;
}

export interface MemoryLessonEntry {
  id: string;
  trigger: string;
  badAction: string;
  betterAction: string;
  scope: string;
  sessionKey: string | null;
  confidence: number;
  effectiveConfidence: number;
  hits: number;
  state: string;
  enabled: boolean;
  source: string;
  createdAt: string;
  updatedAt: string;
}

export interface MemoryLessonsResult {
  lessons: MemoryLessonEntry[];
}

export const MemoryLessonUnlearnInput = z.object({
  lesson_id: z.string().min(1),
});

export interface MemoryLessonUnlearnResult {
  unlearned: string[];
}

export interface ExperienceEntry {
  id: string;
  type: 'fact' | 'rule' | 'trace';
  title: string;
  content: string;
  confidence: number;
  enabled: boolean;
  scope: string;
  source: string;
  session_key: string;
  created_at: number;
  updated_at: number;
  metadata: Record<string, unknown>;
}

// ---------------------------------------------------------------------------
// Skills schemas
// ---------------------------------------------------------------------------

export const SkillsGetInput = z.object({
  name: z.string().min(1),
});

export interface SkillSummary {
  name: string;
  source: 'builtin' | 'workspace';
  path: string;
  description: string;
  available: boolean;
  missingRequirements: string | null;
}

export interface SkillsListResult {
  skills: SkillSummary[];
}

export interface SkillDetail {
  name: string;
  source: 'builtin' | 'workspace';
  path: string;
  description: string;
  available: boolean;
  missingRequirements: string | null;
  content: string;
  metadata: Record<string, unknown> | null;
}

// ---------------------------------------------------------------------------
// MCP schemas
// ---------------------------------------------------------------------------

export interface McpServerConfig {
  command?: string;
  args?: string[];
  env?: Record<string, string>;
  url?: string;
  headers?: Record<string, string>;
  tool_timeout?: number;
  progress_interval_seconds?: number;
  description?: string;
  lazy?: boolean;
}

export interface McpServerInfo extends McpServerConfig {
  name: string;
}

export const McpUpsertInput = z.object({
  name: z.string().min(1),
  command: z.string().optional(),
  args: z.array(z.string()).optional(),
  env: z.record(z.string()).optional(),
  url: z.string().optional(),
  headers: z.record(z.string()).optional(),
  tool_timeout: z.number().optional(),
  progress_interval_seconds: z.number().optional(),
  description: z.string().optional(),
  lazy: z.boolean().optional(),
});

export const McpDeleteInput = z.object({
  name: z.string().min(1),
});

// ---------------------------------------------------------------------------
// Files schemas
// ---------------------------------------------------------------------------

export const FilesReadInput = z.object({
  path: z.string().min(1),
  session_key: z.string().optional(),
});

export const FilesWriteInput = z.object({
  path: z.string().min(1),
  content: z.string(),
  session_key: z.string().optional(),
});

export interface FileNode {
  name: string;
  path: string;
  is_dir: boolean;
  children?: FileNode[];
}

export interface FilesTreeResult {
  root: FileNode;
  workspace_path: string;
}

export interface FilesReadResult {
  path: string;
  content?: string;
  data_base64?: string;
  size: number;
  mime_type?: string;
  is_binary?: boolean;
}

export interface FilesWriteResult {
  saved: boolean;
  path: string;
}

export interface FilesDiffResult {
  path: string;
  diff: string | null;
  has_diff: boolean;
  original_content: string | null;
  current_content: string | null;
  error?: string;
  is_new_file?: boolean;
}

export interface FilesRevertResult {
  reverted: boolean;
  path: string;
}

export interface FilesOpenExternalResult {
  opened: boolean;
  path: string;
  error?: string;
}

export interface FilesOpenContainingFolderResult {
  revealed: boolean;
  path: string;
  error?: string;
}

export interface TrackedFileInfo {
  path: string;
  op: 'read' | 'write' | 'edit' | 'delete';
  name: string;
  lastSeen: number;
}

// ---------------------------------------------------------------------------
// Chat types
// ---------------------------------------------------------------------------

export interface ChatProgress {
  text: string;
  tool_hint: boolean;
  stream?: 'stdout' | 'stderr';
  delta?: string;
  tool_call_id?: string;
  /** Session key for frontend-side event filtering (fix #212).
   *  Optional for backward compatibility with backends that don't yet
   *  emit this field.  Should become required once all backends are
   *  updated. */
  session_key?: string;
}

export interface ChatFinal {
  content: string;
  aborted?: boolean;
  tool_calls?: unknown[];
  /** Session key for frontend-side event filtering (fix #212).  Optional
   *  for backward compatibility; see ChatProgress.session_key. */
  session_key?: string;
}

export interface ChatError {
  message: string;
  /** Session key for frontend-side event filtering (fix #212).  Optional
   *  for backward compatibility; see ChatProgress.session_key. */
  session_key?: string;
}

export interface ChatAborted {
  message: string;
  /** Session key for frontend-side event filtering (fix #212).  Optional
   *  for backward compatibility; see ChatProgress.session_key. */
  session_key?: string;
}

export interface ChatSubagentResult {
  task_id: string;
  label: string;
  task: string;
  result: string;
  status: string; // "ok" | "error"
  session_key: string;
}

// ---------------------------------------------------------------------------
// Python check result
// ---------------------------------------------------------------------------

export interface PythonCheckResult {
  ok: boolean;
  python_version: string;
  issues: string[];
  config_exists: boolean;
}

// ---------------------------------------------------------------------------
// WSL2 check result
// ---------------------------------------------------------------------------

export interface WslCheckResult {
  isWindows: boolean;
  installed: boolean;
  version: string | null; // e.g. "2" or "1"
  distros: string[]; // e.g. ["Ubuntu"]
  defaultDistro: string | null;
  running: boolean; // whether WSL is currently active
}
export interface WslExportDistroResult {
  exported: boolean;
  distro: string | null; // exported distro name
  tarPath: string | null; // path to exported tar file
  error: string | null;
}
export interface WslImportDistroResult {
  imported: boolean;
  distro: string | null; // imported distro name
  installLocation: string | null; // where the distro was installed
  error: string | null;
}

// ---------------------------------------------------------------------------
// WSL runtime stats (memory / CPU / disk)
// ---------------------------------------------------------------------------

export interface WslStatsResult {
  ok: boolean;
  error?: string;
  distro: string; // which distro was queried
  memory: {
    total_mb: number;
    used_mb: number;
    free_mb: number;
    used_pct: number; // 0-100
  };
  cpu: {
    usage_pct: number; // 0-100, instantaneous snapshot
    cores: number;
  };
  disk: {
    total_gb: number;
    used_gb: number;
    free_gb: number;
    used_pct: number;
  };
  uptime_sec: number;
}

// ---------------------------------------------------------------------------
// Phase 1: New types for multi-agent, plan, permissions
// ---------------------------------------------------------------------------

export interface LiveAgentInfo {
  agent_id: string;
  thread_id: string;
  type: string;
  status:
    'idle' | 'thinking' | 'executing' | 'waiting_approval' | 'completed' | 'error' | 'aborted';
  parent: string | null;
  label: string;
  spawned_at: number;
}

export interface PlanStep {
  id: string;
  description: string;
  status: 'pending' | 'in_progress' | 'completed' | 'skipped';
  depends_on: string[];
}

export interface Plan {
  plan_id: string;
  title: string;
  steps: PlanStep[];
  created_at: number;
  updated_at: number;
}

export interface AgentSpawnedEvent {
  sub_agent_id: string;
  sub_thread_id: string;
  agent_type: string;
  task_label: string;
}

export interface AgentCompletedEvent {
  sub_agent_id: string;
  sub_thread_id: string;
  outcome: string;
  summary: string;
}

export interface PlanUpdatedEvent {
  plan: Plan;
}

export interface TurnStartedEvent {
  turn_id: string;
  agent_name: string;
  thread_id: string;
}

export interface TurnCompletedEvent {
  turn_id: string;
  thread_id: string;
  outcome: string;
  tools_used: string[];
  token_usage: Record<string, number>;
}

// ── Thread / Turn types (Phase 36+) ───────────────────────────────────────

export const ThreadStartInput = z.object({
  title: z.string().optional(),
  session_key: z.string().optional(),
  thread_id: z.string().optional(),
});

export const ThreadReadInput = z.object({
  thread_id: z.string().min(1),
  session_key: z.string().optional(),
});

export const ThreadNameSetInput = z.object({
  thread_id: z.string().min(1),
  name: z.string().min(1),
  session_key: z.string().optional(),
});

export const TurnStartInput = z.object({
  thread_id: z.string().min(1),
  content: z.string().min(1),
  session_key: z.string().optional(),
  model: z.string().optional(),
  effort: z.string().optional(),
});

export const TurnInterruptInput = z.object({
  thread_id: z.string().min(1),
  turn_id: z.string().min(1),
  session_key: z.string().optional(),
});

export const ChatAbortInput = z.object({
  session_key: z.string().optional(),
  thread_id: z.string().optional(),
});

export const AgentListInput = z.object({
  session_key: z.string().optional(),
});

export interface ThreadInfo {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  turn_count: number;
}

export interface ThreadStartResult {
  thread: Record<string, unknown>;
}

export interface ThreadListResult {
  items: Record<string, unknown>[];
  nextCursor?: null | string;
}

export interface ThreadReadResult {
  thread: Record<string, unknown>;
}

export interface TurnStartResult {
  turn: Record<string, unknown>;
}

export interface TurnInterruptResult {
  interrupted: boolean;
}

export interface ThreadStartedEvent {
  thread: Record<string, unknown>;
}

export interface SandboxSetEnabledResult {
  enabled: boolean;
  destroyed?: number;
  already?: boolean;
  initializing?: boolean;
}

// ---------------------------------------------------------------------------
// Feedback schemas
// ---------------------------------------------------------------------------

// Per-screenshot validator: must be a `data:image/<mime>;base64,<...>`
// URL whose decoded byte size is within the documented 10 MB limit.
// Mirrors the server-side check in miqi/runtime/feedback_handlers.py
// _decode_data_url so oversized/malformed payloads are rejected at the
// IPC boundary before they reach the bridge.
const MAX_DATA_URL_BYTES = 10 * 1024 * 1024;
const dataUrlScreenshot = z
  .string()
  .refine(
    (s) => s.startsWith('data:image/') && s.includes(';base64,'),
    'Screenshot must be a base64-encoded data URL with image MIME type',
  )
  .refine(
    (s) => {
      const comma = s.indexOf(',');
      if (comma < 0) return false;
      const b64 = s.slice(comma + 1);
      // base64 inflates ~4/3, so 14 MB encoded → ~10.5 MB decoded
      return b64.length * 3 <= MAX_DATA_URL_BYTES * 4 + 4;
    },
    'Screenshot exceeds 10 MB limit',
  );

export const FeedbackSubmitInput = z.object({
  category: z.enum(['bug', 'question', 'suggestion', 'other']),
  title: z.string().min(1).max(200),
  content: z.string().min(1).max(10000),
  contact: z.string().max(200).optional(),
  app_version: z.string().max(50).optional(),
  screenshots: z.array(dataUrlScreenshot).max(5).optional(),
  prompt_used: z.string().max(10000).optional(),
  repro_frequency: z.string().max(200).optional(),
});

export interface FeedbackEntry {
  id: string;
  category: 'bug' | 'question' | 'suggestion' | 'other';
  title: string;
  content: string;
  contact: string;
  app_version: string;
  os: string;
  python_version: string;
  feishu_record_id: string;
  created_at: string;
}

export interface FeedbackListResult {
  entries: FeedbackEntry[];
}

export interface FeedbackSubmitResult {
  ok: boolean;
  record_id: string;
}
