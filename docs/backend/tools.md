# 工具系统

工具系统通过 `ToolRegistry`（`miqi/agent/tools/registry.py`）统一管理所有 Agent 可用工具，并通过 `ToolOrchestrator`（`miqi/execution/orchestrator.py`）执行四阶段安全管道。

## 工具注册架构

```
ToolRegistry
├── 内置工具 (Built-in) — 16 个工具
│   ├── filesystem:    read_file, write_file, edit_file, list_dir
│   ├── apply_patch:   apply_patch (Unified Diff)
│   ├── web:           web_search, web_fetch
│   ├── shell:         exec
│   ├── memory:        memory_read, memory_write, memory_append
│   ├── message:       message
│   ├── skill:         skill_manage
│   ├── session:       session_search
│   ├── cron:          cron_create, cron_list, cron_delete
│   ├── papers:        paper_search, paper_get, paper_download
│   ├── task_trace:    task_begin, task_end, trace_search
│   ├── spawn:         agent_spawn
│   └── mcp:           MCP 工具代理
└── MCP 工具 (External) — 通过 MCP Client 动态加载
    ├── raspa-mcp:     create_workspace, simulate, parse_output, ...
    ├── zeopp-backend: pore_analysis, ...
    └── ... (7 个 MCP 服务)
```

## 工具接口

```python
class Tool:
    name: str           # 工具名称 (LLM function name)
    description: str    # 工具描述
    parameters: dict    # JSON Schema 参数定义

    async def execute(self, params: dict, context: ToolContext) -> ToolResult:
        """执行工具，返回结果"""
        ...

class ToolResult:
    success: bool
    content: str        # 文本结果
    metadata: dict      # 额外元数据
```

## ToolOrchestrator 执行管道

所有工具执行通过 `ToolOrchestrator` 四阶段管道：

```
审批 (ApprovalPolicy) → 沙箱选择 (SandboxPolicyEngine) → 执行 (ToolRegistry) → 重试 (指数退避)
```

### 阶段 1: 审批

`ApprovalPolicy` 根据 `ApprovalMode` 决定是否需要用户确认：

- `AUTO` — 自动批准（内置安全工具）
- `ASK` — 每次询问用户
- `DENY` — 拒绝执行

### 阶段 2: 沙箱选择

`SandboxPolicyEngine` 根据工具类型和参数选择沙箱：

- `NONE` — 无需沙箱（纯文本操作）
- `BWRAP` — bwrap 沙箱（Shell 命令执行）
- `WORKSPACE_ONLY` — 仅限工作区（文件操作）

### 阶段 3: 执行

通过 `ToolRegistry` 实际执行工具，支持串行和并行模式。

### 阶段 4: 重试

`ExecPolicy` 控制重试行为，指数退避重试瞬时错误。

## 内置工具详解

### 文件系统工具

| 工具 | 功能 | 安全限制 |
|------|------|----------|
| `read_file` | 读取文件内容 | 仅限工作区 |
| `write_file` | 写入/创建文件 | 自动创建快照 |
| `edit_file` | 精确字符串替换 | 仅限工作区 |
| `list_dir` | 列出目录 | 仅限工作区 |
| `apply_patch` | Unified Diff 补丁应用 | 版本快照 |

### 网络工具

| 工具 | 功能 | 后端 |
|------|------|------|
| `web_search` | 搜索互联网 | Brave / SearXNG / Hybrid |
| `web_fetch` | 获取网页内容 | readability-lxml 解析 |

### 执行工具

| 工具 | 功能 | 安全机制 |
|------|------|----------|
| `exec` | Shell 命令执行 | bwrap 沙箱 + LANDLOCK 规则 |

> 命令执行通过 `command/exec` 和 `process/*` AppServer 协议方法支持流式 I/O、PTY 调整和进程快照。

## MCP 工具特性

外部 MCP 工具通过 Model Context Protocol 集成：

- **心跳进度**：长时任务每 15 秒报告进度
- **超时控制**：每个 MCP 工具可独立设置超时（如 RASPA GCMC 6 小时）
- **延迟加载**：按需启动 MCP 服务器，节省资源
- **连接复用**：MCP 进程保持存活，避免重复启动

## 安全机制

1. **工作区隔离**：文件操作默认限制在 `workspace` 目录（`restrict_to_workspace: true`）
2. **危险命令审批**：39 种危险命令模式需用户确认（`miqi/agent/command_approval.py`）
3. **bwrap 沙箱**：LANDLOCK 文件系统规则，FIFO 驱逐（最多 10 个）
4. **快照保护**：文件写入前自动创建原始内容快照，支持回滚
5. **超时终止**：工具执行超时自动中断
6. **默认拒绝**：PermissionEngine 采用 deny-by-default 策略

## Hook 系统

`HookRuntime` 支持在工具执行生命周期中注入自定义行为：

| Hook 点 | 触发时机 |
|----------|----------|
| `pre_tool` | 工具执行前 |
| `post_tool` | 工具执行后 |
| `on_error` | 工具执行出错时 |

## 相关文档

- [Runtime 引擎](agent.md) — RuntimeSession / TaskRunner / TurnRunner
- [Bridge 通信](bridge.md) — Bridge Server 工具调用处理
