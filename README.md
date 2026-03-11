# FeatherFlow

<p align="center">
  <em>🐈‍⬛🪶 A lightweight, extensible personal AI agent framework for production automation and conversational workflows.</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12-blue" alt="Python 3.11 | 3.12" />
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Development Status: Alpha" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
  <a href="https://github.com/astral-sh/ruff"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json" alt="Ruff" /></a>
  <a href="https://github.com/astral-sh/uv"><img src="https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json" alt="uv" /></a>
  <img src="https://img.shields.io/badge/docker-supported-2496ED?logo=docker&logoColor=white" alt="Docker Supported" />
</p>

---

## Overview

FeatherFlow is a compact AI agent runtime designed for developers who want a self-hosted, programmable assistant. It connects to any OpenAI-compatible LLM provider and exposes a rich toolset — file operations, shell execution, web search, scheduled tasks, sub-agents, and external MCP servers — all configurable via a single JSON file.

FeatherFlow is a domain-focused evolution of the upstream [`nanobot`](https://github.com/HKUDS/nanobot) project. Full credit to the upstream team for the excellent engineering baseline in runtime design and tool abstraction.

> **Reference baseline:** `nanobot` @ [`30361c9`](https://github.com/HKUDS/nanobot/commit/30361c9307f9014f49530d80abd5717bc97f554a) (2026-02-23)

---

## Features

| Category | Capabilities |
|---|---|
| **LLM Providers** | OpenRouter, OpenAI, Anthropic, DeepSeek, Gemini, Groq, Moonshot, MiniMax, ZhipuAI, DashScope (Qwen), SiliconFlow, VolcEngine, AiHubMix, vLLM, Ollama, OpenAI Codex (OAuth), GitHub Copilot (OAuth), and any OpenAI-compatible endpoint |
| **Built-in Tools** | File system, shell, web fetch/search, paper research (search/details/download), cron scheduler, sub-agent spawning |
| **Channels** | Channel adapters exist for Feishu/Telegram/Discord/Slack/Email/QQ/DingTalk/MoChat (runtime wiring via config) |
| **MCP Integration** | Connect any MCP-compatible tool server (e.g. [feishu-mcp](https://github.com/lichman0405/feishu-mcp)) |
| **Memory** | RAM-first with snapshots, lesson extraction, and compact session history |
| **Extensibility** | MCP server integration, skill files, custom provider plugins |
| **CLI** | Interactive onboarding, agent chat, gateway mode, cron and memory management |

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/lichman0405/featherflow.git
cd featherflow

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install FeatherFlow
pip install --upgrade pip
pip install -e .

# Verify
featherflow --version
```

### First Run

```bash
# Interactive setup wizard — configures your provider, model, and identity
featherflow onboard

# Send a one-shot message
featherflow agent -m "hello"

# Start an interactive chat session
featherflow agent

# Launch the long-running gateway (channels + scheduled jobs)
featherflow gateway
```

`featherflow onboard` now also supports:

- Paper research tool configuration (`tools.papers` provider, API key, limits)

---

## Installation Options

### With Dev Dependencies

```bash
pip install -e '.[dev]'
```

### Docker (Recommended for Production)

```bash
# Start the gateway
docker compose up --build featherflow-gateway

# Run a one-off CLI command in the container
docker compose --profile cli run --rm featherflow-cli status
```

**Runtime data directory mapping:**

| Location | Path |
|---|---|
| Host | `~/.featherflow` |
| Container | `/home/featherflow/.featherflow` |

> **Security:** The container runs as unprivileged user `featherflow` (UID 1000) — not root. The gateway port (`18790`) is bound to `127.0.0.1` by default and is **not** exposed to the network. Use a reverse proxy (e.g. Nginx) to expose it externally.

---

## Configuration

FeatherFlow reads from `~/.featherflow/config.json`. The interactive wizard (`featherflow onboard`) can generate this file for you.

**Default paths:**

| Item | Path |
|---|---|
| Config file | `~/.featherflow/config.json` |
| Workspace | `~/.featherflow/workspace` |

### Configuration Skeleton

```json
{
  "providers": {
    "openrouter": {
      "apiKey": "sk-or-v1-xxx"
    }
  },
  "agents": {
    "defaults": {
      "model": "anthropic/claude-opus-4-5",
      "name": "featherflow",
      "temperature": 0.7
    }
  },
  "channels": {
  },
  "tools": {
    "web": {
      "enabled": true
    }
  },
  "heartbeat": {
    "enabled": true,
    "intervalSeconds": 1800
  }
}
```

### Key Sections

- **`providers`** — API keys, custom `apiBase` URLs, and optional `extraHeaders` (e.g. `APP-Code` for AiHubMix) for each LLM provider.
- **`agents.defaults`** — Default model, temperature, `maxTokens`, `maxToolIterations`, `memoryWindow`, and agent identity (`name`, `workspace`).
- **`agents.memory`** — Memory flush cadence (`flushEveryUpdates`, `flushIntervalSeconds`) and short-term window sizes.
- **`agents.sessions`** — Session compaction thresholds (`compactThresholdMessages`, `compactThresholdBytes`, `compactKeepMessages`).
- **`agents.selfImprovement`** — Lesson extraction settings: `enabled`, `maxLessonsInPrompt`, `minLessonConfidence`, `maxLessons`, `promotionEnabled`, etc.
- **`channels`** — Channel configuration for each IM adapter; also controls `sendProgress` (stream text to channel), `sendToolHints` (stream tool-call hints), and `sendQueueNotifications` (notify users about task queue position).
  - **`channels.feishu.requireMentionInGroups`** — When `true` (default), the bot only responds to group messages where it is @mentioned. Private chats are unaffected.
- **`gateway`** — HTTP gateway listen address (`host`, `port`; default `0.0.0.0:18790` for bare-metal runs). When using Docker Compose the port is bound to `127.0.0.1:18790` by default.
- **`tools`** — Web/search/fetch behavior, paper research provider settings (`tools.papers`), shell execution policy (`tools.exec.timeout`), `restrictToWorkspace` flag, and MCP server definitions (`tools.mcpServers`).
  - **`tools.mcpServers.<name>.progressIntervalSeconds`** — Heartbeat interval (seconds) for long-running MCP tool calls. Set to `0` to disable. Default `15`.
  - **`tools.mcpServers.<name>.toolTimeout`** — Timeout in seconds before a tool call is cancelled. For scientific computing MCP servers (e.g. raspa, mofstructure), set to `300`–`600`.
  - **`tools.mcpServers.<name>.allowedTools`** — Optional allowlist of tool names. When non-empty, only the listed tools from this MCP server are registered. All others are silently dropped.
  - **`tools.mcpServers.<name>.deniedTools`** — Optional denylist of tool names. Any tool whose name appears here is never registered, regardless of `allowedTools`.
- **`heartbeat`** — Periodic background prompts (`enabled`, `intervalSeconds`) for proactive agent behaviors.

> **Security:** Set file permissions to `0600` on your config file and configure strict `allowFrom` lists before exposing to any channel. See [`docs/SECURITY.md`](docs/SECURITY.md) for full guidance.

### Environment Variable Overrides

Every config field can be overridden at runtime via environment variables using the prefix `FEATHERFLOW_` and `__` as the nesting delimiter:

```bash
# Override the default model
FEATHERFLOW_AGENTS__DEFAULTS__MODEL=deepseek/deepseek-chat featherflow agent

# Inject an API key without editing config.json
FEATHERFLOW_PROVIDERS__OPENROUTER__API_KEY=sk-or-v1-xxx featherflow gateway
```

This is particularly useful in containerised deployments where secrets are injected as environment variables rather than mounted files.

---

## CLI Reference

**Agent & Gateway**

| Command | Description |
|---|---|
| `featherflow onboard` | Interactive setup wizard |
| `featherflow agent` | Start an interactive chat session |
| `featherflow agent -m "<prompt>"` | Send a single prompt and exit |
| `featherflow gateway` | Run the long-running gateway (channels + cron) |

**Status & Diagnostics**

| Command | Description |
|---|---|
| `featherflow status` | Show runtime and provider status |
| `featherflow channels status` | Show channel connection status |

**Memory Management**

| Command | Description |
|---|---|
| `featherflow memory status` | Show memory snapshot and stats |
| `featherflow memory flush` | Force-persist pending memory updates immediately |
| `featherflow memory compact [--max-items N]` | Prune long-term snapshot to at most N items |
| `featherflow memory list [--limit N] [--session S]` | Browse long-term snapshot entries |
| `featherflow memory delete <id>` | Remove a snapshot entry by ID |
| `featherflow memory lessons status` | Show self-improvement lesson stats |
| `featherflow memory lessons list` | List lessons (filter by `--scope`, `--session`, `--limit`) |
| `featherflow memory lessons enable <id>` | Re-enable a disabled lesson |
| `featherflow memory lessons disable <id>` | Suppress a lesson from future prompts |
| `featherflow memory lessons delete <id>` | Permanently remove a lesson |
| `featherflow memory lessons compact [--max-lessons N]` | Prune lessons to at most N entries |
| `featherflow memory lessons reset` | Wipe all lessons |

**Session Management**

| Command | Description |
|---|---|
| `featherflow session compact --session <id>` | Compact a single conversation session |
| `featherflow session compact --all` | Compact all stored sessions |

**Cron Scheduler**

| Command | Description |
|---|---|
| `featherflow cron list` | List all scheduled jobs |
| `featherflow cron add` | Add a new scheduled job |
| `featherflow cron run <id>` | Trigger a job manually |
| `featherflow cron enable <id>` | Enable a job |
| `featherflow cron disable <id>` | Disable a job |
| `featherflow cron remove <id>` | Remove a job permanently |

**Configuration**

| Command | Description |
|---|---|
| `featherflow config show` | Print all non-default config values |
| `featherflow config provider <name>` | Set or update a provider's API key / base URL |
| `featherflow config feishu` | One-shot Feishu channel + feishu-mcp setup |
| `featherflow config pdf2zh` | Configure pdf2zh MCP server (auto-fills LLM credentials) |
| `featherflow config mcp list` | List all configured MCP servers |
| `featherflow config mcp add <name>` | Add or update an MCP server (stdio or HTTP) |
| `featherflow config mcp remove <name>` | Remove an MCP server |

**Providers**

| Command | Description |
|---|---|
| `featherflow provider login openai-codex` | Authenticate with OpenAI Codex (OAuth) |
| `featherflow provider login github-copilot` | Authenticate with GitHub Copilot (OAuth) |

---

## Core Capabilities

### Memory & Self-Improvement

FeatherFlow uses a RAM-first memory architecture:

- **Session window** — unconsolidated recent context for fast recall
- **Long-term snapshots** — periodic persistence with audit trails
- **Lesson extraction** — automatically distills insights from user feedback and tool outcomes
- **Configurable confidence thresholds** — controls promotion of lessons to long-term memory

### Scheduled Tasks

Jobs can be defined as:

- **Interval jobs** — run every N seconds/minutes/hours
- **Cron expression jobs** — full cron syntax support
- **One-time jobs** — execute at a specific datetime

All jobs can be toggled, triggered manually, or removed via the CLI.

### MCP Integration

Connect any MCP-compatible tool server and expose its tools directly to the agent. Define MCP servers under `tools.mcpServers` in your config. For example, connect [feishu-mcp](https://github.com/lichman0405/feishu-mcp) to bring Feishu collaboration capabilities (messages, calendar, tasks, documents) into the agent via a clean MCP interface.

For long-running MCP tools (e.g. scientific computing), FeatherFlow automatically sends periodic heartbeat progress messages to the user so they know the task is still running. Configure `progressIntervalSeconds` per MCP server (default 15s) and increase `toolTimeout` for compute-heavy operations.

### Task Queue Awareness

When multiple users send messages simultaneously (e.g. in a group chat), FeatherFlow queues tasks and notifies each user of their queue position. Users see when their task starts processing and how many tasks are ahead. This is enabled by default via `channels.sendQueueNotifications`.

---

## Development

### Prerequisites

- Python 3.11+
- Linux or macOS (recommended)

### Run Tests

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

### Lint

```bash
.venv/bin/ruff check .
```

---

## Migration Guide

If upgrading from a previous version or migrating from `nanobot`:

| Item | Old | New |
|---|---|---|
| Python package | `nanobot.*` | `featherflow.*` |
| CLI command | `assistant` | `featherflow` |
| Runtime directory | `~/.assistant` | `~/.featherflow` |
| Workspace directory | `~/.assistant/workspace` | `~/.featherflow/workspace` |

Backward-compatible fallbacks for old config and data paths are retained where possible.

---

## MCP Ecosystem

FeatherFlow ships with six domain-specific MCP servers as git submodules under `mcps/`.
They cover porous-material simulation, PDF translation, and team collaboration.

### Bundled MCP Servers

| Name | Submodule | Python | Description |
|---|---|---|---|
| **zeopp** | `mcps/zeopp-backend` | 3.10+ | Zeo++ porous material geometry (volume, pore size, channels) |
| **raspa2** | `mcps/raspa-mcp` | 3.11+ | RASPA2 molecular simulation — input templates, output parsing |
| **mofstructure** | `mcps/mofstructure-mcp` | 3.9+ | MOF structural analysis — building blocks, topology, metal nodes |
| **mofchecker** | `mcps/mofchecker-mcp` | **<3.11** | MOF structure validation — CIF integrity, geometry defects |
| **pdf2zh** | `mcps/pdftranslate-mcp` | 3.10–3.12 | PDF paper translation preserving LaTeX layout (needs OpenAI key) |
| **feishu** | `mcps/feishu-mcp` | 3.11+ | Feishu/Lark — messaging, docs, tasks (needs App ID & Secret) |

### Setup

**1. Clone with submodules** (one-time):

```bash
git clone --recurse-submodules https://github.com/lichman0405/featherflow.git
# or, if you already cloned without --recurse-submodules:
git submodule update --init --recursive
```

**2. Install Python venvs** for each MCP:

```bash
bash scripts/setup_mcps.sh
```

The script uses [`uv`](https://docs.astral.sh/uv/) and pins the correct Python version per MCP
(notably `mofchecker` requires Python 3.10; `pdf2zh` requires ≤3.12).

**3. Register MCPs with featherflow**:

```bash
bash scripts/configure_mcps.sh
```

This calls `featherflow config mcp add` for every server with recommended timeouts and lazy-mode settings.

**4. Add credentials** for the two servers that need them — open `~/.featherflow/config.json` and fill in:

```jsonc
"tools": {
  "mcpServers": {
    "pdf2zh": {
      "env": {
        "OPENAI_BASE_URL": "https://api.openai.com/v1",
        "OPENAI_API_KEY":  "sk-...",
        "OPENAI_MODEL":    "gpt-4o"
      }
    },
    "feishu": {
      "env": {
        "FEISHU_APP_ID":     "cli_...",
        "FEISHU_APP_SECRET": "..."
      }
    }
  }
}
```

> **Security note**: MCP subprocesses launched via the stdio transport inherit only a minimal environment
> (`HOME`, `PATH`, `SHELL`, `USER`, `TERM`, `LOGNAME`) — your LLM provider API keys are never exposed
> to MCP servers unless you explicitly add them to `cfg.env` as shown above.

---

## Documentation Index

### Root Documents

- [README.md](README.md)
- [CHANGELOG.md](CHANGELOG.md)
- [CONTRIBUTING.md](CONTRIBUTING.md)

### Project Docs (`docs/`)

- [docs/API.md](docs/API.md)
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
- [docs/DEVELOPER_GUIDE.md](docs/DEVELOPER_GUIDE.md)
- [docs/RAM_FIRST_MEMORY_CHECKPOINT.md](docs/RAM_FIRST_MEMORY_CHECKPOINT.md)
- [docs/SECURITY.md](docs/SECURITY.md)
- [docs/SELF_DEVELOPMENT.md](docs/SELF_DEVELOPMENT.md)

### Scripts (`scripts/`)

- [scripts/setup_mcps.sh](scripts/setup_mcps.sh) — Create isolated Python venvs for all bundled MCP servers
- [scripts/configure_mcps.sh](scripts/configure_mcps.sh) — Register all bundled MCPs into `~/.featherflow/config.json`

### Skills Docs (`featherflow/skills/`)

- [featherflow/skills/README.md](featherflow/skills/README.md)
- [featherflow/skills/clawhub/SKILL.md](featherflow/skills/clawhub/SKILL.md)
- [featherflow/skills/cron/SKILL.md](featherflow/skills/cron/SKILL.md)
- [featherflow/skills/github/SKILL.md](featherflow/skills/github/SKILL.md)
- [featherflow/skills/memory/SKILL.md](featherflow/skills/memory/SKILL.md)
- [featherflow/skills/skill-creator/SKILL.md](featherflow/skills/skill-creator/SKILL.md)
- [featherflow/skills/summarize/SKILL.md](featherflow/skills/summarize/SKILL.md)
- [featherflow/skills/tmux/SKILL.md](featherflow/skills/tmux/SKILL.md)
- [featherflow/skills/weather/SKILL.md](featherflow/skills/weather/SKILL.md)

### Template Docs (`featherflow/templates/`)

- [featherflow/templates/AGENTS.md](featherflow/templates/AGENTS.md)
- [featherflow/templates/HEARTBEAT.md](featherflow/templates/HEARTBEAT.md)
- [featherflow/templates/SOUL.md](featherflow/templates/SOUL.md)
- [featherflow/templates/TOOLS.md](featherflow/templates/TOOLS.md)
- [featherflow/templates/USER.md](featherflow/templates/USER.md)
- [featherflow/templates/memory/MEMORY.md](featherflow/templates/memory/MEMORY.md)

---

## License

[MIT](LICENSE)
