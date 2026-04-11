# MiQi

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

MiQi is a compact AI agent runtime designed for developers who want a self-hosted, programmable assistant. It connects to any OpenAI-compatible LLM provider and exposes a rich toolset — file operations, shell execution, web search, scheduled tasks, sub-agents, and external MCP servers — all configurable via a single JSON file.

MiQi is a domain-focused evolution of the upstream [`nanobot`](https://github.com/HKUDS/nanobot) project. Full credit to the upstream team for the excellent engineering baseline in runtime design and tool abstraction.

> **Reference baseline:** `nanobot` @ [`30361c9`](https://github.com/HKUDS/nanobot/commit/30361c9307f9014f49530d80abd5717bc97f554a) (2026-02-23)

---

## Features

| Category | Capabilities |
|---|---|
| **LLM Providers** | OpenRouter, OpenAI, Anthropic, DeepSeek, Gemini, Groq, Moonshot, MiniMax, ZhipuAI, DashScope (Qwen), SiliconFlow, VolcEngine, AiHubMix, vLLM, Ollama, OpenAI Codex (OAuth), and any OpenAI-compatible endpoint |
| **Built-in Tools** | File system, shell, web fetch/search, paper research (search/details/download), cron scheduler, sub-agent spawning |
| **Channels** | Feishu is wired in the packaged gateway today; additional adapter modules for Telegram/Discord/Slack/Email/QQ/DingTalk/MoChat are present in the repository for extension work |
| **MCP Integration** | Connect any MCP-compatible tool server (e.g. [feishu-mcp](https://github.com/lichman0405/feishu-mcp)) |
| **Memory** | RAM-first long-term snapshots, lesson extraction, and append-only JSONL session history under the configured workspace |
| **Agent Runtime** | Safe concurrent tool execution for read-only batches, iteration-budget safeguards, MCP heartbeat progress, and optional embedded routing/compression hooks |
| **Extensibility** | MCP server integration, skill files, custom provider plugins |
| **CLI** | Interactive onboarding, agent chat, gateway mode, cron and memory management |

---

## Quick Start

### Installation

```bash
# Clone the repository
git clone https://github.com/lichman0405/miqi.git
cd miqi

# Create and activate a virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install MiQi
pip install --upgrade pip
pip install -e .

# Verify
miqi --version
```

### First Run

```bash
# Interactive setup wizard — configures your provider, model, and identity
miqi onboard

# Send a one-shot message
miqi agent -m "hello"

# Start an interactive chat session
miqi agent

# Launch the long-running gateway (channels + scheduled jobs)
miqi gateway
```

`miqi onboard` now also supports:

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
docker compose up --build miqi-gateway

# Run a one-off CLI command in the container
docker compose --profile cli run --rm miqi-cli status
```

**Runtime data directory mapping:**

| Location | Path |
|---|---|
| Host | `~/.miqi` |
| Container | `/home/miqi/.miqi` |

> **Security:** The container runs as unprivileged user `miqi` (UID 1000) — not root. The gateway port (`18790`) is bound to `127.0.0.1` by default and is **not** exposed to the network. Use a reverse proxy (e.g. Nginx) to expose it externally.

### Bare-Metal (Non-Docker) Deployment

For running the gateway directly on a Linux/macOS host as a long-running service:

**1. Prepare configuration** (if not done already):

```bash
# Interactive setup — creates ~/.miqi/config.json
miqi onboard

# Verify the config
miqi status
```

**2. (Optional) Set up MCP servers:**

```bash
bash scripts/setup_mcps.sh      # install isolated venvs
bash scripts/configure_mcps.sh  # register MCPs into config
```

**3. Run with systemd** (Linux, recommended):

Create `/etc/systemd/system/miqi.service`:

```ini
[Unit]
Description=MiQi AI Agent Gateway
After=network.target

[Service]
Type=simple
User=miqi
WorkingDirectory=/home/miqi
ExecStart=/home/miqi/.local/bin/miqi gateway
Restart=on-failure
RestartSec=10
Environment=HOME=/home/miqi

[Install]
WantedBy=multi-user.target
```

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now miqi
sudo journalctl -u miqi -f   # tail logs
```

On macOS, use `launchd` or a process manager like `supervisord` instead.

**4. Reverse proxy** (optional, for external access):

The gateway listens on `127.0.0.1:18790`. To expose it, place it behind Nginx:

```nginx
server {
    listen 443 ssl;
    server_name miqi.example.com;

    location / {
        proxy_pass http://127.0.0.1:18790;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```

### Upgrading

```bash
cd miqi
git pull --recurse-submodules
pip install -e .                    # reinstall core
bash scripts/setup_mcps.sh          # update MCP venvs
bash scripts/configure_mcps.sh      # re-register MCPs (idempotent)
# then restart the gateway (systemctl restart miqi / docker compose up --build)
```

> **Note:** The Docker image does **not** include MCP submodules — MCP servers run as separate stdio subprocesses on the host. When using Docker, mount or install MCP venvs on the host and configure `tools.mcpServers` commands to point at host-side interpreters, or run MCP servers as separate containers and use HTTP transport (`url` instead of `command`).

---

## Configuration

MiQi reads from `~/.miqi/config.json`. The interactive wizard (`miqi onboard`) can generate this file for you.

**Default paths:**

| Item | Path |
|---|---|
| Config file | `~/.miqi/config.json` |
| Workspace | `~/.miqi/workspace` |

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
      "name": "miqi",
      "temperature": 0.1
    }
  },
  "channels": {},
  "tools": {},
  "heartbeat": {
    "enabled": true,
    "intervalSeconds": 1800
  }
}
```

### Key Sections

- **`providers`** — API keys, custom `apiBase` URLs, and optional `extraHeaders` (for example `APP-Code` on AiHubMix) for each provider.
- **`agents.defaults`** — Default model, temperature, `maxTokens`, `maxToolIterations`, `maxToolResultChars`, `contextLimitChars`, `memoryWindow`, and the workspace path.
- **`agents.memory`** — Flush cadence plus in-memory short-term window sizing. Runtime files live under `<workspace>/memory/`.
- **`agents.sessions`** — JSONL session compaction thresholds and saved-tool-result truncation. The schema also exposes `useSqlite` for the shipped SQLite+FTS5 session backend module, but the packaged CLI/gateway path still instantiates the JSONL `SessionManager` by default.
- **`agents.selfImprovement`** — Lesson extraction settings such as `maxLessonsInPrompt`, `minLessonConfidence`, `feedbackMaxMessageChars`, and promotion controls.
- **`agents.smartRouting`** — Cheap-model routing settings. `AgentLoop` supports them programmatically; the packaged CLI/gateway path currently leaves this disabled unless you embed the runtime yourself.
- **`agents.commandApproval`** — Schema for interactive dangerous-command approval. The repository ships the helper module, while the default `exec` tool path still relies on static deny-pattern guards.
- **`channels`** — Global channel delivery flags (`sendProgress`, `sendToolHints`, `sendQueueNotifications`) plus Feishu gateway configuration. Other adapter modules exist in the repo but are not currently surfaced by the public config schema.
- **`gateway`** — HTTP gateway listen address (`host`, `port`; default `0.0.0.0:18790` for bare-metal runs). Docker Compose binds the published port to `127.0.0.1:18790` by default.
- **`tools`** — Web/search/fetch behavior, paper research provider settings, shell execution policy (`tools.exec.timeout`, `tools.exec.envPassthrough`), the global `restrictToWorkspace` flag, and MCP server definitions.
  - **`tools.mcpServers.<name>.progressIntervalSeconds`** — Heartbeat interval for long-running MCP tools. Set `0` to disable. Default `15`.
  - **`tools.mcpServers.<name>.toolTimeout`** — Timeout before a single MCP tool call is cancelled. Default `30`.
  - **`tools.mcpServers.<name>.lazy`** — Register one lightweight gateway tool instead of all server tools up front.
  - **`tools.mcpServers.<name>.description`** — LLM-facing description for lazy gateway mode.
- **`heartbeat`** — Periodic background prompts (`enabled`, `intervalSeconds`) for proactive behaviors.
- **`cron`** — Scheduler-wide job timeout (`jobTimeoutSeconds`; default `86400`).

> **Security:** Config files are automatically saved with `0600` permissions (owner-read-only) to protect API keys. See [docs/security.md](docs/security.md) for the current security model and operational limits.

### Environment Variable Overrides

Every config field can be overridden at runtime via environment variables using the prefix `MIQI_` and `__` as the nesting delimiter:

```bash
# Override the default model
MIQI_AGENTS__DEFAULTS__MODEL=deepseek/deepseek-chat miqi agent

# Inject an API key without editing config.json
MIQI_PROVIDERS__OPENROUTER__API_KEY=sk-or-v1-xxx miqi gateway
```

This is particularly useful in containerised deployments where secrets are injected as environment variables rather than mounted files.

---

## CLI Reference

**Agent & Gateway**

| Command | Description |
|---|---|
| `miqi onboard` | Interactive setup wizard |
| `miqi agent` | Start an interactive chat session |
| `miqi agent -m "<prompt>"` | Send a single prompt and exit |
| `miqi gateway` | Run the long-running gateway (channels + cron) |

**Status & Diagnostics**

| Command | Description |
|---|---|
| `miqi status` | Show runtime and provider status |
| `miqi channels status` | Show channel connection status |

**Memory Management**

| Command | Description |
|---|---|
| `miqi memory status` | Show memory snapshot and stats |
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

**Session Management**

| Command | Description |
|---|---|
| `miqi session compact --session <id>` | Compact a single conversation session |
| `miqi session compact --all` | Compact all stored sessions |

**Cron Scheduler**

| Command | Description |
|---|---|
| `miqi cron list` | List all scheduled jobs |
| `miqi cron add` | Add a new scheduled job |
| `miqi cron run <id>` | Trigger a job manually |
| `miqi cron enable <id>` | Enable a job |
| `miqi cron disable <id>` | Disable a job |
| `miqi cron remove <id>` | Remove a job permanently |

**Configuration**

| Command | Description |
|---|---|
| `miqi config show` | Print all non-default config values |
| `miqi config provider <name>` | Set or update a provider's API key / base URL |
| `miqi config feishu` | One-shot Feishu channel + feishu-mcp setup |
| `miqi config pdf2zh` | Configure pdf2zh MCP server (auto-fills LLM credentials) |
| `miqi config mcp list` | List all configured MCP servers |
| `miqi config mcp add <name>` | Add or update an MCP server (stdio or HTTP) |
| `miqi config mcp remove <name>` | Remove an MCP server |

**Providers**

| Command | Description |
|---|---|
| `miqi provider login openai-codex` | Authenticate with OpenAI Codex (OAuth) |

---

## Core Capabilities

### Memory & Self-Improvement

MiQi uses a RAM-first memory architecture:

- **Session window** — unconsolidated recent context for fast recall, persisted by default as append-only JSONL files under `<workspace>/sessions/`
- **Long-term snapshots** — periodic persistence with audit trails under `<workspace>/memory/`
- **Lesson extraction** — automatically distills insights from user feedback and tool outcomes
- **Configurable confidence thresholds** — controls promotion of lessons to long-term memory

### Agent Runtime Controls

- **Iteration budget** — the main loop injects pressure hints as it approaches `maxToolIterations`
- **Concurrent dispatch** — safe read-only or path-disjoint tool batches run via `asyncio.gather`
- **Embedded hooks** — the `AgentLoop` constructor exposes optional smart-routing and context-compression controls for programmatic use

### Scheduled Tasks

Jobs can be defined as:

- **Interval jobs** — run every N seconds/minutes/hours
- **Cron expression jobs** — full cron syntax support
- **One-time jobs** — execute at a specific datetime

All jobs can be toggled, triggered manually, or removed via the CLI.

### MCP Integration

Connect any MCP-compatible tool server and expose its tools directly to the agent. Define MCP servers under `tools.mcpServers` in your config. For example, connect [feishu-mcp](https://github.com/lichman0405/feishu-mcp) to bring Feishu collaboration capabilities (messages, calendar, tasks, documents) into the agent via a clean MCP interface.

For long-running MCP tools (e.g. scientific computing), MiQi automatically sends periodic heartbeat progress messages to the user so they know the task is still running. Configure `progressIntervalSeconds` per MCP server (default 15s), increase `toolTimeout` for compute-heavy operations, and use `lazy` mode when a server exposes a large tool surface.

### Task Queue Awareness

When multiple users send messages simultaneously (e.g. in a group chat), MiQi queues tasks and notifies each user of their queue position. Users see when their task starts processing and how many tasks are ahead. This is enabled by default via `channels.sendQueueNotifications`.

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
| Python package | `nanobot.*` | `miqi.*` |
| CLI command | `assistant` | `miqi` |
| Runtime directory | `~/.assistant` | `~/.miqi` |
| Workspace directory | `~/.assistant/workspace` | `~/.miqi/workspace` |

Backward-compatible fallbacks for old config and data paths are retained where possible.

---

## MCP Ecosystem

MiQi ships with seven domain-specific MCP servers as git submodules under `mcps/`.
They cover porous-material science, epitaxial surface analysis, PDF translation, and team collaboration.

### Bundled MCP Servers

| Name | Submodule | Python | Description |
|---|---|---|---|
| **zeopp** | `mcps/zeopp-backend` | 3.10+ | Zeo++ porous material geometry (volume, pore size, channels) |
| **raspa2** | `mcps/raspa-mcp` | 3.11+ | RASPA2 molecular simulation — input templates, output parsing |
| **mofstructure** | `mcps/mofstructure-mcp` | 3.9+ | MOF structural analysis — building blocks, topology, metal nodes |
| **mofchecker** | `mcps/mofchecker-mcp` | **<3.11** | MOF structure validation — CIF integrity, geometry defects |
| **miqrophi** | `mcps/miqrophi-mcp` | 3.10+ | Epitaxial lattice matching — CIF surface analysis, substrate screening, strain calculation |
| **pdf2zh** | `mcps/pdftranslate-mcp` | 3.10–3.12 | PDF paper translation preserving LaTeX layout (needs OpenAI key) |
| **feishu** | `mcps/feishu-mcp` | 3.11+ | Feishu/Lark — messaging, docs, tasks (needs App ID & Secret) |

### Setup

**1. Clone with submodules** (one-time):

```bash
git clone --recurse-submodules https://github.com/lichman0405/miqi.git
# or, if you already cloned without --recurse-submodules:
git submodule update --init --recursive
```

**2. Install Python venvs** for each MCP:

```bash
bash scripts/setup_mcps.sh
```

The script uses [`uv`](https://docs.astral.sh/uv/) and pins the correct Python version per MCP
(notably `mofchecker` requires Python 3.10; `pdf2zh` requires ≤3.12).

**3. Register MCPs with miqi**:

```bash
bash scripts/configure_mcps.sh
```

This calls `miqi config mcp add` for every server with recommended timeouts and lazy-mode settings.

**4. Add credentials** for the two servers that need them — open `~/.miqi/config.json` and fill in:

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

- [docs/index.md](docs/index.md)
- [docs/getting-started.md](docs/getting-started.md)
- [docs/configuration.md](docs/configuration.md)
- [docs/cli-reference.md](docs/cli-reference.md)
- [docs/mcp-integration.md](docs/mcp-integration.md)
- [docs/architecture.md](docs/architecture.md)
- [docs/memory-system.md](docs/memory-system.md)
- [docs/self-improvement.md](docs/self-improvement.md)
- [docs/security.md](docs/security.md)
- [docs/developer-guide.md](docs/developer-guide.md)
- [docs/changelog.md](docs/changelog.md)

### Scripts (`scripts/`)

- [scripts/setup_mcps.sh](scripts/setup_mcps.sh) — Create isolated Python venvs for all bundled MCP servers
- [scripts/configure_mcps.sh](scripts/configure_mcps.sh) — Register all bundled MCPs into `~/.miqi/config.json`

### Skills Docs (`miqi/skills/`)

- [miqi/skills/README.md](miqi/skills/README.md)
- [miqi/skills/cron/SKILL.md](miqi/skills/cron/SKILL.md)
- [miqi/skills/feishu-report/SKILL.md](miqi/skills/feishu-report/SKILL.md)
- [miqi/skills/github/SKILL.md](miqi/skills/github/SKILL.md)
- [miqi/skills/memory/SKILL.md](miqi/skills/memory/SKILL.md)
- [miqi/skills/paper-research/SKILL.md](miqi/skills/paper-research/SKILL.md)
- [miqi/skills/skill-creator/SKILL.md](miqi/skills/skill-creator/SKILL.md)
- [miqi/skills/summarize/SKILL.md](miqi/skills/summarize/SKILL.md)
- [miqi/skills/tmux/SKILL.md](miqi/skills/tmux/SKILL.md)
- [miqi/skills/weather/SKILL.md](miqi/skills/weather/SKILL.md)
- [miqi/skills/workspace-cleanup/SKILL.md](miqi/skills/workspace-cleanup/SKILL.md)

### Template Docs (`miqi/templates/`)

- [miqi/templates/AGENTS.md](miqi/templates/AGENTS.md)
- [miqi/templates/HEARTBEAT.md](miqi/templates/HEARTBEAT.md)
- [miqi/templates/SOUL.md](miqi/templates/SOUL.md)
- [miqi/templates/TOOLS.md](miqi/templates/TOOLS.md)
- [miqi/templates/USER.md](miqi/templates/USER.md)
- [miqi/templates/memory/MEMORY.md](miqi/templates/memory/MEMORY.md)

---

## License

[MIT](LICENSE)
