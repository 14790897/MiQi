# [0.2.0-dev.6](https://github.com/14790897/MiQi/compare/v0.2.0-dev.5...v0.2.0-dev.6) (2026-06-24)


### Bug Fixes

* **chat:** scroll to bottom on session open ([2fce763](https://github.com/14790897/MiQi/commit/2fce763fd7d395b959789600e060717ad0aba16c))

# [0.2.0-dev.5](https://github.com/14790897/MiQi/compare/v0.2.0-dev.4...v0.2.0-dev.5) (2026-06-24)


### Bug Fixes

* **desktop:** stop scroll jank — sidebar list reset & chat stream lock ([2644787](https://github.com/14790897/MiQi/commit/264478766b7a94c83f1b222920badae380d4b1bf))

# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]
### Added (2026-06-08)
- **Collapse tool call messages in chat**:
  - Added ability to collapse tool call messages in chat interface for cleaner conversation view
- **Per-session bwrap sandbox isolation** (`miqi/sandbox/`):
  - Added `manager.py` with FIFO-based sandbox eviction policy (max 10 sandboxes) for per-session bwrap isolation
- **Docs tab to Settings page**:
  - Added documentation tab to settings page for easy access to project documentation

### Added
- **KUN runtime migration — Bridge server integration**:
  - Modified `miqi/bridge/server.py` `BridgeState` to support KUN runtime:
    - Added `runtime_mode` field (initialized from `config.agents.defaults.runtime`, values `"legacy"` or `"kun"`).
    - `build_agent()` now reads runtime mode: when `"kun"`, creates a `GatewayKunRuntime` instead of legacy `AgentLoop`.
    - Extracted `_build_tool_registry(config)` helper function for shared ToolRegistry construction (filesystem/shell/web/papers).
    - `load_config()` auto-updates `runtime_mode` from config.
    - Bridge startup logs `Runtime mode: legacy` or `Runtime mode: kun`.
  - Modified `miqi/kun_runtime/migration_adapter.py` `GatewayKunRuntime`:
    - Added `_abort_event` (threading.Event) for compatibility with bridge's `abort_active()` / `handle_chat_send` abort logic.
  - No changes to bridge protocol, stdin/stdout JSON-line format, or frontend code.
  - All tests pass: 447 total (103 original + 344 new).

- **KUN runtime migration — Phase 10 (CLI/Gateway Integration)**:
  - Added `runtime` field to `AgentDefaults` config (`agents.defaults.runtime`, default `"legacy"`).
  - In `miqi/cli/gateway_cmd.py`: when `runtime == "kun"`, wire a `GatewayKunRuntime` as the agent instead of the legacy `AgentLoop`.
  - In `miqi/cli/agent_cmd.py`: same runtime-switch logic for both one-shot (`-m`) and interactive modes.
  - `GatewayKunRuntime` adapter provides `process_direct()` backed by KUN pipeline.
  - All tests pass: 447 total (103 original + 344 new).

### Fixed (2026-06-08)
- **Keep accepted files visible in referenced context**:
  - Fixed issue where accepted files were not visible in referenced context after acceptance

### Fixed (2026-05-25)
- **Strip `<think>` reasoning blocks from assistant messages** (`ChatConsole.tsx`):
  - Added `stripThinkBlocks()` helper that removes `</think>` blocks (case-insensitive, multi-line) before passing content to `MarkdownContent`/`ReactMarkdown`

### Fixed (2026-05-22)
- **Fixes and refactor for the "Merge Changes" button**:
  - Fixed silent snapshot failures (exceptions in `_write_snapshot_to` were swallowed)
  - Fixed merge incorrectly deleting newly created files (unlinking files that were created when the snapshot was empty)
  - Fixed files reappearing after switching sessions (`SessionManager.save` append-only mode prevented `_tool_hint` changes from being persisted)
  - Refactored sidebar file tracking: moved `_tool_hint` out of `conversation.jsonl` into a separate `tracked_files.json`; accept/revert now only remove JSON entries without rewriting conversation history
- **SkillHub CSP and file extension fixes**:
  - Fixed CSP in `index.html` blocking fetch requests to `https://skills.sixiangjia.de` — added to `connect-src`
  - Fixed `skills_create` and `skills_upload` in `bridge/server.py` writing `skill.yml` instead of `SKILL.md`, causing installed skills to be invisible to the `SkillsLoader`

### Added (2026-05-22)
- **SkillHub registry integration** (`apps/desktop/src/renderer/features/skills/SkillHubPage.tsx`):
  - New "SkillHub" tab in the Skills page, alongside the existing "本地技能" (Local Skills) tab
  - Browsing: loads the full skill index from `https://skills.sixiangjia.de/index.json` and displays skills in a card grid
  - Search: debounced (300ms) keyword search via `/api/search?q=<keyword>`
  - One-click install: fetches `SKILL.md` from the registry and writes it to the workspace skills directory via the existing `skills.upload` IPC channel
  - Installed status: already-installed skills show an "已安装" (Installed) badge; loading and error states have inline feedback
- **Conversation archiving**:
  - Added an archive button on the right side of each conversation in the sidebar (visible on hover); archived conversations are hidden from the list
  - Added an "Archived" tab in Settings to view, restore, and permanently delete archived conversations
  - Implemented via `.archived` marker files with zero runtime overhead

### Added (2026-05-20)
- **SetupWizard WSL2 Installation Guide Steps**:
  - Added `wsl2` step to wizard flow (environment → wsl2 → provider) to guide Windows users through WSL2 installation
  - Automatically detects WSL2 installation status: installed/version/distribution/running
  - One-click installation when not installed (UAC elevation) + manual installation instructions
  - Guides `wsl --install -d Ubuntu` when WSL is installed but no distribution exists
  - Prompts upgrade command for WSL1; automatically skips on non-Windows
  - Added IPC channels `wsl:check` / `wsl:install` and `WslCheckResult` type
- **Settings Page "Rerun Configuration Wizard" Button**:
  - Added "Reconfigure" section at the bottom of Settings → General tab, click to reopen SetupWizard
  - Controls AppShell `needsSetup` state via React props callback chain, no additional IPC channel required

### Added (2026-05-18)
- **Experience panel** (`apps/desktop/src/renderer/features/experience/`):
  - `ExperiencePage` component: Facts / Rules / History three tabs
  - `ExperienceStore` unified read interface, consolidating facts/rules/traces data
  - Experience IPC bridge handlers: `experience:list` / `delete` / `toggle` / `search`
- **MCPs management page** (`apps/desktop/src/renderer/features/mcps/`):
  - `MCPsPage` component: MCP service list with add/edit/delete actions
  - MCP list/upsert/delete IPC and bridge handlers
- **Skills CRUD**:
  - Desktop Skills page: create / upload / delete operations
  - `skill_manage` tool: agents can create, view, modify, and archive workspace skills
  - `skill_curator`: LLM-driven skill lifecycle management, automatically archives stale skills
- **Session management improvements**:
  - Session directory restructuring: each session stored in its own directory
  - Session-scoped working directory: file writes isolated to the current session directory
  - Automatically add `sessions/` to `.gitignore`
  - Session title support: sidebar shows custom titles
- **Trace task tracking system**:
  - Task Graph git-like self-improvement system (`miqi/agent/trace/`)
  - Full trace lifecycle: `trace_begin` → `record_step` → `trace_end`
  - CLI `miqi trace` command: `log` / `show` / `search` / `export` / `import`
  - Semantic search: vector similarity search based on `fastembed`
  - Context injection: automatically inject similar historical tasks into the system prompt
  - Nudge system: periodic reminders to agents to close open tasks
- **UI improvements**:
  - Settings page consolidation: providers / channels / approvals / cron merged into tabs
  - Sidebar improvements: session status filters, tracked file preview
  - Light theme color palette (WorkBench style)
  - Chat Console: session title, new chat button, context menu
  - Right-click context menus for chat / sessions / workspace / memory pages

### Added (2026-05-15)
- **Task Graph — git-like agent self-improvement system** (`miqi/agent/trace/`):
  - `TraceStore`: SQLite WAL-backed storage at `{workspace}/traces/TRACES.sqlite` with FTS5 full-text index and optional BLAKE3 content-addressed hashing (`miqi/agent/trace/store.py`).
  - `TaskTrace` / `TaskStep` data model with `trace_hash`, `goal`, `tool_calls`, `outcome`, `outcome_notes`, `embedding`, `parent_hash`, and `session_id` fields (`miqi/agent/trace/model.py`).
  - `Embedder`: lazy-loaded local embeddings via `fastembed` (`intfloat/multilingual-e5-small`, 384-dim, ONNX); cosine-similarity semantic search; graceful FTS5 fallback when `fastembed` is unavailable (`miqi/agent/trace/embedder.py`).
  - Three new agent tools: `task_begin` (open a trace), `task_end` (close with outcome + notes, returns similar historical traces), `trace_search` (semantic/FTS5 search of task history) (`miqi/agent/tools/task_trace.py`).
  - Context injection: up to 3 similar historical traces are prepended to `build_system_prompt()` when cosine similarity ≥ 0.65 (`miqi/agent/context.py`).
  - Nudge system: every `trace_nudge_interval` turns (default 8), a system message reminds the agent to call `task_end` if a task is open (`miqi/agent/loop.py`).
  - Auto-close: open tasks are closed as `partial` on `AgentLoop.stop()` (process shutdown) and on `/new` session reset (`miqi/agent/loop.py`).
  - Legacy lesson migration utility: converts `LESSONS.jsonl` entries to minimal `TaskTrace` records idempotently (`miqi/agent/trace/migrate.py`).
  - CLI sub-command `miqi trace` with `log`, `show`, `search`, `export`, `import` commands (`miqi/cli/trace_cmd.py`, `miqi/cli/commands.py`).
  - Six new config fields in `AgentSelfImprovementConfig`: `trace_enabled`, `embedding_model`, `trace_inject_top_k`, `trace_similarity_threshold`, `trace_nudge_interval`, `lessons_legacy_inject_enabled` (`miqi/config/schema.py`).
  - Optional dependency group `[trace]`: `fastembed>=0.6.0`, `numpy>=1.24.0`, `blake3>=0.4.0` (`pyproject.toml`).
- **`task_begin` / `task_end` / `trace_search` tool concurrency classification**: `trace_search` added to `_PARALLEL_SAFE_TOOLS`; `task_begin` and `task_end` added to `_PATH_SCOPED_TOOLS` (`miqi/agent/tools/registry.py`).
- **`execute_concurrent` `default_kwargs` forwarding**: added `default_kwargs` parameter to `ToolRegistry.execute_concurrent()` so `session_id` is correctly propagated to trace tools in the parallel dispatch path (`miqi/agent/tools/registry.py`).

### Fixed (2026-05-15)
- **`/new` session reset**: `session.clear()` was missing after successful archival and open-task auto-close; stale messages persisted into the new session (`miqi/agent/loop.py`, fix commit `347e9b5`).
- **Legacy lesson tests**: two tests in `test_tool_validation.py` assumed `record_tool_feedback()` / `record_user_feedback()` write lessons by default; they now explicitly opt in with `lessons_legacy_inject_enabled=True` to match the new Phase 5 kill-switch default (`tests/test_tool_validation.py`, fix commit `8b7e42a`).

### Changed (2026-05-15)
- **Legacy lesson injection disabled by default**: `MemoryStore` now defaults to `lessons_legacy_inject_enabled=False`; the `## Lessons` block is no longer included in `get_memory_context()` output unless explicitly opted in. Lesson write paths (`record_tool_feedback`, `record_user_feedback`) are gated by the same flag. Existing `LESSONS.jsonl` data is preserved on disk (`miqi/agent/memory/store.py`).

---

### Added (2026-05-14)
- **Memory tool** (`miqi/agent/tools/memory.py`): agent can now explicitly read/write/append long-term memory via the `memory` tool.
- **`session_search` tool** (`miqi/agent/tools/session_search.py`): FTS5-backed cross-session recall; lets the agent retrieve relevant past conversation snippets by natural language query.
- **`skill_manage` tool** (`miqi/agent/tools/skill_manage.py`): agent can create, view, patch, and archive workspace skills.
- **Nudge system**: periodic system-message reminders prompt the agent to persist memory and skills; interval configurable via `self_improvement.nudge_interval` (`miqi/agent/loop.py`).
- **System-prompt guidance** for memory, skills, and `session_search` tools injected into every turn (`miqi/agent/context.py`).
- **Skill curator** (`miqi/agent/memory/skill_curator.py`): LLM-driven lifecycle management — auto-archives stale skills after configurable threshold.
- **Lesson lifecycle management** (`miqi/agent/memory/lessons.py`): lessons now track `state` (`active` / `stale` / `archived`); auto-transition based on `lesson_stale_days` / `lesson_archive_days` config fields.
- **Lesson unlearn button and state badge** in MemoryPage desktop UI (`apps/desktop/src/renderer/features/memory/MemoryPage.tsx`).

### Added
- **Sidebar redesign**: Added session status filters to sidebar; introduced tracked file parsing and preview panel in chat console; refactored styling to use inline CSS variables over Tailwind arbitrary values; added debug logging for bridge stderr and runtime log flow (`apps/desktop/src/renderer/components/Sidebar.tsx`, `apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- **Python backend hot reload**: Added automatic hot reload for Python backend code changes. When running in development mode, changes to `.py` files in the `miqi/` directory automatically trigger a bridge restart (`apps/desktop/src/main/bridge.ts`).
- **File diff and revert functionality**: Added file snapshot system that saves original content before first write, enabling non-git diff comparison and revert operations (`miqi/bridge/server.py`).
- **Merge all changes**: Implemented merge functionality for all file changes with file tracking (`miqi/bridge/server.py`).
- **Bundled bridge executable support**: Added support for packaging `miqi-bridge.exe` with Electron app, enabling standalone desktop deployment without requiring Python installation (`apps/desktop/src/main/bridge.ts`, `apps/desktop/electron-builder.yml`).
- **Global right-click context menu**: Added to chat, sessions, workspace, and memory pages (`apps/desktop/src/renderer/components/ContextMenu.tsx`, `apps/desktop/src/main/index.ts`).

### Changed
- Updated README: Rewrote for MiQi Desktop with English content and added Chinese translation (`README.md`, `README_zh.md`).
- Adjusted code formatting: Set printWidth to 80 and reformatted code (`apps/desktop/.prettierrc`).

### Fixed
- Fixed file operation tool hint truncation: Skip truncation for file operation tool hints to preserve full file paths (`miqi/agent/loop.py`).
- Fixed chat input alignment: Adjusted chat input alignment and line height for better visual appearance (`apps/desktop/src/renderer/features/chat/ChatInput.tsx`).
- Fixed IPC bridge startup: Ensured bridge is started before IPC calls and improved accessibility (`apps/desktop/src/renderer/contexts/RuntimeContext.tsx`).

### Documentation
- Added documentation for MiQi Desktop app features and development setup (`README.md`).



### Added
- Added **Agent 配置** step (step 4) to Setup Wizard: lets first-time users set Agent name, workspace directory (with Browse button), and optional Brave Search API key before finalising setup (`apps/desktop/src/renderer/features/setup/SetupWizard.tsx`).
- Added finish screen summary card showing configured provider, agent name, workspace, and web-search state before saving (`apps/desktop/src/renderer/features/setup/SetupWizard.tsx`).
- Expanded `CONFIG_WRITE_INITIAL` IPC handler to write `agents.defaults.name`, `agents.defaults.workspace`, and `tools.web.search.apiKey` in addition to provider key and model (`apps/desktop/src/main/ipc/index.ts`).
- Expanded `window.miqi.setup.writeInitialConfig` preload API to accept `agentName`, `workspace`, and `braveApiKey` optional parameters (`apps/desktop/src/preload/index.ts`).
- Replaced single-view Settings page with a tabbed layout: **通用** (agent name, workspace, model, temperature, max tokens), **Web 工具** (Brave Search API key), **外观** (light/dark/system theme toggle), and **运行日志** (existing logs viewer) (`apps/desktop/src/renderer/features/settings/SettingsPage.tsx`).

### Fixed
- Fixed Electron desktop session not persisting assistant replies: `_run_agent_loop` returns `final_content` separately from `messages`; `_save_turn` never saw it.  
  Now explicitly appends the final assistant message to `session.messages` before `sessions.save()` (`miqi/agent/loop.py`).
- Fixed Electron desktop chat messages lost when switching navigation tabs: `ChatConsole` was conditionally rendered and unmounted on every tab change.  
  Component is now always mounted; hidden/shown via CSS `hidden` class so React state is preserved (`apps/desktop/src/renderer/App.tsx`).
- Fixed Electron desktop chat showing no prior history on app restart or session change: `ChatConsole` now loads session history from `window.miqi.sessions.get()` on mount and on `sessionKey` prop changes, converting JSONL records to UI messages (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- Fixed Electron desktop assistant responses appearing instantaneously with no visual feedback: added requestAnimationFrame-based typewriter animation that reveals reply text ~4 characters per frame; an animated cursor block is shown while the response is assembling (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).

### Added
- Added **New Session** button to Chat Console toolbar: sends `/new` to the agent bridge and clears the local message list (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- Added session key label to Chat Console toolbar so users can see which session is active (`apps/desktop/src/renderer/features/chat/ChatConsole.tsx`).
- M1 Electron desktop shell (`apps/desktop/`):
  - Python bridge (`miqi/bridge/server.py`) with stdin/stdout JSON-line protocol for chat streaming, session management, config CRUD, and provider operations.
  - Electron main process with secure BrowserWindow (contextIsolation + sandbox), BridgeManager for MiQi subprocess lifecycle, and 12 typed IPC handlers with zod validation.
  - Secure preload API via contextBridge exposing only typed RPC methods.
  - Setup wizard: 4-step flow (welcome → environment check → provider config with connection test → save & launch).
  - Chat console with streaming progress display, tool-call hints, code rendering, and copy support.
  - Session explorer: split-pane list and detail view with delete.
  - Settings: runtime logs viewer with auto-scroll, error highlighting, and export.
  - MiQi design system: warm neutral palette, Inter font bundled locally, Tailwind v4 + Radix primitives.

### Added
- **KUN runtime migration — Phase 0 (Analysis & Design)**:
  - Added comprehensive migration design document `docs/kun-runtime-migration.md`.
  - Document covers: architectural comparison (message-bus vs desktop workbench), 33-module KUN→Python mapping table, 15 capability adapter mappings, Pydantic data model definitions, 9-risk register, and an 11-phase migration plan with 11 recommended PR splits.
  - No code changes — read-only analysis phase.

- **KUN runtime migration — Phase 8 (AgentLoop Core)**:
  - Added `miqi/kun_runtime/loop.py` — KUN AgentLoop port: full `runTurn()` pipeline (drain steering → model_step → tool dispatch → compaction → loop), parallel-safe tool batching (max 3 concurrent reads), tool storm breaker integration, pipeline stage events, usage recording, interrupt/abort support.
  - Added `miqi/kun_runtime/compactor.py` — ContextCompactor with soft/hard/force thresholds, planCompaction + compact with summary generation.
  - Added `miqi/kun_runtime/context_estimator.py` — Token estimation (4 chars ≈ 1 token) for items and model requests.
  - Added `miqi/kun_runtime/history_repair.py` — healLoadedHistoryItems (normalization + repair) and repairModelHistoryItems (orphan tool result removal, stub injection).
  - Added `miqi/kun_runtime/history_hygiene.py` — applyRequestHistoryHygiene with line/byte/token budget trimming, signal-line preservation, single-line truncation.
  - Added `miqi/kun_runtime/token_economy.py` — normalizeTokenEconomyConfig, TOKEN_ECONOMY_INSTRUCTION constant.
  - Added `miqi/kun_runtime/tool_call_repair.py` — repairDispatchToolArguments with wrapper flattening, JSON string scavenging, oversized string truncation.
  - Added `miqi/kun_runtime/tool_storm_breaker.py` — ToolStormBreaker with windowed identical-call detection, exempt tools, reset.
  - Added `miqi/kun_runtime/auto_model_router.py` — resolveAutoModelRoute with candidate selection and fallback.

- **KUN runtime migration — Phase 9 (HTTP Runtime Composition)**:
  - Added `miqi/kun_runtime/auth.py` — BearerTokenAuth with insecure mode and token extraction.
  - Added `miqi/kun_runtime/runtime.py` — KunRuntime composition root (factory) wiring all Phase 1-8 components: EventBus, stores, services, compactor, gates, AgentLoop with lazy initialization.
  - Added `tests/kun_runtime/test_agent_loop_basic.py` with 12 tests: text completion, pipeline events, text deltas, item persistence, tool dispatch, multiple tool calls, error handling, interrupt/abort, model errors, compaction, tool storm suppression, usage accumulation.
  - Added `tests/kun_runtime/test_history_repair.py` with 26 tests: history healing (orphan removal, stub injection), history hygiene (oversized + single-line trimming), token economy, tool storm breaker (suppression, exempt, reset), tool call repair (wrapper flatten, JSON parsing, truncation), compactor (plan/compact/noop), context estimator, auto model router.
  - Added `tests/kun_runtime/test_http_runtime.py` with 11 tests: BearerTokenAuth, composition errors, full end-to-end turn lifecycle, multi-turn threads, thread listing, events sinceSeq replay.
  - All tests pass: 373 total (103 original + 270 new).

- **KUN runtime migration — Phase 7 (ApprovalGate & UserInputGate)**:
  - Added `miqi/kun_runtime/approval_gate.py` — `ApprovalGate` with async request/resolve/cancel_all, per-turn filtering, timeout→deny safety, idempotent resolve.
  - Added `miqi/kun_runtime/user_input_gate.py` — `UserInputGate` with async request/resolve/cancel_all, answers dict, timeout→cancelled fallback.
  - Added `tests/kun_runtime/test_agent_loop_gates.py` with 21 tests covering: ApprovalRequest lifecycle (resolve allow/deny, cancel, wait+timeout), ApprovalGate (parallel request+resolve, deny, cancel_all per-turn isolation), UserInputRequest lifecycle, UserInputGate (request+resolve with answers, cancel_all, nonexistent rejection).
  - All tests pass: 324 total (103 original + 221 new).

- **KUN runtime migration — Phase 6 (ToolHost adapter)**:
  - Added `miqi/kun_runtime/tool_host.py` — KUN ToolHost wrapping MiQi ToolRegistry:
    - `MiQiToolHost`: delegates `listTools(context)` and `execute(call, context)` to the registry with KUN-compatible ToolHostResult items.
    - Tool kind classification: `bash/exec` → command_execution, `write/edit/delete` → file_change, others → tool_call.
    - Concurrency: delegates to `ToolRegistry.should_parallelize()` with path-scoped parallel-safe rules; untrusted/never approval policies force sequential.
    - `FakeToolHost`: test double with configurable tool list, results, error tools, and call recording.
    - `ToolHostContext` dataclass with thread/turn/workspace/model info, approval/user-input callbacks, abort signal, and skill/memory/delegation policies.
  - Added `tests/kun_runtime/test_tool_host.py` with 24 tests covering: tool kind classification, list_tools (full listing + allowed-name filtering), execute (normal, read_file, error handling, unknown tool, result shape), concurrency (parallel-safe, same-path serialization, different-path parallelization, mixed, untrusted policy), and FakeToolHost (configured tools/results/errors, call recording, parallel classification).
  - All tests pass: 303 total (103 original + 200 new).

- **KUN runtime migration — Phase 5 (ModelClient adapter)**:
  - Added `miqi/kun_runtime/model_client.py` — KUN-compatible model client:
    - `MiQiModelClient` wraps `LLMProvider.chat()` with pseudo-streaming (Phase 5a): converts `ModelRequest` to provider messages, yields `assistant_reasoning_delta`, `assistant_text_delta`, `tool_call_complete`, `usage`, and `completed` chunks.
    - `FakeModelClient` test double with configurable text/reasoning/tool/usage/error responses and request recording.
    - `ModelRequest`, `ModelToolSpec`, `ModelStreamChunk` dataclasses matching KUN wire format.
    - TurnItem → OpenAI message conversion for all 10 item kinds.
    - Tool spec → OpenAI function definition conversion.
  - Added `tests/kun_runtime/test_model_client.py` with 27 tests covering: FakeModelClient text/tools/reasoning/usage/error/recording, 6 item→message conversions, 4 build_messages scenarios, tool spec conversion, and 7 MiQiModelClient integration tests (text, reasoning, tools, usage, provider error, API error, tool passing).

- **Security fix — Phase 3 stores**: Added `os.chmod(0o600)` to all file writes in `FileThreadStore.upsert()`, `FileSessionStore.append_item()`, `FileSessionStore.append_event()`, and `FileSessionStore._rewrite_items_file()` to restrict session/thread files to owner-only (matching MiQi's existing security practice in `config/loader.py` and `session/manager.py`).

- **KUN runtime migration — Phase 4 (TurnService, ThreadService, Cancellation, MigrationAdapter)**:
  - Added `miqi/kun_runtime/cancellation.py` — `CancellationToken` (asyncio.Event-based cooperative cancellation) and `InflightTracker` (running operation accounting per thread/turn).
  - Added `miqi/kun_runtime/thread_service.py` — `ThreadService` with create/get/list/update/delete/fork, event recording for thread_created/thread_updated.
  - Added `miqi/kun_runtime/turn_service.py` — `TurnService` with full lifecycle: start_turn (creates turn + user item, abort token, inflight tracking), finish_turn (completed/failed/aborted with item finalization), interrupt_turn (abort token + optional discard), steer_turn (drain steering), apply_item, update_item, get_turn.
  - Added `miqi/kun_runtime/migration_adapter.py` — deterministic `session_key → threadId` bidirectional mapping with register/clear support.
  - Added `tests/kun_runtime/test_turn_service.py` with 38 tests covering: CancellationToken lifecycle, InflightTracker accounting, session→thread mapping determinism, ThreadService CRUD/fork/events, TurnService start/finish/interrupt/steer/items/cancellation lifecycle.
  - All tests pass: 252 total (103 original + 149 new).

- **KUN runtime migration — Phase 3 (ThreadStore, SessionStore, UsageService)**:
  - Added `miqi/kun_runtime/stores.py` — file-based persistent stores:
    - `FileThreadStore`: one JSON file per thread (upsert/get/delete/list), atomic write via os.replace.
    - `FileSessionStore`: append-only JSONL for TurnItems and runtime events (load_items, append_item, update_item, rewrite_items, append_event, load_events_since).
    - All paths relative to configurable `data_dir` — tests use `tmp_path` for isolation.
  - Added `miqi/kun_runtime/usage.py` — `UsageService` for per-thread token/cost accumulation with token economy savings tracking, seed/reset, and thread isolation.
  - Added `tests/kun_runtime/test_stores.py` with 26 tests covering: thread CRUD, persistence across instances, session item append/load/update/rewrite ordering, event sinceSeq filtering, corrupt line handling, thread isolation, and usage accumulation/savings/seed/reset.
  - All tests pass: 214 total (103 original + 111 new).

- **KUN runtime migration — Phase 2 (EventBus, SSE, RuntimeEventRecorder)**:
  - Added `miqi/kun_runtime/event_bus.py` — in-memory per-thread event bus with monotonically increasing seq, append, history replay, sinceSeq filtering, and async subscribe (AsyncIterator).
  - Added `miqi/kun_runtime/event_recorder.py` — RuntimeEventRecorder that auto-assigns seq + timestamp and records to the event bus.
  - Added `miqi/kun_runtime/sse.py` — SSE encoder producing KUN-compatible format (`id: <seq>\nevent: <kind>\ndata: <json>\n\n`), plus comment and [DONE] markers.
  - Added `tests/kun_runtime/test_event_bus.py` with 27 tests covering: seq monotonicity, per-thread isolation, append ordering, history/sinceSeq filtering, async subscribe with replay + live events, recorder seq/timestamp auto-assignment, SSE field format, JSON round-trip, and special characters.

- **KUN runtime migration — Phase 1 (Contracts & Event Model)**:
  - Added `miqi/kun_runtime/` package with `contracts.py` — Pydantic v2 models for the complete KUN data model:
    - 10 `TurnItem` variants (user_message, assistant_text, assistant_reasoning, tool_call, tool_result, approval, user_input, compaction, review, error) as discriminated union.
    - 32 `RuntimeEvent` variants (thread/turn lifecycle, item lifecycle, streaming deltas, tool events, approval/user-input gates, compaction, goal/todo, pipeline stage, usage, error, heartbeat) as discriminated union.
    - Thread/Turn models: `ThreadRecord`, `ThreadSummary`, `Turn`, `ThreadGoal`, `ThreadTodoList`.
    - Request/Response models: `StartTurnRequest/Response`, `SteerTurnRequest`, `InterruptTurnRequest/Response`, `CompactRequest/Response`, `CreateThreadRequest`, `ForkThreadRequest`, `UpdateThreadRequest`, `SetThreadGoalRequest`, `ApprovalDecisionRequest`, `UserInputResolveRequest`.
    - Supporting types: `UsageSnapshot`, `ModelToolSpec`, `ModelCapabilityMetadata`, 11 enums, `PipelineStage` literal with labels.
    - All models use camelCase field names matching KUN HTTP/SSE payloads for wire compatibility.
  - Added `tests/kun_runtime/test_contracts.py` with 58 tests covering: serialization round-trips, enum validation, discriminator dispatch, default values, field constraints (min_length, ge), empty/id rejection, and `ThreadTodoList` at-most-one-in-progress invariant.

### Documentation
- Added uv installation instructions to README, getting-started, developer-guide, and contributing docs; uv is the recommended install method, pip retained as fallback.
- Updated `maxTokens` default from `16000` to `8192` in `docs/configuration.md` to match code.
- Added GitHub Copilot (OAuth) to README LLM Providers feature list.
- Fixed `ff agent` → `miqi agent` in historical changelog entries.
- Updated README and project docs to match current code paths and schema defaults:
  - corrected workspace-relative memory/session storage paths (`<workspace>/memory`, `<workspace>/sessions`)
  - documented current packaged gateway scope (Feishu wired today; other channel adapters remain extension modules)
  - refreshed config defaults for memory, sessions, self-improvement, heartbeat, cron, and shell execution
  - documented MCP `lazy`, `description`, `headers`, and environment-inheritance behavior
  - clarified that SQLite session storage, provider fallback chains, command approval, and smart routing exist as shipped modules/helpers but are not all enabled by default in the packaged CLI/gateway path

### Added
- Added `paper-research` skill (`miqi/skills/paper-research/SKILL.md`):
  - Full workflow: `paper_search` → `paper_download` → `translate_pdf` → summarize with references.
  - Covers scheduled briefing scenarios (cron + feishu delivery).
  - Includes `web_search` fallback for news and preprints not indexed in Semantic Scholar.
- Added `feishu-report` skill (`miqi/skills/feishu-report/SKILL.md`):
  - Format decision table: plain text / card message / Feishu Doc / calendar event / task.
  - Covers `send_message`, `send_card_message`, `create_document` + `write_document_markdown`, `create_calendar_event`, `create_task`.
  - Includes user identity resolution via `resolve_users_by_name` and `get_chat_members`.
- Added `workspace-cleanup` skill (`miqi/skills/workspace-cleanup/SKILL.md`):
  - Organizes `~/.miqi/workspace` into structured `artifacts/` subdirectories.
  - Archives files older than 30 days to `archive/YYYY-MM/`.
  - Defines sacred directories (memory/, skills/, sessions/, system .md files) that are never touched.

### Changed
- Updated `cron` skill (`miqi/skills/cron/SKILL.md`):
  - Corrected timezone fallback documentation: without `tz`, cron expressions are now evaluated in **UTC** (not server local time).
  - Updated `at` mode examples to always include timezone offset (e.g. `+08:00`) or explicit `tz=`.
  - Added China Standard Time (`Asia/Shanghai`) examples to time expression table.
- Updated `cron` tool parameter descriptions (`miqi/agent/tools/cron.py`):
  - `message`: clarified it is the full task prompt executed at trigger time, not just a label.
  - `cron_expr`: added explicit warning that expressions default to UTC; must pass `tz=` for non-UTC users.
  - `at`: updated example to include timezone offset; documents `tz=` fallback for naive datetimes.
  - `tz`: extended to apply to both `cron_expr` and `at` modes.

### Fixed
- Fixed `max_tokens` default of 16000 exceeding DeepSeek API maximum (8192 output tokens): lowered `AgentDefaults.max_tokens` back to 8192. After migration from litellm (which auto-capped per model) to direct SDK calls (which do not), the previous 16000 default caused 400 BadRequest errors on DeepSeek (`config/schema.py`).
- Fixed `_match_provider()` using bare `api_key` truthiness check, preventing `is_local` providers (vLLM, Ollama Local) from matching when they use `api_base` instead of `api_key`: replaced with `_is_configured()` helper that checks both `api_key` and `api_base` (`config/schema.py`).
- Fixed `build_provider()` not passing `provider_name` and `default_model` to fallback-chain provider constructors, causing fallback providers to use wrong endpoints and model names (`config/schema.py`).
- Fixed `_make_provider()` in onboard CLI requiring `api_key` for `is_local` providers (vLLM, Ollama Local) that only need `api_base`: added `is_local` exemption to the api_key requirement check (`cli/commands.py`).
- Fixed `AnthropicProvider` passing empty-string `api_key` to SDK instead of `None`, preventing the SDK from falling back to `ANTHROPIC_API_KEY` environment variable (`providers/anthropic_provider.py`).
- Fixed cron `at` mode silently using server local timezone for naive datetime strings: naive datetimes now interpreted as UTC when no `tz` is provided; `tz=` can be passed together with `at=` to override (`miqi/agent/tools/cron.py`).
- Fixed `tz` parameter rejected when combined with `at`: removed erroneous validation that blocked `tz` + `at` combinations (`miqi/agent/tools/cron.py`).
- Fixed cron `cron` mode using unpredictable server local timezone as fallback: now falls back to UTC for deterministic behavior across deployment environments (`miqi/cron/service.py`).
- Fixed `miqi agent` mode (CLI) silently ignoring all cron jobs: `on_job` callback was never registered and `cron.start()` was never called; both now wired correctly in `cli/agent_cmd.py`.
- Fixed `miqi agent` mode not propagating `job_timeout` from config to `CronService` (`miqi/cli/agent_cmd.py`).

### Removed
- Removed `clawhub` skill (`miqi/skills/clawhub/`) — not applicable to this deployment.

---

## [Unreleased — previous]

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
  - `miqi/cli/onboard.py`
  - `miqi/cli/agent_cmd.py`
  - `miqi/cli/gateway_cmd.py`
  - `miqi/cli/management.py`
- Added core regression tests:
  - `tests/test_agent_loop_core.py`
  - `tests/test_cron_service_core.py`
- Added project documentation:
  - `docs/API.md`
  - `docs/DEVELOPER_GUIDE.md`
  - `docs/ARCHITECTURE.md`
  - `CONTRIBUTING.md`
- Added Feishu business tools in `miqi/agent/tools/feishu.py`:
  - `feishu_doc` for cloud doc creation and optional plain-text write.
  - `feishu_calendar` for calendar event creation and attendee assignment.
  - `feishu_task` for task creation with group-member assignment.
  - `feishu_drive` for Drive folder creation (`create_folder` / `ensure_folder_path`) and workspace file uploads.
  - `feishu_handoff` as a generic collaboration handoff layer that orchestrates delivery steps.
- Added Feishu mention metadata extraction (`sender_open_id`, `mentions`) in `miqi/channels/feishu.py`.
- Added Feishu tool usage guidance in `miqi/templates/TOOLS.md`.
- Added `paper_download` tool in `miqi/agent/tools/papers.py` to download PDFs into workspace.
- Added documentation updates for Feishu collaboration + paper delivery workflow:
  - README feature/capability updates
  - API docs for `paper_download`, `feishu_drive`, and `feishu_handoff`
  - Feishu backend permission checklist in `docs/API.md`

### Changed
- Refactored `miqi/cli/commands.py` into an entry/compatibility layer that registers split command modules.
- Refactored arXiv XML parsing in `miqi/agent/tools/papers.py` by extracting shared `_parse_arxiv_entry` logic.
- Replaced remaining built-in `print()` calls with `loguru.logger` warnings in `miqi/config/loader.py`.
- Split memory implementation into package modules with `MemoryStore` facade in `miqi/agent/memory/store.py`.
- Normalized provider `api_base` handling in `LiteLLMProvider` to auto-fill missing default base paths (for example `/v1`, `/api/v1`) when users provide host-only URLs, while preserving explicit custom paths.
- Updated `AgentLoop` tool wiring in `miqi/agent/loop.py` to:
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
- Fixed pdf2zh MCP timeout severely underestimated at 800 s: default raised to 3 600 s (1 h) in both `miqi config pdf2zh` and `configure_mcps.sh` — translating a 50+ page paper can easily exceed 30 min depending on LLM response time (`cli/config_cmd.py`, `scripts/configure_mcps.sh`).
- Fixed `max_tool_iterations` default of 40 stopping complex scientific workflows mid-task: raised to 100. A RASPA GCMC + result parsing workflow can easily consume 30-50+ steps; 40 caused "⚠️ 已达到最大执行步数" errors. Configurable via `agents.defaults.maxToolIterations` in `config.json` (`config/schema.py`).
- Fixed `max_tokens` default of 8192 being too small for DeepSeek-R1 and extended Claude 4 responses: raised to 16 000 in `AgentDefaults`. LiteLLM itself has no cap; the 8192 ceiling was miqi's own config default (`config/schema.py`).
- Fixed DeepSeek-R1 (deepseek-reasoner) multi-turn conversations breaking when used via the official DeepSeek API: `_sanitize_messages` now preserves `reasoning_content` in assistant message history when the provider spec sets `supports_reasoning_history=True`; DeepSeek spec updated accordingly. OpenRouter/gateway paths are unaffected — reasoning is still stripped there (`providers/registry.py`, `providers/litellm_provider.py`).
- Fixed agent returning a silent empty response when a reasoning model (e.g. DeepSeek-R1 via OpenRouter) exhausts `max_tokens` during thinking and emits no visible answer text: `_strip_think` returning `None` now logs a warning and surfaces "⚠️ 模型完成了推理但未输出最终回复（可能是 max_tokens 设置过低）" to the user instead of sending nothing (`agent/loop.py`).
- Fixed cron `_execute_job()` hardcoded 600 s timeout killing long-running scientific jobs: `CronService` now accepts `job_timeout` parameter (default 86 400 s / 24 h) read from `config.cron.job_timeout_seconds`; gateway plumbs the value from config (`cron/service.py`, `config/schema.py`, `cli/gateway_cmd.py`).

### Tests
- Added provider routing regression tests for API base normalization behavior in `tests/test_provider_routing.py`.
