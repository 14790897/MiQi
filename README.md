# MiQi Desktop

<p align="center">
  <em>🐈‍⬛🪶 A lightweight, extensible personal AI agent with a modern desktop interface</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12-blue" alt="Python 3.11 | 3.12" />
  <img src="https://img.shields.io/badge/node.js-20+-green" alt="Node.js 20+" />
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Development Status: Alpha" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
</p>

---

## Overview

MiQi Desktop is an Electron-based desktop application that provides a modern graphical interface for the MiQi AI agent. It combines powerful AI agent capabilities with an intuitive user interface, supporting chat interaction, memory management, task scheduling, and more.

## Key Features

| Feature | Description |
|---|---|
| **Smart Chat** | Natural language conversation with AI agent |
| **Multi-provider Support** | Supports OpenAI, Anthropic, Gemini, OpenRouter, and more LLM providers |
| **Multi-channel** | Connect via Feishu, WeChat, DingTalk and more message channels |
| **Memory System** | Manage long-term memory snapshots and self-improvement lessons |
| **Session Management** | Browse, search, and compact conversation history |
| **Task Scheduler** | Create and manage scheduled tasks (Cron support) |
| **Skill System** | Configure and enable various agent skills |
| **Sandbox Isolation** | Per-session bwrap sandbox on WSL2 for safe code execution |
| **File Management** | Workspace file system operations |
| **Real-time Logs** | Monitor agent activity and debug information |

---

## Quick Start

### Prerequisites

- **Python 3.11+** - Required to run MiQi backend
- **Node.js 20+** - Required to run Electron frontend
- **uv** - Python package manager (recommended)

### Installation

```bash
# 1. Clone the repository
git clone http://git.miqroera.com/intership/miqi-desktop.git
cd miqi-desktop

# 2. Install Python dependencies
uv sync

# 3. Install frontend dependencies
cd apps/desktop
npm install
```

### Development Mode

```bash
# Start Electron dev server with hot-reload
cd apps/desktop
npm run dev
```

### Production Build

**One-step build** (recommended):

```bash
cd apps/desktop
npm run build:all    # Python backend → Frontend compile → Electron package
```

**Step-by-step build**:

```bash
cd apps/desktop

# 1. Build Python backend (generates dist/miqi-bridge.exe)
npm run build:bridge

# 2. Compile frontend
npm run build

# 3. Package as desktop application
npx electron-builder --win --publish never
```

The packaged `miqi-bridge.exe` is a self-contained binary (PyInstaller onefile) that includes Python and all dependencies — no system Python installation required on the target machine. It also supports a `--check` flag for environment validation:

```bash
miqi-bridge.exe --check
# Output: {"ok": true, "python_version": "3.12.10", "issues": []}
```

---

## Usage Guide

### First Run

1. Launch the application
2. Go through the setup wizard:
   - **Environment Check** — validates Python and dependencies (bundled exe auto-detects; dev mode checks system Python)
   - **WSL2 Setup** — (Windows only) auto-detects and installs WSL2 for sandbox support
   - **LLM Provider** — configure API keys and default model
3. Start chatting with the AI agent

### Core Features

**Chat Interface**
- Markdown format support
- Real-time tool call progress
- Code syntax highlighting

**Provider Management**
- Add/edit LLM provider configurations
- Test connection status
- Switch default models

**Memory Management**
- View long-term memory snapshots
- Manage self-improvement lessons
- Import/export memory data

**Task Scheduler**
- Create scheduled tasks (Cron expressions supported)
- Enable/disable tasks
- Manually trigger task execution

---

## Configuration

The application configuration file is located at `~/.miqi/config.json` and contains the following main configuration options:

```json
{
  "providers": {
    "openai": { "apiKey": "sk-..." },
    "anthropic": { "apiKey": "sk-ant-..." }
  },
  "agents": {
    "defaults": {
      "model": "gpt-4o",
      "temperature": 0.1,
      "maxToolIterations": 50
    }
  },
  "tools": {
    "restrictToWorkspace": true
  }
}
```

### Environment Variables

| Variable | Description |
|---|---|
| `MIQI_PYTHON_PATH` | Custom Python interpreter path |
| `MIQI_AGENTS__DEFAULTS__MODEL` | Override default model |

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    MiQi Desktop App                         │
├─────────────────────────────────────────────────────────────┤
│  Electron Frontend                                          │
│  ├── React + TypeScript                                    │
│  ├── Tailwind CSS                                          │
│  └── Radix UI Components                                   │
├─────────────────────────────────────────────────────────────┤
│  Bridge (IPC Communication)                                 │
│  ├── stdout/stderr JSON protocol                           │
│  ├── State synchronization                                 │
│  └── Log forwarding                                        │
├─────────────────────────────────────────────────────────────┤
│  MiQi Python Runtime                                       │
│  ├── AgentLoop (Core agent engine)                         │
│  ├── Memory System                                         │
│  ├── Tool Registry                                         │
│  ├── Provider Interface                                    │
│  └── Channel Bus (Feishu / WeChat / DingTalk)              │
├─────────────────────────────────────────────────────────────┤
│  Sandbox Layer (WSL2 + bwrap)                              │
│  ├── Per-session isolation                                 │
│  ├── Filesystem sandboxing                                 │
│  └── Safe code execution                                   │
└─────────────────────────────────────────────────────────────┘
```

---

## Development Guide

### Project Structure

```
miqi-desktop/
├── miqi/                    # Python backend code
│   ├── agent/               # Core agent logic & tool registry
│   ├── bridge/              # Bridge service for Electron communication
│   ├── providers/           # LLM provider implementations
│   ├── channels/            # Message channel adapters (Feishu/WeChat/DingTalk)
│   ├── sandbox/             # bwrap sandbox manager (WSL2)
│   └── ...
├── apps/
│   └── desktop/             # Electron frontend application
│       ├── src/
│       │   ├── main/        # Main process (IPC handlers, BridgeManager)
│       │   ├── renderer/    # Renderer process (React UI)
│       │   └── preload/     # Preload scripts (contextBridge)
│       └── electron-builder.yml
└── ...
```

### Code Standards

- **Python**: Ruff for linting
- **TypeScript**: ESLint for linting
- **Commit Messages**: Conventional Commits format

### Testing

```bash
# Python backend tests
uv run pytest

# Frontend tests
cd apps/desktop
npm run test
```

---

## License

[MIT License](LICENSE)

---

## Contributing

Contributions are welcome! Please see [CONTRIBUTING.md](CONTRIBUTING.md) for details.
