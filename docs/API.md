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
- Messaging: `message`
- Sub-agent: `spawn`
- Scheduler: `cron` (when `CronService` is enabled)

Notes:
- MCP tools are registered on first message when `tools.mcpServers` is configured.

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
