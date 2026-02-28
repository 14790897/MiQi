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
| **LLM Providers** | OpenRouter, OpenAI, Anthropic, DeepSeek, Gemini, and any OpenAI-compatible endpoint |
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
| Container | `/root/.featherflow` |

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

- **`providers`** — API keys and base URLs for each LLM provider.
- **`agents.defaults`** — Default model, temperature, token limits, and agent identity.
- **`channels`** — Channel configuration for each IM adapter (see individual channel docs).
- **`tools`** — Web/search/fetch behavior, paper research provider settings (`tools.papers`), shell execution policy, and MCP server definitions.
- **`heartbeat`** — Periodic background prompts (`enabled`, `intervalSeconds`) for proactive agent behaviors.

> **Security:** Set file permissions to `0600` on your config file and configure strict `allowFrom` lists before exposing to any channel. See [`docs/SECURITY.md`](docs/SECURITY.md) for full guidance.

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
| `featherflow memory status` | Show memory snapshot and stats |

**Cron Scheduler**

| Command | Description |
|---|---|
| `featherflow cron list` | List all scheduled jobs |
| `featherflow cron add` | Add a new scheduled job |
| `featherflow cron run <id>` | Trigger a job manually |
| `featherflow cron enable <id>` | Enable a job |
| `featherflow cron disable <id>` | Disable a job |
| `featherflow cron remove <id>` | Remove a job permanently |

**Providers**

| Command | Description |
|---|---|
| `featherflow provider login <provider>` | Authenticate with an LLM provider |

**Config (interactive wizards)**

| Command | Description |
|---|---|
| `featherflow config show` | Print current config (keys masked) |
| `featherflow config provider <name>` | Set API key / base URL for a provider |
| `featherflow config feishu` | Configure Feishu channel **and** feishu-mcp in one step |
| `featherflow config pdf2zh` | Configure pdf2zh MCP, auto-filling credentials from your provider |
| `featherflow config mcp list` | List all configured MCP servers |
| `featherflow config mcp add` | Add a custom MCP server interactively |
| `featherflow config mcp remove <name>` | Remove an MCP server |

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

Connect any MCP-compatible tool server and expose its tools directly to the agent.
MCP servers are defined under `tools.mcpServers` in your config — but you don't need to edit JSON by hand.
Use the `featherflow config` commands described below.

---

## Chat App Setup

This guide walks through connecting FeatherFlow to a Feishu group with PDF translation.
All steps use the interactive `featherflow config` wizards — no JSON editing required.

### Prerequisites

1. **Feishu Open Platform app** — create an in-house app at <https://open.feishu.cn/>, note down:
   - **App ID** — looks like `cli_xxxxxxxxxxxxxxxxxx`
   - **App Secret** — 32-character hex string
   - Grant permissions: `im:message`, `im:chat.members:read`, `drive:drive`, `docx:document`, `drive:permission:write`
   - Add bot to your target group: Group Settings → Group Bots → Add Bot

2. **feishu-mcp installed** in a venv:
   ```bash
   git clone https://github.com/lichman0405/feishu-mcp ~/feishu-mcp
   cd ~/feishu-mcp && python3 -m venv .venv && .venv/bin/pip install -e .
   ```

3. *(Optional)* **pdftranslate-mcp installed** in a separate Python 3.12 venv
   (required because its dependencies need Python < 3.13):
   ```bash
   git clone https://github.com/lichman0405/pdftranslate-mcp ~/pdftranslate-mcp
   cd ~/pdftranslate-mcp
   uv venv .venv --python 3.12   # or: python3.12 -m venv .venv
   .venv/bin/pip install -e .
   ```

---

### Step 1 — Configure Feishu channel + feishu-mcp

```bash
featherflow config feishu
```

What it asks:

| Prompt | What to enter |
|---|---|
| `Feishu App ID` | `cli_xxxxxxxxxxxxxxxxxx` from the open platform |
| `Feishu App Secret` | the 32-char secret (input is hidden) |
| `Path to feishu-mcp Python executable` | auto-detected from `~/feishu-mcp/.venv/bin/python`; press Enter to accept, or paste the path manually |

This writes both `channels.feishu` and `tools.mcpServers.feishu-mcp` in one shot.

---

### Step 2 — Configure pdf2zh MCP (optional)

```bash
featherflow config pdf2zh
```

What it asks:

| Prompt | What to enter |
|---|---|
| `Model name for translation` | defaults to your current model — press Enter to keep it, or type e.g. `kimi-k2.5` |
| `Path to pdf2zh Python executable` | auto-detected from `~/pdftranslate-mcp/.venv/bin/python`; press Enter or paste path |

> **Note:** API key and base URL are copied automatically from the provider you configured during `featherflow onboard`. You do **not** need to re-enter them.

If your provider base URL doesn't already end in `/v1`, the command appends it automatically.

---

### Step 3 — Start the gateway

```bash
featherflow gateway
```

FeatherFlow will connect to Feishu via WebSocket long connection and start the MCP servers as child processes. Send a message to the bot in your Feishu group to verify.

---

### Verify configuration

```bash
featherflow config show          # see full config (keys masked)
featherflow config mcp list      # confirm feishu-mcp and pdf2zh are listed
featherflow channels status      # check Feishu WebSocket connection
```

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
