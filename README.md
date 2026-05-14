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
| **Memory System** | Manage long-term memory snapshots and self-improvement lessons |
| **Session Management** | Browse, search, and compact conversation history |
| **Task Scheduler** | Create and manage scheduled tasks (Cron support) |
| **Skill System** | Configure and enable various agent skills |
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

```bash
# Build frontend code
cd apps/desktop
npm run build

# Package as desktop application
npx electron-builder
```

---

## Usage Guide

### First Run

1. Launch the application
2. Go through the setup wizard
3. Configure LLM providers (e.g., OpenAI, OpenRouter)
4. Enter your API keys
5. Start chatting with the AI agent

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
│  └── shadcn/ui Components                                  │
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
│  └── Provider Interface                                    │
└─────────────────────────────────────────────────────────────┘
```

---

## Development Guide

### Project Structure

```
miqi-desktop/
├── miqi/                    # Python backend code
│   ├── agent/               # Core agent logic
│   ├── bridge/              # Bridge service for Electron communication
│   ├── providers/           # LLM provider implementations
│   └── ...
├── apps/
│   └── desktop/             # Electron frontend application
│       ├── src/
│       │   ├── main/        # Main process code
│       │   ├── renderer/    # Renderer process code
│       │   └── preload/     # Preload scripts
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
