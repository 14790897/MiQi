# 系统架构

## 分层架构

MiQi Desktop 采用 **三层分离架构**：

### 前端层 + 通信协议

```mermaid
graph TB
    UI["🖥️ Electron 窗口 (Chromium)"]

    subgraph MAIN["Main Process (Node.js)"]
        BM["BridgeManager<br/>管理 Python 子进程生命周期"]
        WM["WindowManager<br/>窗口创建、尺寸、托盘"]
        IPC["IPC Router<br/>10+ ipcMain.handle() 注册"]
    end

    subgraph RENDERER["Renderer Process (React + TypeScript)"]
        CC["💬 ChatConsole<br/>流式对话、Markdown 渲染"]
        SE["📂 SessionExplorer<br/>历史会话浏览、切换"]
        PP["🔌 ProvidersPage<br/>LLM 提供商配置"]
        MP["🧠 MemoryPage<br/>三层记忆管理"]
        SP["⚡ SkillsPage<br/>技能安装、管理"]
        STP["⚙️ SettingsPage<br/>全局配置"]
    end

    MAIN <==>"contextBridge<br/>ipcRenderer.invoke / on"==> RENDERER

    BRIDGE_PROTO["📡 Bridge IPC Protocol<br/>stdin → JSON-line → stdout<br/>{id, method, params}"]

    MAIN --> BRIDGE_PROTO
```

### Python 后端 + 工具层

```mermaid
graph TB
    BS["🔀 Bridge Server<br/>57 个 handler, 异步消息分发"]
    BS --> ROUTER{"请求路由"}

    ROUTER --> AGENT
    ROUTER --> CHAT
    ROUTER --> MEM
    ROUTER --> SESS
    ROUTER --> CNF

    subgraph AGENT["Agent 引擎"]
        AL["AgentLoop<br/>上下文构建 → LLM 调用 → 工具执行 → 循环"]
        CTX["ContextBuilder<br/>注入 SOUL/IDENTITY/MEMORY/TRACE"]
        SUB["Subagent<br/>多 Agent 协作"]
    end

    subgraph TOOLS["工具系统 (15+ 内置工具)"]
        FS["文件操作<br/>read / write / edit / glob"]
        NET["网络工具<br/>web_search / web_fetch"]
        EXEC["执行工具<br/>bash / powershell / python"]
        MCP_CLIENT["MCP Client<br/>连接外部工具服务器"]
    end

    subgraph MEM["记忆系统"]
        CLOUD["☁️ Cloud Memory"]
        USER["👤 User Memory"]
        WS["📁 Workspace Memory"]
    end

    subgraph INFRA["基础设施"]
        SESS["Session Manager"]
        TRACE["Trace Store"]
        CONFIG["Config Loader"]
    end

    AL --> CTX
    AL --> TOOLS
    MCP_CLIENT --> MCP_SERVERS

    MCP_SERVERS["🔗 MCP 工具服务器<br/>raspa-mcp · zeopp-backend · pdftranslate-mcp · mofstructure-mcp · feishu-mcp"]
```

## 核心设计原则

### 1. 前后端分离

前端 (Electron + React) 和后端 (Python Agent) 通过 **JSON-line stdin/stdout** 协议通信，而非 HTTP。这样设计的原因：

- **零网络依赖**：不需要端口管理，避免端口冲突
- **进程隔离**：Python 进程崩溃不影响 UI
- **安全通信**：不暴露网络接口
- **子进程管理**：Electron 可控制 Python 进程的生命周期

### 2. 工具可插拔

所有工具通过 `ToolRegistry` 统一注册，支持：

- 内置工具（文件、网络、Shell 等）
- MCP 外部工具（RASPA2、Zeo++ 等）
- Agent 自定义技能

### 3. 记忆持久化

采用三层记忆架构：Cloud Memory → User Memory → Workspace Memory，确保 Agent 在跨会话、跨项目中保持上下文。

### 4. 非破坏性编辑

文件写入前自动创建快照，支持 diff / revert / accept，提供 Git 之外的轻量级版本控制。

## 运行时组件

| 组件 | 进程 | 职责 |
|------|------|------|
| Electron Main | Node.js 主进程 | 窗口管理、IPC 路由、Bridge 生命周期 |
| Electron Renderer | Chromium 渲染进程 | React UI 渲染、用户交互 |
| Bridge Server | Python 子进程 | 协议解析、请求分发、Agent 执行 |
| MCP Servers | 独立子进程 | 外部工具服务，通过 MCP 协议通信 |
