# FeatherFlow API Documentation

## CLI Overview

Entry command: `featherflow`

Common commands:
- `featherflow onboard`: Initialize config and workspace
- `featherflow agent`: Interact with the agent (one-shot or interactive)
- `featherflow gateway`: Start gateway and channel services
- `featherflow status`: Show runtime status

Subcommand groups:
- `featherflow channels status`
- `featherflow memory ...`
- `featherflow session compact ...`
- `featherflow cron ...`
- `featherflow provider login ...`

## Tool Invocation Interface (Internal)

Tools are executed through `ToolRegistry` and return string results:
- Filesystem: `read_file` / `write_file` / `edit_file` / `list_dir`
- Shell: `exec`
- Web: `web_search` / `web_fetch`
- Papers: `paper_search` / `paper_get` / `paper_download`
- Feishu collaboration: `feishu_doc` / `feishu_calendar` / `feishu_task` / `feishu_drive` / `feishu_handoff`
- Messaging: `message`
- Sub-agent: `spawn`
- Scheduler: `cron` (when `CronService` is enabled)

Notes:
- Feishu tools are auto-registered only when Feishu credentials are configured.
- Feishu business tools run only in Feishu channel context (group/private chat messages from Feishu).

## Web Tool Configuration

Config path: `tools.web`
- `search.provider`: `brave` | `ollama` | `hybrid`
- `fetch.provider`: `builtin` | `ollama` | `hybrid`
- Tunables include `search.maxResults`, `fetch.ollamaApiBase`, and `fetch.ollamaApiKey`

## Papers Tool Configuration

Config path: `tools.papers`
- `provider`: `hybrid` | `semantic_scholar` | `arxiv`
- `semanticScholarApiKey`
- `timeoutSeconds`
- `defaultLimit` / `maxLimit`

`paper_download` behavior:
- Accepts either `url` or `paperId` (resolved to open-access PDF URL via `paper_get`).
- Writes output inside workspace and supports optional `outPath`.
- Applies download size limit (`maxSizeMB`) and timeout controls.
- Detects common paywall/login/interstitial HTML responses and returns structured error payloads with `paywall_suspected=true` instead of saving invalid `.pdf` files.

## Feishu Collaboration Tools

### Identity Resolution in Group Chats

For `feishu_task.assignees` and `feishu_calendar.attendees`, user resolution order is:
1. direct `open_id`
2. current message mentions
3. group member exact-name match
4. group member fuzzy-name match

When ambiguous, tools return candidate lists and fail safely; they do not auto-pick a user.

`feishu_task` sender fallback:
- if `assignees` is omitted, fallback assignee is the message sender (`sender_open_id`) when available.

### Drive + Handoff

- `feishu_drive` supports `create_folder`, `ensure_folder_path`, `upload_file`, and `upload_files`.
- Upload paths are restricted to workspace for safety.
- `feishu_handoff` is a generic orchestration layer that can combine:
  - folder preparation
  - artifact uploads
  - summary doc creation
  - task creation
  - calendar event creation
  - optional `dry_run` and `continue_on_error`

## Feishu Open Platform Setup (Latest Verification: 2026-02-26)

### Permission Management (Scopes)

In Feishu Open Platform, open **Permission Management** and grant scopes for enabled capabilities.

Minimum scopes for current FeatherFlow flow:
- Cloud docs create/write: `docx:document`
- Calendar create/invite: `calendar:calendar`
- Tasks create: `task:task`
- Drive folders/files/upload/share: `drive:drive`
- Drive permission management: `drive:drive.permission` (for `permission-member/create`)
- Group member resolution (`im.v1.chat_members.get`): `im:chat.group_info:readonly` (or broader `im:chat`)
- Message intake in groups:
  - `im:message.group_at_msg` (messages that @mention bot)
  - `im:message.group_msg` (all group messages; enable only if needed)

**Two-layer permission model (important)**:
- **Scopes** = what APIs the app is allowed to call (granted in developer console)
- **Resource access** = whether the specific doc/file/folder is shared with the app/group
  - Scopes alone are NOT enough; the cloud doc/file must also be shared with the app or group
  - Recommended: create docs inside a team shared folder, or call `permission-member/create` after creation

Notes:
- Scope names shown in console can vary slightly by tenant language/version. Search by API name if needed.
- After changing scopes, publish the app again.

### Events & Callback

In **Events & Callback**:
- Add event `im.message.receive_v1`.
- For self-built apps, Feishu supports WebSocket long connection mode (no public callback URL required).
- After adding/updating events, publish the app again.

### API Endpoints (Latest Docs)

Docs:
- `POST /open-apis/docx/v1/documents` (`docx.v1.document.create`). Last updated: 2025-07-17.
- `POST /open-apis/docx/v1/documents/:document_id/blocks/:block_id/children` (`docx.v1.document_block_children.create`). Last updated: 2025-07-17.

