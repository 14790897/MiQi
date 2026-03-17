# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
- Added Feishu group chat @mention filtering (`channels/feishu.py`):
  - New config `channels.feishu.requireMentionInGroups` (default `true`).
  - In group chats, messages are only forwarded to the agent when the bot is @mentioned.
  - @mention placeholder (`@_user_N`) is automatically stripped from the message text.
  - Private chats (p2p) remain unaffected and always forwarded.
- Added MCP tool heartbeat progress reporting (`agent/tools/mcp.py`, `agent/loop.py`):
  - New config `tools.mcpServers.<name>.progressIntervalSeconds` (default `15`).
  - During long-running MCP tool calls, periodic status messages are sent to the user (e.g. "⏳ raspa_run_simulation 正在执行中... (已用时 1m30s)").
  - Heartbeat task is automatically cancelled when the tool finishes.
  - Existing MCP SDK progress callbacks remain functional alongside heartbeat.
- Added task queue tracker with user notifications (`agent/loop.py`):
  - New `TaskTracker` class tracks active and pending tasks.
  - New config `channels.sendQueueNotifications` (default `true`).
  - When agent is busy, new messages are queued and senders receive position notifications (e.g. "✅ 收到！当前正在处理 Alice 的任务，您排在第 2 位，请稍候。").
  - When a queued task starts processing, sender receives "🚀 开始处理您的任务...".
  - CLI and system messages bypass the queue for immediate processing.
- Added `sender_name` field to `InboundMessage` (`bus/events.py`) for display-friendly queue notifications.
- Added `sender_name` parameter to `BaseChannel._handle_message()` (`channels/base.py`).
- Added tests for new features:
  - `tests/test_task_tracker.py`: TaskTracker unit tests, MCP heartbeat integration test, InboundMessage sender_name tests.
  - `tests/test_feishu_mention_filter.py`: Feishu group @mention filtering tests, config schema tests.
- Added modular CLI command files:
  - `featherflow/cli/onboard.py`
  - `featherflow/cli/agent_cmd.py`
  - `featherflow/cli/gateway_cmd.py`
  - `featherflow/cli/management.py`
- Added core regression tests:
  - `tests/test_agent_loop_core.py`
  - `tests/test_cron_service_core.py`
- Added project documentation:
  - `docs/API.md`
  - `docs/DEVELOPER_GUIDE.md`
  - `docs/ARCHITECTURE.md`
  - `CONTRIBUTING.md`
- Added Feishu business tools in `featherflow/agent/tools/feishu.py`:
  - `feishu_doc` for cloud doc creation and optional plain-text write.
  - `feishu_calendar` for calendar event creation and attendee assignment.
  - `feishu_task` for task creation with group-member assignment.
  - `feishu_drive` for Drive folder creation (`create_folder` / `ensure_folder_path`) and workspace file uploads.
  - `feishu_handoff` as a generic collaboration handoff layer that orchestrates delivery steps.
- Added Feishu mention metadata extraction (`sender_open_id`, `mentions`) in `featherflow/channels/feishu.py`.
- Added Feishu tool usage guidance in `featherflow/templates/TOOLS.md`.
- Added `paper_download` tool in `featherflow/agent/tools/papers.py` to download PDFs into workspace.
- Added documentation updates for Feishu collaboration + paper delivery workflow:
  - README feature/capability updates
  - API docs for `paper_download`, `feishu_drive`, and `feishu_handoff`
  - Feishu backend permission checklist in `docs/API.md`

### Changed
- Refactored `featherflow/cli/commands.py` into an entry/compatibility layer that registers split command modules.
- Refactored arXiv XML parsing in `featherflow/agent/tools/papers.py` by extracting shared `_parse_arxiv_entry` logic.
- Replaced remaining built-in `print()` calls with `loguru.logger` warnings in `featherflow/config/loader.py`.
- Split memory implementation into package modules with `MemoryStore` facade in `featherflow/agent/memory/store.py`.
- Normalized provider `api_base` handling in `LiteLLMProvider` to auto-fill missing default base paths (for example `/v1`, `/api/v1`) when users provide host-only URLs, while preserving explicit custom paths.
- Updated `AgentLoop` tool wiring in `featherflow/agent/loop.py` to:
  - auto-register Feishu business tools when Feishu credentials are configured.
  - propagate message context (`channel`, `chat_id`, `message_id`, `sender_id`, `metadata`) into Feishu tools for group assignment resolution.
  - include the generic Feishu handoff tool in runtime registration/context propagation.
- Added paywall-aware PDF download behavior:
  - detects common login/paywall HTML responses and returns structured errors instead of saving invalid `.pdf` files.
