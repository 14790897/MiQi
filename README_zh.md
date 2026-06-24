# MiQi

<p align="center">
  <em>🐈‍⬛🪶 轻量级、可扩展的个人 AI 代理框架，带现代化桌面界面</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.11%20%7C%203.12-blue" alt="Python 3.11 | 3.12" />
  <img src="https://img.shields.io/badge/node.js-20+-green" alt="Node.js 20+" />
  <img src="https://img.shields.io/badge/status-alpha-orange" alt="Development Status: Alpha" />
  <a href="LICENSE"><img src="https://img.shields.io/badge/license-MIT-green" alt="MIT License" /></a>
</p>

---

## 概述

MiQi 是一个个人 AI 代理框架，将强大的 **Python 运行时引擎** 与 **Electron 桌面应用** 相结合。提供 Codex 风格的应用服务器协议、类型化请求验证、多提供商 LLM 支持、沙箱化命令执行以及插件/技能生态——全部采用本地优先、尊重隐私的架构。

### 核心定位

- 🎯 **个人 AI 代理** — 不只是聊天机器人：持久化记忆、学习技能、文件操作、定时任务
- 🔧 **高度可扩展** — MCP 协议集成外部工具、自定义技能、可插拔 LLM 提供商
- 🖥️ **原生桌面体验** — Electron 系统级集成（WSL2 沙箱、文件系统操作）
- 🔒 **本地优先** — 所有数据本地存储；带版本快照的非破坏性文件编辑
- 📋 **Codex 风格协议** — 类型化 AppServer，JSON Schema 目录，方法稳定性追踪，处理器边界验证

### 技术栈

| 层级 | 技术 | 版本 |
|------|------|------|
| 桌面框架 | Electron | 35.2 |
| 前端 UI | React + TypeScript | 19.1 / 5.8 |
| CSS | Tailwind CSS 4 | 4.x |
| 组件库 | Radix UI + Lucide Icons | — |
| 后端引擎 | Python (asyncio) | 3.11+ |
| 数据验证 | Pydantic v2 | 2.12+ |
| CLI 框架 | Typer | 0.20+ |
| 桌面构建 | electron-vite + electron-builder | 3.1 / 26.0 |
| Python 打包 | PyInstaller + Hatchling | 6.20+ |

---

## 主要特性

| 功能 | 描述 |
|---|---|
| **智能聊天** | 自然语言对话，流式响应，工具调用进度实时显示 |
| **多提供商** | OpenAI、Anthropic、Gemini、OpenRouter、DeepSeek 等，带提供商容错 |
| **Codex 协议** | 类型化 AppServer，31 个方法规范，JSON Schema 目录，处理器边界验证 |
| **记忆系统** | 长期记忆快照、自改进课程、跨会话回忆 |
| **任务调度** | 基于 Cron 的定时任务，支持时区设置 |
| **技能系统** | 创建、上传、管理代理技能；SkillHub 注册中心集成 |
| **插件生态** | MCP 服务器、插件和市场的确定性目录 |
| **沙箱执行** | 基于 bwrap 的沙箱，LANDLOCK 文件系统规则，流式 I/O，进程生命周期管理 |
| **文件管理** | 工作区 FS 带文件监听、模糊搜索、快照/版本控制、非破坏性编辑 |
| **回放调试** | 回合、时间线和消息的确定性回放用于检查 |
| **会话管理** | 浏览、搜索、归档、导入/导出对话历史 |
| **桌面应用** | 15+ 功能页面，实时流式传输，打字机动画，右键菜单 |

---

## 快速开始

### 前置依赖

- **Python 3.11+** — 运行 MiQi 后端
- **Node.js 20+** — 运行 Electron 前端
- **uv** — Python 包管理器（推荐）

### 安装步骤

```bash
# 1. 克隆仓库
git clone http://git.miqroera.com/intership/miqi-desktop.git
cd miqi-desktop

# 2. 安装 Python 依赖
uv sync

# 3. 安装前端依赖
cd apps/desktop
npm install
```

### 开发模式

```bash
# 启动 Electron 开发服务器（带热重载）
cd apps/desktop
npm run dev
```

### 生产构建

```bash
# 构建前端代码
cd apps/desktop
npm run build

# 打包为桌面应用
npx electron-builder
```

---

## 架构说明

```
┌─────────────────────────────────────────────────────────────┐
│                    MiQi Desktop App                         │
├─────────────────────────────────────────────────────────────┤
│  Electron Frontend                                          │
│  ├── React 19 + TypeScript                                 │
│  ├── Tailwind CSS 4 + shadcn/ui                            │
│  └── 15+ 功能页面 (Chat, Agents, Skills, MCPs, ...)        │
├─────────────────────────────────────────────────────────────┤
│  Bridge (IPC 通信)                                          │
│  ├── stdin/stdout JSON-line 协议                            │
│  ├── 状态同步 + 日志转发                                     │
│  └── BridgeRuntimeLoop (持久化 asyncio 事件循环)             │
├─────────────────────────────────────────────────────────────┤
│  AppServer (Codex 风格协议)                                  │
│  ├── ProtocolRegistry (31 个类型化方法规范)                   │
│  ├── 类型化信封 (Pydantic v2)                                │
│  ├── JSON Schema Draft 2020-12 目录                          │
│  └── Turn 处理器类型化验证                                    │
├─────────────────────────────────────────────────────────────┤
│  MiQi Runtime Engine (运行时引擎)                            │
│  ├── RuntimeSession / TaskRunner / TurnRunner               │
│  ├── HistoryRuntime + LedgerRuntime (SQLite 持久化)          │
│  ├── ContextRuntime (压缩、token 预算)                       │
│  ├── ThreadRuntime (fork、rollback、导入/导出)               │
│  └── ReplayRuntime (确定性回放检查)                           │
├─────────────────────────────────────────────────────────────┤
│  Execution & Sandbox (执行与沙箱)                            │
│  ├── ToolOrchestrator (审批 → 沙箱 → 执行)                  │
│  ├── PermissionEngine + ApprovalPolicy + HookRuntime        │
│  ├── bwrap 沙箱 (LANDLOCK、流式 I/O、取消)                   │
│  └── Workbench Process Runtime (command/exec、process/*)    │
├─────────────────────────────────────────────────────────────┤
│  Tools & Integrations (工具与集成)                           │
│  ├── 内置工具 (文件系统、Shell、网络、论文、...)              │
│  ├── MCP Client (外部工具服务器)                             │
│  ├── Plugin Manager + Skill Loader (插件管理 + 技能加载)     │
│  └── Office 文档工具 (docx、pptx、xlsx)                     │
└─────────────────────────────────────────────────────────────┘
```

