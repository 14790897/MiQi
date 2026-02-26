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

## Feishu Open Platform Permissions (Backend Setup)

Enable bot capability and event subscription for message intake (for example, `im.message.receive_v1`), then grant API permissions required by enabled tools.

The following Feishu APIs are used directly by FeatherFlow:
- `docx.v1.document.create`
- `docx.v1.document_block_children.create` (when writing plain text content)
- `calendar.v4.calendar.primary` (when calendar ID is not provided)
- `calendar.v4.calendar_event.create`
- `calendar.v4.calendar_event_attendee.create` (when attendees are provided)
- `task.v2.task.create`
- `drive.v1.file.create_folder`
- `drive.v1.file.list`
- `drive.v1.file.upload_all`
- `im.v1.chat_members.get` (for group member resolution by name)

Because permission names/scopes can differ by tenant and Feishu console language, use the API names above in the Open Platform permission search and publish the app after updates.

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