- Updated Feishu Drive upload implementation to support multipart upload (分片上传) for files > 20 MB:
  - `_upload_file_multipart()`: full 3-step flow — `upload_prepare` → `upload_part × block_num` → `upload_finish`.
  - Auto-routing in `_upload_file()`: ≤ 20 MB → `upload_all`, > 20 MB → multipart.
  - Added `_FEISHU_UPLOAD_ALL_MAX_BYTES = 20 MB` constant (per Feishu official docs 2024-10-23 hard limit).
- Added `feishu_drive` action `grant_permission`: calls `POST /open-apis/drive/v1/permissions/:token/members` to grant doc/file access to a user or group chat.
- Added `_grant_permission()` helper to `FeishuToolBase` (shared across doc/drive tools).
- Added `grant_chat_access` parameter to `feishu_doc`: when `true`, auto-grants current group chat view access after doc creation.
- Added `docs/API.md` corrections based on Feishu Open Platform official docs (2026-02-26 verification):
  - `Permission Management` vs `Events & Callback` setup guide reorganized.
  - Two-layer permission model explanation (scopes ≠ resource access).
  - Drive: full multipart upload flow documented; Adler-32 checksum requirement noted.
  - Drive: `permission-member/create` API fully documented including group-chat limitations.
  - Calendar: corrected HTTP method from GET to POST for `calendar.v4.calendar.primary`.
  - Task: corrected API version — v2 is the latest (`POST /open-apis/task/v2/tasks`, updated 2025-06-04).
  - Updated "Current Implementation Limits" to reflect new capabilities.

