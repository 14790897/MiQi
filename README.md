# FeatherFlow Assistant

FeatherFlow is a lightweight personal AI assistant runtime focused on practical automation, conversational workflows, and extensibility.

## Project Origin

FeatherFlow is derived from the upstream `nanobot` project and then evolved for a Feishu-first domain workflow.

- Upstream repository: https://github.com/HKUDS/nanobot
- Reference baseline: `origin/main` commit `30361c9307f9014f49530d80abd5717bc97f554a` (2026-02-23)

Respect to the upstream team: `nanobot` provides an excellent engineering baseline in runtime design, tool abstraction, and practical developer experience. FeatherFlow stands on that solid foundation and continues with domain-specific optimization.

## What FeatherFlow Provides

- Feishu-first chat runtime for production usage
- Multi-provider LLM routing (OpenRouter, OpenAI, Anthropic, DeepSeek, Gemini, local OpenAI-compatible endpoints, etc.)
- Built-in tools for files, shell, web search/fetch, scheduling, and sub-agents
- RAM-first memory with snapshots, lessons, and compact session history
- MCP integration for external tool servers
- Complete CLI workflow for onboarding, chat, gateway, status, memory, and cron management

## Core Capabilities

### 1. Interactive Onboarding

`featherflow onboard` guides you through:

- LLM provider selection
- model selection (including cloud model listing for compatible providers)
- API key and base URL setup
- web search/fetch mode setup
- runtime identity and soul preset setup

### 2. Chat and Gateway Modes

- `featherflow agent`: interactive terminal chat
- `featherflow agent -m "..."`: one-shot prompt
- `featherflow gateway`: long-running gateway for channels and scheduled jobs

### 3. Feishu Runtime

- WebSocket long connection
- access control via `allowFrom`
- gateway routing and progress streaming controls

### 4. Memory and Self-Improvement

- session memory with unconsolidated window handling
- long-term snapshots and audit trails
- lesson extraction from user feedback and tool outcomes
- configurable confidence and promotion logic

### 5. Scheduled Tasks

- interval jobs
- cron-expression jobs
- one-time jobs
- manual run / enable / disable / remove

### 6. MCP Support

Connect MCP servers and expose external tools directly to FeatherFlow.

## Installation

### Prerequisites

- Python 3.11+
- Linux/macOS shell environment recommended

### Clone Repository

```bash
git clone https://github.com/lichman0405/featherflow.git
cd featherflow
python3 -m venv .venv
source .venv/bin/activate
```

### Install Runtime

```bash
pip install --upgrade pip
pip install -e .
```

### Install Dev Dependencies (Optional)

```bash
pip install -e '.[dev]'
```

### Verify Install

```bash
featherflow --version
```

## Quick Start

```bash
featherflow onboard
featherflow agent -m "hello"
featherflow gateway
featherflow status
```

## Docker Quick Start

### Start Gateway with Docker Compose

```bash
docker compose up --build featherflow-gateway
```

### Run One-Off CLI Command in Container

```bash
docker compose --profile cli run --rm featherflow-cli status
```

### Docker Runtime Data Directory

- Host path: `~/.featherflow`
- Container path: `/root/.featherflow`

## Migration

If you are migrating from previous project naming/runtime versions:

- Python package path changed from `nanobot.*` to `featherflow.*`
- CLI command changed from `assistant` to `featherflow`
- Default runtime directory changed from `~/.assistant` to `~/.featherflow`
- Default workspace changed from `~/.assistant/workspace` to `~/.featherflow/workspace`

FeatherFlow keeps backward-compatible fallback for old config/data paths where possible.

## Configuration Overview

Main config is JSON-based and includes:

- default config path: `~/.featherflow/config.json`
- default workspace path: `~/.featherflow/workspace`
- `providers`: API keys and endpoints
- `agents.defaults`: model, temperature, limits, identity defaults
- `channels.feishu`: app credentials and allow-list
- `tools`: web/search/fetch/exec behavior and MCP servers
- `heartbeat`: periodic background prompts

Example skeleton:

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
      "name": "featherflow"
    }
  },
  "channels": {
    "feishu": {
      "enabled": true,
      "appId": "cli_xxx",
      "appSecret": "xxx",
      "allowFrom": []
    }
  }
}
```

## CLI Reference

- `featherflow onboard`
- `featherflow agent`
- `featherflow gateway`
- `featherflow status`
- `featherflow channels status`
- `featherflow memory status`
- `featherflow cron add|list|run|remove|enable`
- `featherflow provider login <provider>`

## Development

### Run Tests

```bash
PYTHONPATH=. .venv/bin/pytest -q
```

### Lint

```bash
.venv/bin/ruff check .
```

## Notes

- The repository keeps a compact implementation style for fast iteration.
- Use dedicated keys and strict channel allow-lists for production.
- Read `docs/SECURITY.md` before internet-facing deployment.

## License

MIT
