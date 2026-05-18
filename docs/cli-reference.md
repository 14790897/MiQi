# CLI Reference

## Overview

Entry command: `miqi`

```
miqi [OPTIONS] COMMAND [ARGS]...
```

All commands support `--help` for usage details.

---

## Agent & Gateway

| Command | Description |
|---|---|
| `miqi onboard` | Interactive setup wizard — creates `~/.miqi/config.json` |
| `miqi agent` | Start an interactive chat session |
| `miqi agent -m "<prompt>"` | Send a single prompt and exit |
| `miqi gateway` | Run the long-running gateway (channels + cron) |

---

## Status & Diagnostics

| Command | Description |
|---|---|
| `miqi status` | Show runtime and provider status |
| `miqi channels status` | Show channel connection status |

---

## Memory Management

| Command | Description |
|---|---|
| `miqi memory status` | Show memory snapshot stats and flush state |
| `miqi memory flush` | Force-persist pending memory updates immediately |
| `miqi memory compact [--max-items N]` | Prune long-term snapshot to at most N items |
| `miqi memory list [--limit N] [--session S]` | Browse long-term snapshot entries |
| `miqi memory delete <id>` | Remove a snapshot entry by ID |
| `miqi memory lessons status` | Show self-improvement lesson stats |
| `miqi memory lessons list` | List lessons (filter by `--scope`, `--session`, `--limit`) |
| `miqi memory lessons enable <id>` | Re-enable a disabled lesson |
| `miqi memory lessons disable <id>` | Suppress a lesson from future prompts |
| `miqi memory lessons delete <id>` | Permanently remove a lesson |
| `miqi memory lessons compact [--max-lessons N]` | Prune lessons to at most N entries |
| `miqi memory lessons reset` | Wipe all lessons |

---

## Session Management

| Command | Description |
|---|---|
| `miqi session compact --session <id>` | Compact a single conversation session by ID |
| `miqi session compact --all` | Compact all stored sessions |

---

## Trace

| Command | Description |
|---|---|
| `miqi trace log` | Show recent task execution history |
| `miqi trace show <id>` | Show details of a specific task trace |
| `miqi trace search <query>` | Full-text search across task traces |
| `miqi trace export` | Export task traces as a JSONL file |
| `miqi trace import <file>` | Import task traces from a JSONL file |

---

## Cron Scheduler

| Command | Description |
|---|---|
| `miqi cron list` | List all scheduled jobs |
| `miqi cron add` | Add a new scheduled job interactively |
| `miqi cron run <id>` | Trigger a job manually |
| `miqi cron enable <id>` | Enable a job (use `--disable` flag to disable) |
| `miqi cron remove <id>` | Remove a job permanently |

---

## Configuration

| Command | Description |
|---|---|
| `miqi config show` | Print all non-default config values |
| `miqi config provider <name>` | Set or update a provider's API key / base URL |
| `miqi config feishu` | One-shot Feishu channel + feishu-mcp setup |
| `miqi config pdf2zh` | Configure pdf2zh MCP server (auto-fills LLM credentials) |
| `miqi config mcp list` | List all configured MCP servers |
| `miqi config mcp add <name>` | Add or update an MCP server (stdio or HTTP, supports `--lazy` and `--description`) |
| `miqi config mcp remove <name>` | Remove an MCP server |
| `miqi config sync-llm` | Sync LLM provider credentials to MCP servers (pdf2zh, etc.) |

---

## Built-in Tool Reference

Tools are executed through `ToolRegistry` and return string results.

### Filesystem Tools

| Tool | Description |
|---|---|
| `read_file` | Read file contents from workspace |
| `write_file` | Write or overwrite a file |
| `edit_file` | Apply targeted edits to an existing file |
| `list_dir` | List directory contents |

### Shell Tool

| Tool | Description |
|---|---|
| `exec` | Run a shell command. Subject to deny-list safety guards, credential env stripping, optional workspace restriction, and a configurable timeout. |

### Web Tools

| Tool | Description |
|---|---|
| `web_search` | Search the web (Brave or Ollama backend) |
| `web_fetch` | Fetch and extract content from a URL |

Web tools have SSRF protection: requests to private/loopback/link-local IP ranges are rejected.

**Web config path:** `tools.web`

| Key | Description |
|---|---|
| `search.provider` | `brave` \| `ollama` \| `hybrid` |
| `search.maxResults` | Maximum number of results |
| `fetch.provider` | `builtin` \| `ollama` \| `hybrid` |

### Paper Research Tools

| Tool | Description |
|---|---|
| `paper_search` | Search academic papers (Semantic Scholar + arXiv) |
| `paper_get` | Get paper metadata and open-access PDF link |
| `paper_download` | Download a paper PDF into the workspace |

`paper_download` accepts either `url` or `paperId`. It applies download size limits, timeouts, and detects paywall/login pages — returning `paywall_suspected=true` instead of saving invalid files.

**Papers config path:** `tools.papers`

| Key | Description |
|---|---|
| `provider` | `hybrid` \| `semantic_scholar` \| `arxiv` |
| `semanticScholarApiKey` | Semantic Scholar API key |
| `timeoutSeconds` | Request timeout |
| `defaultLimit` / `maxLimit` | Result count limits |

### Messaging Tool

| Tool | Description |
|---|---|
| `message` | Send a message to a channel or user |

### Sub-agent Tool

| Tool | Description |
|---|---|
| `spawn` | Spawn a child agent for a sub-task |

### Memory Tool

| Tool | Description |
|---|---|
| `memory` | Save, recall, list, or delete items in the agent's long-term snapshot memory |

### Skill Management Tool

| Tool | Description |
|---|---|
| `skill_manage` | List, view, create, patch, or archive reusable skill files in the workspace `skills/` directory |

### Session Search Tool

| Tool | Description |
|---|---|
| `session_search` | Full-text search across persisted session history using SQLite FTS5 |

### Task Trace Tools

| Tool | Description |
|---|---|
| `task_begin` | Mark the start of a tracked task with a goal description |
| `task_end` | Mark the end of a tracked task with outcome and summary |
| `trace_search` | Search across recorded task traces by keyword or embedding similarity |

### Cron Tool

| Tool | Description |
|---|---|
| `cron` | Schedule a task (available when `CronService` is running) |

**Cron schedule modes:**

| Mode | Example | Description |
|---|---|---|
| `at` | `"2026-04-15T09:00:00+08:00"` | Run once at a specific datetime |
| `every` | `"1h"`, `"30m"` | Run on an interval |
| `cron` | `"0 9 * * 1-5 tz=Asia/Shanghai"` | Full cron expression |

!!! warning "Timezone"
    Cron expressions default to **UTC**. Pass `tz=Asia/Shanghai` (or another IANA timezone) for non-UTC scheduling. `at` mode naive datetimes are also interpreted as UTC unless `tz` is specified.

---

## MCP Tools

MCP tools are registered on first message when `tools.mcpServers` is configured. They appear alongside built-in tools in the agent's tool list. See [MCP Integration](mcp-integration.md) for details.
