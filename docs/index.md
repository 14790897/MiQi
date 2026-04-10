# MiQi

<p align="center">
  <em>A lightweight, extensible personal AI agent framework for production automation and conversational workflows.</em>
</p>

[![Python](https://img.shields.io/badge/python-3.11%20%7C%203.12-blue)](https://python.org)
[![Status](https://img.shields.io/badge/status-alpha-orange)](https://github.com/lichman0405/MiQi)
[![License](https://img.shields.io/badge/license-MIT-green)](https://github.com/lichman0405/MiQi/blob/main/LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Docker](https://img.shields.io/badge/docker-supported-2496ED?logo=docker&logoColor=white)](https://hub.docker.com)

---

MiQi is a compact AI agent runtime designed for developers who want a self-hosted, programmable assistant. It connects to any OpenAI-compatible LLM provider and exposes a rich toolset — file operations, shell execution, web search, scheduled tasks, sub-agents, and external MCP servers — all configurable via a single JSON file.

## Features

| Category | Capabilities |
|---|---|
| **LLM Providers** | OpenRouter, OpenAI, Anthropic, DeepSeek, Gemini, Groq, Moonshot, MiniMax, ZhipuAI, DashScope (Qwen), SiliconFlow, VolcEngine, AiHubMix, vLLM, Ollama, OpenAI Codex (OAuth), and any OpenAI-compatible endpoint |
| **Built-in Tools** | File system, shell, web fetch/search, paper research (search/details/download), cron scheduler, sub-agent spawning |
| **Channels** | Feishu/Lark, Telegram, Discord, Slack, Email, QQ, DingTalk, MoChat |
| **MCP Integration** | Connect any MCP-compatible tool server; seven domain-specific MCP servers bundled |
| **Memory** | RAM-first with snapshots, lesson extraction, and compact session history |
| **Extensibility** | MCP server integration, skill files, custom provider plugins |
| **CLI** | Interactive onboarding, agent chat, gateway mode, cron and memory management |

## Quick Navigation

- :material-rocket-launch: **[Getting Started](getting-started.md)** — Installation, quick start, and first run
- :material-cog: **[Configuration](configuration.md)** — Config file reference and environment variables
- :material-console: **[CLI Reference](cli-reference.md)** — All commands, tools, and their options
- :material-puzzle: **[MCP Integration](mcp-integration.md)** — Connect bundled and custom MCP servers
- :material-sitemap: **[Architecture](architecture.md)** — System design and module breakdown
- :material-brain: **[Memory System](memory-system.md)** — RAM-first memory architecture
- :material-school: **[Self-Improvement](self-improvement.md)** — Lesson extraction and feedback loop
- :material-shield: **[Security](security.md)** — Security policy and best practices
- :material-code-braces: **[Developer Guide](developer-guide.md)** — Contributing and development setup

## Acknowledgements

MiQi is a domain-focused evolution of the upstream [`nanobot`](https://github.com/HKUDS/nanobot) project. Full credit to the upstream team for the excellent engineering baseline in runtime design and tool abstraction.

> **Reference baseline:** `nanobot` @ [`30361c9`](https://github.com/HKUDS/nanobot/commit/30361c9307f9014f49530d80abd5717bc97f554a) (2026-02-23)