Calendar:
- `POST /open-apis/calendar/v4/calendars/primary` (`calendar.v4.calendar.primary`) — **method is POST, not GET**. Last updated: 2024-07-16.
- `POST /open-apis/calendar/v4/calendars/:calendar_id/events` (`calendar.v4.calendar_event.create`)
- `POST /open-apis/calendar/v4/calendars/:calendar_id/events/:event_id/attendees` (`calendar.v4.calendar_event_attendee.create`)

Tasks:
- Latest: **Task v2** — `POST /open-apis/task/v2/tasks` (`task.v2.task.create`). Last updated: 2025-06-04.
- FeatherFlow correctly uses `task.v2.task.create`; **do not downgrade to v1**.
- Assignees are set via the `members` field in the create request body (no separate add_members call needed for initial assignment).

Drive — Upload:
- **Small files (≤ 20 MB)**: `POST /open-apis/drive/v1/files/upload_all` (`drive.v1.file.upload_all`).
  - Hard limit: 20 MB per Feishu official docs (2024-10-23). Empty files are rejected.
  - Checksum parameter expects **Adler-32** (decimal string), NOT MD5/SHA. (FeatherFlow now uses `zlib.adler32`.)
  - Rate limit: 5 QPS, 10,000 times/day.
- **Large files (> 20 MB)**: must use multipart upload — 3-step flow:
  1. `POST /open-apis/drive/v1/files/upload_prepare` (`drive.v1.file.upload_prepare`) → returns `upload_id`, `block_size`, `block_num`.
  2. `POST /open-apis/drive/v1/files/upload_part` (`drive.v1.file.upload_part`) × block_num.
  3. `POST /open-apis/drive/v1/files/upload_finish` (`drive.v1.file.upload_finish`) → returns `file_token`.
  - FeatherFlow `feishu_drive` now auto-routes to multipart for files > 20 MB.

Drive — Folders & Files:
- `POST /open-apis/drive/v1/files/create_folder` (`drive.v1.file.create_folder`)
- `GET /open-apis/drive/v1/files` (`drive.v1.file.list`)

Drive — Permissions:
- **Add collaborator** (user or group): `POST /open-apis/drive/v1/permissions/:token/members` (`drive.v1.permission_member.create`). Last updated: 2025-07-03.
  - `member_type`: `openid` (user), `openchat` (group chat), `unionid`, etc.
  - `perm`: `view`, `edit`, `full_access`.
  - To add a group as collaborator with `tenant_access_token`, **the app must already be in the group as a bot**.
  - **Folder-level app grants via this API do not work** (grant succeeds but has no effect); use group-based access instead.
  - FeatherFlow exposes this as `feishu_drive` action `grant_permission`.
- **Update public sharing**: `PATCH /open-apis/drive/v1/permissions/:token/public` (`drive.v1.permission_public.patch`). Last updated: 2025-07-03.

IM:
- `GET /open-apis/im/v1/chats/:chat_id/members` (`im.v1.chat_members.get`)

### Current Implementation Limits (Important)

- `feishu_doc` currently writes plain text paragraph blocks only; rich-text rendering is not implemented yet.
- Rich text is supported by Feishu Docx blocks (heading/list/code/quote/todo + inline styles), but FeatherFlow does not yet map markdown/content structure into those block types.
- `feishu_doc` now supports optional `grant_chat_access: true` to auto-grant current group view access after doc creation.
- `feishu_drive` auto-selects upload method based on file size: `upload_all` for ≤ 20 MB, multipart for > 20 MB.
- `feishu_drive` action `grant_permission` supports granting doc/file access to a user or group post-upload.
- **Root folder (`parent_folder_token` = `"root"`)** may not be writable with `tenant_access_token`. Best practice: have the admin create a shared folder and configure its token as `delivery_folder_token` in your deployment.
- Calendar: Using `tenant_access_token` queries the **application's primary calendar**, not any individual user's personal calendar. To write to a user's personal calendar, `user_access_token` (OAuth) is required.

## Cron Data Model

Core types are defined in `featherflow/cron/types.py`:
- `CronSchedule`: `at` / `every` / `cron`
- `CronPayload`: Job message and delivery config
- `CronJob`: Job entity with runtime state and timestamps

Default store path is under runtime data directory: `cron/jobs.json`.

## Session and Memory

- Session: `SessionManager` handles persistence and compaction of conversation history.
- Memory: `MemoryStore` provides snapshot memory, short-term memory, pending items, and self-improvement lessons.

Primary memory management commands:
- `featherflow memory status|flush|compact|list|delete`
- `featherflow memory lessons status|list|enable|disable|delete|compact|reset`
