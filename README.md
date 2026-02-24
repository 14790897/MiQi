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

FeatherFlow is a domain-focused evolution of the upstream [`nanobot`](https://github.com/HKUDS/nanobot) project, optimized for Feishu-first production workflows. Full credit to the upstream team for the excellent engineering baseline in runtime design and tool abstraction.

> **Reference baseline:** `nanobot` @ [`30361c9`](https://github.com/HKUDS/nanobot/commit/30361c9307f9014f49530d80abd5717bc97f554a) (2026-02-23)

---

## Features

| Category | Capabilities |
|---|---|
| **LLM Providers** | OpenRouter, OpenAI, Anthropic, DeepSeek, Gemini, and any OpenAI-compatible endpoint |
| **Built-in Tools** | File system, shell, web fetch/search, cron scheduler, sub-agent spawning |
| **Channels** | Feishu (WebSocket, runtime enabled) |
| **Memory** | RAM-first with snapshots, lesson extraction, and compact session history |
| **Extensibility** | MCP server integration, skill files, custom provider plugins |
| **CLI** | Interactive onboarding, agent chat, gateway mode, cron and memory management |

> Channel adapters for Telegram/Discord/Slack/Email/QQ/DingTalk/MoChat may exist in code, but current runtime wiring is Feishu-only.

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
    "feishu": {
      "enabled": true,
      "appId": "cli_xxx",
      "appSecret": "xxx",
      "allowFrom": []
    }
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
- **`channels`** — Feishu channel credentials and access-control settings.
- **`tools`** — Web/search/fetch behavior, shell execution policy, and MCP server definitions.
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

Connect any MCP-compatible tool server and expose its tools directly to the agent. Define MCP servers under the `tools.mcp` section of your config.

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

## License

[MIT](LICENSE)
