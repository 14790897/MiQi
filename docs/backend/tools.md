# 工具系统

工具系统通过 `ToolRegistry`（`miqi/agent/tools/registry.py`）统一管理所有 Agent 可用工具。每个工具实现 `ToolBase` 接口。

## 工具注册架构

```
ToolRegistry
├── 内置工具 (Built-in)
│   ├── filesystem:    read_file, write_file, edit_file, list_dir
│   ├── web:           web_search, web_fetch
│   ├── shell:         exec
│   ├── memory:        memory_read, memory_write, memory_append
│   ├── skill:         skill_manage
│   ├── session:       session_search
│   ├── cron:          cron_create, cron_list, cron_delete
│   ├── papers:        paper_search, paper_get, paper_download
│   ├── task_trace:    task_begin, task_end, trace_search
│   └── spawn:         agent_spawn
└── MCP 工具 (External)
    ├── raspa-mcp:     create_workspace, simulate, parse_output, ...
    ├── zeopp-backend: pore_analysis, ...
    └── ... (7个 MCP 服务)
```

## 工具接口

```python
class ToolBase:
    name: str           # 工具名称 (LLM function name)
    description: str    # 工具描述 (LLM function description)
    parameters: dict    # JSON Schema 参数定义

    async def execute(self, params: dict) -> ToolResult:
        """执行工具，返回结果"""
        ...

class ToolResult:
    success: bool
    content: str        # 文本结果
    metadata: dict      # 额外元数据
```

## 内置工具详解

### 文件系统工具

| 工具 | 功能 | 安全限制 |
|------|------|----------|
| `read_file` | 读取文件内容 | 仅限工作区 |
| `write_file` | 写入/创建文件 | 自动创建快照 |
| `edit_file` | 精确字符串替换 | 仅限工作区 |
| `list_dir` | 列出目录 | 仅限工作区 |

### 网络工具

| 工具 | 功能 | 后端 |
|------|------|------|
| `web_search` | 搜索互联网 | Brave / Ollama / Hybrid |
| `web_fetch` | 获取网页内容 | readability-lxml 解析 |

### 执行工具

| 工具 | 功能 | 安全机制 |
|------|------|----------|
| `exec` | Shell 命令执行 | 沙箱限制 + 命令白名单/黑名单 |

## MCP 工具特性

外部 MCP 工具通过 Model Context Protocol 集成：

- **心跳进度**：长时任务每 15 秒报告进度
- **超时控制**：每个 MCP 工具可独立设置超时（如 RASPA GCMC 6小时）
- **延迟加载**：按需启动 MCP 服务器，节省资源
- **环境继承**：子进程继承当前环境变量
- **连接复用**：MCP 进程保持存活，避免重复启动

## 工具执行

```python
# 串行执行
result = await registry.execute("read_file", {"path": "/path/to/file"})

# 并行执行
results = await registry.execute_concurrent([
    ToolCall(name="web_search", params={"query": "..."}),
    ToolCall(name="read_file", params={"path": "..."}),
])
```

## 安全机制

1. **工作区隔离**：文件操作默认限制在 `workspace` 目录（`restrict_to_workspace: true`）
2. **命令审批**：危险命令需用户确认（`command_approval.enabled: true`）
3. **快照保护**：文件写入前自动创建原始内容快照，支持回滚
4. **超时终止**：工具执行超时自动中断
