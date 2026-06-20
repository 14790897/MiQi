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

## 概述

MiQi Desktop 是一款基于 Electron 构建的桌面应用，为 MiQi AI 代理提供现代化的图形界面。它将强大的 AI 代理能力与直观的用户界面相结合，支持聊天交互、记忆管理、任务调度等功能。

## 主要特性

| 功能 | 描述 |
|---|---|
| **智能聊天** | 与 AI 代理进行自然语言对话 |
| **多提供商支持** | 支持 OpenAI、Anthropic、Gemini、OpenRouter 等多种 LLM 提供商 |
| **记忆系统** | 管理长期记忆快照和自改进课程 |
| **会话管理** | 浏览、搜索和压缩对话历史 |
| **任务调度** | 创建和管理定时任务（Cron） |
| **技能系统** | 配置和启用各类代理技能 |
| **文件管理** | 工作区文件系统操作 |
| **实时日志** | 监控代理活动和调试信息 |

---

## 快速开始

### 前置依赖

- **Python 3.11+** - 运行 MiQi 后端
- **Node.js 20+** - 运行 Electron 前端
- **uv** - Python 包管理器（推荐）

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

## 使用指南

### 首次运行

1. 启动应用后，进入设置向导
2. 配置 LLM 提供商（如 OpenAI、OpenRouter 等）
3. 输入 API 密钥
4. 开始与 AI 代理聊天

### 核心功能

**聊天界面**
- 支持 Markdown 格式输出
- 实时显示工具调用进度
- 支持代码高亮

**提供商管理**
- 添加/编辑 LLM 提供商配置
- 测试连接状态
- 切换默认模型

**记忆管理**
- 查看长期记忆快照
- 管理自改进课程
- 导入/导出记忆数据

**任务调度**
- 创建定时任务（支持 Cron 表达式）
- 启用/禁用任务
- 手动触发任务执行

---

## 配置说明

应用配置文件位于 `~/.miqi/config.json`，包含以下主要配置项：

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

### 环境变量

| 变量名 | 说明 |
|---|---|
| `MIQI_PYTHON_PATH` | 自定义 Python 解释器路径 |
| `MIQI_AGENTS__DEFAULTS__MODEL` | 覆盖默认模型 |

---

## 架构说明

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
│  ├── RuntimeSession/TaskRunner/TurnRunner (核心运行时引擎)    │
│  ├── Memory System (记忆系统)                               │
│  ├── Tool Registry (工具注册)                               │
│  └── Provider Interface (提供商接口)                         │
└─────────────────────────────────────────────────────────────┘
```

---

## 开发指南

### 项目结构

```
miqi-desktop/
├── miqi/                    # Python 后端代码
│   ├── agent/               # 代理核心逻辑
│   ├── bridge/              # 与 Electron 通信的桥接服务
│   ├── providers/           # LLM 提供商实现
│   └── ...
├── apps/
│   └── desktop/             # Electron 前端应用
│       ├── src/
│       │   ├── main/        # 主进程代码
│       │   ├── renderer/    # 渲染进程代码
│       │   └── preload/     # 预加载脚本
│       └── electron-builder.yml
└── ...
```

### 代码规范

- **Python**: 使用 Ruff 进行代码检查
- **TypeScript**: 使用 ESLint 进行代码检查
- **提交信息**: 遵循 Conventional Commits 规范

### 测试

```bash
# Python 后端测试
uv run pytest

# 前端测试
cd apps/desktop
npm run test
```

---

## 许可证

[MIT License](LICENSE)

---

## 贡献

欢迎提交 Issue 和 Pull Request！请参考 [CONTRIBUTING.md](CONTRIBUTING.md) 获取详细信息。
