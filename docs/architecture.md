# 系统架构

## 分层架构

MiQi Desktop 采用 **三层分离架构**：

### 前端层 + 通信协议

```mermaid
graph TB
    subgraph MP [Main Process - Node.js]
        BW[BrowserWindow 管理]
        BM[BridgeManager Python子进程]
        IPC[IPC Handler 注册路由]
        API[系统原生 API]
    end

    subgraph PS [Preload Script]
        CB[contextBridge 安全API暴露]
        NS[window.miqi 命名空间]
    end

    subgraph RP [Renderer Process - Chromium]
        RC[React 19 应用]
        PGS[15个功能页面]
        TW[Tailwind CSS 4 样式]
    end

    MP --> PS
    PS --> RP
```

### Python 后端 + 工具层

```mermaid
graph TB
    BS[Bridge Server - 57个handler]
    R{请求路由}

    BS --> R

    subgraph AgentEngine [Agent 引擎]
        TR[TurnRunner - LLM调用循环]
        CTX[ContextBuilder - 注入上下文]
    end

    subgraph ToolSystem [工具系统]
        FS[文件操作]
        NET[网络工具]
        EXEC[Shell执行]
        MCP_C[MCP Client]
    end

    subgraph MemorySys [记忆系统]
        CLOUD[Cloud Memory]
        USR[User Memory]
        WSP[Workspace Memory]
    end

    subgraph Infra [基础设施]
        SM[Session Manager]
        TS[Trace Store]
        CFG[Config Loader]
    end

    R --> AgentEngine
    R --> ToolSystem
    R --> MemorySys
    R --> Infra

    AL --> CTX
    AL --> ToolSystem
    MCP_C --> MCPS[MCP 工具服务器集群]
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
| AppServer (Codex 协议) | Python 子进程 (Bridge 内) | 工作区文件操作、文件监听、模糊搜索、进程管理 |
| MCP Servers | 独立子进程 | 外部工具服务，通过 MCP 协议通信 |

### AppServer Codex 协议 API

Bridge Server 内置 AppServer 层，实现 Codex 风格的应用服务器协议，
提供以下方法族：

**文件系统 API (fs/\*)**

| 方法 | 说明 |
|------|------|
| `fs/readFile` | 读取文件，返回 base64 编码字节 |
| `fs/writeFile` | 写入 base64 编码字节到文件 |
| `fs/createDirectory` | 创建目录（支持递归） |
| `fs/getMetadata` | 获取路径元数据（isFile/isDirectory/isSymlink/时间戳） |
| `fs/readDirectory` | 列出目录直接子项（按名称排序） |
| `fs/remove` | 删除文件或目录（支持递归和 force 模式） |
| `fs/copy` | 复制文件或目录 |

所有 fs/\* 操作均通过工作区根路径进行容器化隔离，
并解析符号链接以防止逃逸。

**文件监听 API (fs/watch, fs/unwatch)**

轮询式文件系统监听，按 `(client_id, watchId)` 作用域隔离。
变化通过 `fs/changed` 通知事件推送。

**模糊搜索 API (fuzzyFileSearch\*)**

确定性的文件名模糊搜索，采用两层评分策略
（子串匹配 ≥1000，子序列匹配 ≥500）。会话式方法
(`sessionStart/sessionUpdate/sessionStop`) 通过
`experimentalApi` 门控。搜索结果通过
`fuzzyFileSearch/sessionUpdated` 和 `fuzzyFileSearch/sessionCompleted` 事件推送。
