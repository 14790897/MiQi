# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased]

### Added
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

### Tests
- Added provider routing regression tests for API base normalization behavior in `tests/test_provider_routing.py`.