### Fixed
- Fixed Feishu Drive upload checksum algorithm: replaced MD5 (`_md5_file`) with Adler-32 (`_adler32_file` via `zlib.adler32`). The Feishu `upload_all` API requires Adler-32 decimal string; MD5 caused API error `1062008`.
- Fixed Moonshot/Kimi requests failing with 404 (`/chat/completions`) when `apiBase` was configured without `/v1`.
- Fixed heartbeat false trigger: empty `HEARTBEAT.md` no longer fires a heartbeat notification (`heartbeat/service.py`).
- Fixed reflection prompt (`_REFLECT_PROMPT`) being visible to users — demoted from `role: "user"` to `role: "system"` so it is excluded from session history and never sent to the user (`agent/loop.py`).
- Fixed long-task max-iteration message: Chinese-language "processing limit" notification now correctly delivered to users (`agent/loop.py`).
- Fixed progress messages suppressed under default config: milestone and MCP heartbeat notifications now set `_tool_hint=False` so they pass through when `send_progress=True` (default) (`agent/loop.py`).
- Fixed queue position notification: elapsed time now computed from `start_time` (when task started processing) instead of `enqueue_time` (when task arrived) (`agent/loop.py`).
- Fixed `record_tool_feedback` never called: tool execution results now feed into `LessonStore` for self-improvement learning (`agent/loop.py`).
- Fixed stale HISTORY.md references: removed from `context.py`, `AGENTS.md`, `skills/memory/SKILL.md`, `commands.py` — aligned with RAM-first memory architecture.
- Fixed LLM API errors silently passed as normal replies: `finish_reason == "error"` now returns a user-friendly error message instead of raw error content (`agent/loop.py`).
- Fixed `_save_turn` filter for reflect prompt: updated to match new `role: "system"` and made tool result truncation configurable via `session_tool_result_max_chars` (`agent/loop.py`, `config/schema.py`).
- Fixed `cron.status()` called before `cron.start()` in gateway startup: moved into `async run()` after service initialization (`cli/gateway_cmd.py`).
- Fixed subagent missing paper tools: `PaperSearchTool`, `PaperGetTool`, `PaperDownloadTool` now registered in subagent with `paper_config` propagated from main agent (`agent/subagent.py`).
- Fixed cron `every`-type schedule losing continuity on restart: `_compute_next_run` now uses `last_run_at_ms + interval` when available, with `is not None` guard for zero values (`cron/service.py`).
- Fixed subagent defaults misaligned with main agent: `temperature` 0.7→0.1, `max_tokens` 4096→8192 (`agent/subagent.py`, `agent/loop.py`).
- Fixed `MessageBus` queues unbounded: added `maxsize=1000` default to prevent memory leak under load (`bus/queue.py`).
- Fixed skills frontmatter YAML boolean parsing: now returns Python `True`/`False` instead of truthy strings, preventing `always: false` skills from being force-loaded (`agent/skills.py`).
- Fixed queue notification metadata using `_progress` key: changed to distinct `_queue_notification` key with corresponding dispatch filter in `ChannelManager`, preventing double-filtering by `send_progress` config (`agent/loop.py`, `channels/manager.py`).
- Fixed `save_config()` writing config file with default permissions (644): now calls `chmod 0o600` after write to protect API keys from other OS users (`config/loader.py`).
- Fixed `AgentLoop.stop()` leaving consolidation tasks orphaned on shutdown: `stop()` now cancels all in-flight `_consolidation_tasks` before clearing the running flag (`agent/loop.py`).
- Fixed tool execution having no timeout: `ToolRegistry.execute()` now wraps each tool call with `asyncio.wait_for(timeout=120s)` to prevent one hung tool from blocking all agent processing (`agent/tools/registry.py`).
- Fixed MCP reconnect retrying on every message with no delay: `_connect_mcp()` now uses exponential backoff (2 s → 4 s → … → 60 s cap) via `_mcp_retry_after` / `_mcp_backoff_secs` fields (`agent/loop.py`).
- Fixed LiteLLM retry loop using linear backoff (`0.5 * attempt`): replaced with exponential backoff and random jitter (`2^(attempt-1) * 0.5–1.0 s`, capped at 30 s) (`providers/litellm_provider.py`).
- Fixed `json_repair.loads()` silently fixing malformed LLM tool arguments with no visibility: now logs a `WARNING` message including the tool name and the original malformed JSON when repair is triggered (`providers/litellm_provider.py`).
- Fixed cron `_execute_job()` having no execution timeout: now wrapped with `asyncio.wait_for(timeout=600s)` to prevent a stuck job from blocking the entire cron scheduler (`cron/service.py`).
- Fixed `MessageBus.publish_inbound()` blocking forever when inbound queue is full: replaced `await put()` with drop-oldest strategy (logs warning, evicts oldest message); `publish_outbound()` now uses a 10 s `wait_for` timeout and logs an error if outbound consumers stall (`bus/queue.py`).
- Fixed channel send failures silently dropping messages: `_dispatch_outbound()` now retries up to 3 times with linear backoff (0.5 s, 1.0 s) before logging an error and discarding (`channels/manager.py`).
- Fixed `ToolRegistry` 120 s outer timeout overriding per-MCP `toolTimeout`: `Tool` base class gains `execution_timeout` property (default `None`); `MCPToolWrapper` overrides it to `toolTimeout + 5 s`; `ToolRegistry.execute()` prefers per-tool timeout when set (`agent/tools/base.py`, `agent/tools/mcp.py`, `agent/tools/registry.py`).
- Fixed unbounded parallel session consolidations: `AgentLoop` now holds `asyncio.Semaphore(5)` used by every consolidation task to cap concurrency and prevent memory spikes (`agent/loop.py`).
- Fixed critically underestimated MCP tool timeouts in `configure_mcps.sh`: raspa2 60 s → 21 600 s (6 h), zeopp 300 s → 600 s, mofstructure/miqrophi 120 s → 600 s — RASPA GCMC/MD simulations routinely run 4-5+ hours (`scripts/configure_mcps.sh`).
- Fixed pdf2zh MCP timeout severely underestimated at 800 s: default raised to 3 600 s (1 h) in both `featherflow config pdf2zh` and `configure_mcps.sh` — translating a 50+ page paper can easily exceed 30 min depending on LLM response time (`cli/config_cmd.py`, `scripts/configure_mcps.sh`).
- Fixed `max_tool_iterations` default of 40 stopping complex scientific workflows mid-task: raised to 100. A RASPA GCMC + result parsing workflow can easily consume 30-50+ steps; 40 caused "⚠️ 已达到最大执行步数" errors. Configurable via `agents.defaults.maxToolIterations` in `config.json` (`config/schema.py`).
- Fixed `max_tokens` default of 8192 being too small for DeepSeek-R1 and extended Claude 4 responses: raised to 16 000 in `AgentDefaults`. LiteLLM itself has no cap; the 8192 ceiling was featherflow's own config default (`config/schema.py`).
- Fixed DeepSeek-R1 (deepseek-reasoner) multi-turn conversations breaking when used via the official DeepSeek API: `_sanitize_messages` now preserves `reasoning_content` in assistant message history when the provider spec sets `supports_reasoning_history=True`; DeepSeek spec updated accordingly. OpenRouter/gateway paths are unaffected — reasoning is still stripped there (`providers/registry.py`, `providers/litellm_provider.py`).
- Fixed agent returning a silent empty response when a reasoning model (e.g. DeepSeek-R1 via OpenRouter) exhausts `max_tokens` during thinking and emits no visible answer text: `_strip_think` returning `None` now logs a warning and surfaces "⚠️ 模型完成了推理但未输出最终回复（可能是 max_tokens 设置过低）" to the user instead of sending nothing (`agent/loop.py`).
- Fixed cron `_execute_job()` hardcoded 600 s timeout killing long-running scientific jobs: `CronService` now accepts `job_timeout` parameter (default 86 400 s / 24 h) read from `config.cron.job_timeout_seconds`; gateway plumbs the value from config (`cron/service.py`, `config/schema.py`, `cli/gateway_cmd.py`).

### Tests
- Added provider routing regression tests for API base normalization behavior in `tests/test_provider_routing.py`.