### Codex 协议方法族

| 族 | 作用域 | 方法 |
|--------|-------|---------|
| `turn/*` | Turn | start, interrupt, steer |
| `thread/*` | Thread | list, get, rollback, fork, delete, compact/start, inject_items |
| `fs/*` | Filesystem | readFile, writeFile, createDirectory, getMetadata, readDirectory, remove, copy, watch, unwatch |
| `fuzzyFileSearch/*` | Filesystem | sessionStart, sessionUpdate, sessionStop |
| `command/exec` | Process | exec, exec/write, exec/resize, exec/terminate |
| `process/*` | Process | spawn, writeStdin, resizePty, kill, list, get, snapshot |
| `replay.*` | Debug | turns, timeline, messages |
| `config/*` | Session | get, batchWrite |
| `model/*` | Session | list, get |
| `feature/*` | Session | list, set |
| `permission/*` | Session | listProfiles, getProfile |
| `plugin/*` | Session | list, install, uninstall, enable, disable, configure |
| `skills/*` | Session | list, get, create, upload, delete, setExtraRoots |
| `mcp/*` | Session | listServers, getServer, status |
| `agent/*` | Session | list, get, spawn, kill |
| `protocol/*` | Connection | catalog, method_names, schema |

---

## 配置说明

应用配置文件位于 `~/.miqi/config.json`：

```json
{
  "providers": {
    "openai": { "apiKey": "sk-..." },
    "anthropic": { "apiKey": "sk-ant-..." }
  },
  "agents": {
    "defaults": {
      "model": "claude-sonnet-4-6",
      "temperature": 0.1,
      "maxToolIterations": 100
    }
  },
  "tools": {
    "restrictToWorkspace": true
  }
}
```

### 环境变量

| 变量名 | 说明 |
|---|---|
| `MIQI_PYTHON_PATH` | 自定义 Python 解释器路径 |
| `MIQI_AGENTS__DEFAULTS__MODEL` | 覆盖默认模型 |

---

## 开发指南

### 项目结构

```
miqi-desktop/
├── miqi/                         # Python 后端
│   ├── runtime/                  # 运行时引擎 (AppServer, Session, Turn, Thread, Replay, ...)
│   ├── agent/                    # 代理逻辑、工具、记忆、追踪
│   ├── bridge/                   # Electron 桥接服务 (IPC 协议)
│   ├── execution/                # 沙箱、权限、审批、钩子
│   ├── providers/                # LLM 提供商实现
│   ├── channels/                 # 聊天渠道适配器 (飞书、Slack、Discord、...)
│   ├── sandbox/                  # bwrap 沙箱管理器
│   ├── skills/                   # 内置技能 (cron、论文研究、飞书报告、...)
│   ├── config/                   # 配置加载器和 schema
│   ├── cli/                      # CLI 命令 (agent、gateway、trace、config)
│   ├── cron/                     # Cron 调度服务
│   ├── documents/                # Office 文档工具 (docx、pptx、xlsx)
│   └── observability/            # OpenTelemetry 集成
├── apps/
│   └── desktop/                  # Electron 前端
│       ├── src/main/             # 主进程 (BridgeManager、IPC 处理器)
│       ├── src/renderer/         # 渲染进程 (React 页面和组件)
│       └── src/preload/          # 预加载脚本 (contextBridge API)
├── tests/                        # 测试套件 (~1800+ 测试)
│   ├── runtime/                  # 运行时单元和集成测试
│   └── bridge/                   # 桥接协议和审计测试
├── docs/                         # 文档 (MkDocs)
├── plan/                         # 实现计划 (不纳入版本交付物)
└── scripts/                      # 构建和工具脚本
```

### 代码规范

- **Python**: 使用 Ruff 进行代码检查 (行宽 100)
- **TypeScript**: 使用 ESLint 进行代码检查
- **提交信息**: 遵循 Conventional Commits 规范

### 测试

```bash
# Python 后端测试 (~1800+ 测试)
uv run pytest

# 跳过沙箱/子进程测试以快速反馈
uv run pytest -m "not sandbox and not subprocess"

# 前端测试
cd apps/desktop
npm run test
```

---

## 文档

- [快速开始](docs/getting-started.md)
- [系统架构](docs/architecture.md)
- [配置参考](docs/configuration.md)
- [MCP 集成](docs/mcp-integration.md)
- [开发指南](docs/developer-guide.md)
- [内部 Alpha 冒烟测试](docs/internal-alpha-smoke.md)

---

## 许可证

[MIT License](LICENSE)

---

## 贡献

欢迎提交 Issue 和 Pull Request！请参考 [CONTRIBUTING.md](CONTRIBUTING.md) 获取详细信息。
