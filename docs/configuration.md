# 配置参考

MiqroForge Desktop 的全局配置存储在 `~/.miqi/config.json` 中。

## 配置文件位置

| 操作系统 | 路径 |
|----------|------|
| Linux / macOS | `~/.miqi/config.json` |
| Windows | `C:\Users\{username}\.miqi\config.json` |

## 完整配置结构

```json
{
  "approvals": {
    "bypassAll": false,
    "bypassCommandApproval": false,
    "bypassFileWriteApproval": false,
    "bypassToolConfirmation": false,
    "bypassNetworkApproval": false
  },
  "providers": {
    "openai": {
      "apiKey": "sk-...",
      "apiBase": "https://api.openai.com/v1",
      "defaultModel": "gpt-4o"
    }
  },
  "agents": {
    "defaults": {
      "model": "gpt-4o",
      "temperature": 0.1,
      "max_tool_iterations": 100,
      "max_tokens": 16000,
      "memory_window": 100,
      "name": "miqi",
      "workspace": "~/.miqi/workspace"
    },
    "self_improvement": {
      "trace_enabled": true,
      "embedding_model": "intfloat/multilingual-e5-small",
      "trace_inject_top_k": 3,
      "trace_similarity_threshold": 0.65,
      "trace_nudge_interval": 8,
      "lessons_legacy_inject_enabled": false
    },
    "command_approval": {
      "enabled": true,
      "timeout": 60
    }
  },
  "tools": {
    "restrict_to_workspace": false,
    "extra_roots": [],
    "web": {
      "search": {
        "provider": "ddgs",
        "apiKey": "",
        "maxResults": 5
      },
      "fetch": {
        "provider": "builtin"
      }
    },
    "exec": {
      "allowed_commands": [],
      "blocked_commands": ["rm -rf /", "format"]
    },
    "mcp_servers": {}
  },
  "channels": {},
  "cron": {
    "job_timeout_seconds": 86400
  }
}
```

## 配置项详解

### providers — LLM 提供商

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `apiKey` | string | 是 | 提供商 API 密钥 |
| `apiBase` | string | 否 | 自定义 API 地址 |
| `defaultModel` | string | 否 | 默认使用模型 |

### agents.defaults — Agent 默认参数

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `model` | string | "gpt-4o" | 默认 LLM 模型 |
| `temperature` | float | 0.1 | 生成多样性 (0-2) |
| `max_tool_iterations` | int | 100 | 单次对话最大工具调用轮次 |
| `max_tokens` | int | 16000 | 单次响应最大 Token |
| `memory_window` | int | 100 | 对话记忆窗口大小 |
| `name` | string | "miqi" | Agent 默认名称 |
| `workspace` | string | "~/.miqi/workspace" | 默认工作区路径 |

### agents.self_improvement — 自改进系统

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `trace_enabled` | bool | true | 启用任务追踪 |
| `embedding_model` | string | 多语言E5 | 嵌入模型名称 |
| `trace_inject_top_k` | int | 3 | 注入相似历史任务数 |
| `trace_similarity_threshold` | float | 0.65 | 相似度阈值 |
| `trace_nudge_interval` | int | 8 | Nudge 间隔 (轮) |
| `lessons_legacy_inject_enabled` | bool | false | 启用旧版 Lessons 注入 |

### approvals - approval bypass

These switches skip approval prompts while keeping explicit deny rules and
parameter validation active. When any bypass switch is enabled, MiqroForge Desktop
shows a persistent warning in the top bar.

| Field | Type | Default | Description |
|------|------|--------|-------------|
| `bypassAll` | bool | false | Skip every approval prompt. |
| `bypassCommandApproval` | bool | false | Skip command execution approval prompts. |
| `bypassFileWriteApproval` | bool | false | Skip file mutation approval prompts. |
| `bypassToolConfirmation` | bool | false | Skip generic tool confirmation prompts. |
| `bypassNetworkApproval` | bool | false | Reserved for network approval prompts. |

### tools — 工具配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `restrict_to_workspace` | bool | false | 文件操作限制在工作区 |
| `extra_roots` | array | [] | 文件工具额外允许的根目录（支持 workspace 外目录，WSL 沙箱白名单） |
| `web.search.provider` | string | "ddgs" | 搜索引擎 (ddgs/brave/hybrid) |
| `web.search.apiKey` | string | "" | Brave Search API Key，仅 brave/hybrid 使用 |
| `web.search.maxResults` | int | 5 | 最大搜索结果数量 |
| `exec.allowed_commands` | array | [] | Shell 命令白名单 |
| `exec.blocked_commands` | array | [] | Shell 命令黑名单 |

### tools.mcp_servers — MCP 服务器

每个 MCP 服务器可配置：

| 字段 | 类型 | 说明 |
|------|------|------|
| `command` | string | 启动命令 |
| `args` | array | 命令参数 |
| `env` | object | 环境变量 |
| `toolTimeout` | int | 工具超时 (秒) |
| `lazy` | bool | 延迟加载 |
| `progressIntervalSeconds` | int | 心跳间隔 (秒) |

### observability — OpenTelemetry 可观测性

默认关闭。启用并安装可选依赖后，运行时事件将导出为 OpenTelemetry traces 和 metrics。

安装依赖: `pip install miqi[otel]`

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `enabled` | bool | false | 启用 OTel 导出 |
| `endpoint` | string | null | OTLP gRPC/HTTP 端点 URL |
| `serviceName` | string | "miqi" | 服务名称标签 |
| `consoleExport` | bool | false | 输出到控制台 (开发调试用) |
| `sampleRatio` | float | 1.0 | 采样率 (0-1) |
| `captureContent` | bool | false | 捕获消息文本到 Span 属性 (隐私敏感，默认不捕获) |

## 环境变量

| 变量 | 说明 | 示例 |
|------|------|------|
| `MIQI_PYTHON_PATH` | 自定义 Python 解释器 | `/usr/bin/python3.12` |
| `MIQI_AGENTS__DEFAULTS__MODEL` | 覆盖默认模型 | `claude-sonnet-4-20250514` |

环境变量使用双下划线 `__` 分隔嵌套键，优先级高于配置文件。

## 配置热更新

通过 `config:set` IPC 更新配置后：

1. 验证新配置的合法性（Pydantic 校验）
2. 写入 `~/.miqi/config.json`
3. 通知运行中的 Agent 重新加载
4. 部分配置（如 MCP 服务器）需要重启 Python 子进程

### 热生效类别（A / B / C）

每个设置项按保存后的生效方式分为三类（issue #789）：

| 类别 | 含义 | 保存后提示 | 设置项 |
|------|------|-----------|--------|
| **A 热生效** | 保存即生效，无需重启 | 「已生效」 | `tools.sandbox.enabled`（沙箱运行时启停）、`channels.*`（渠道）、`approvals.*`（审批绕过）、`agents.defaults.temperature/maxTokens`、`tools.web.*` 等 |
| **B 新建会话生效** | 对新建会话立即生效；正在进行的会话继续使用旧配置 | 「已保存，对新建会话生效」 | `providers.*`（API Key / Base URL / 模型）、`agents.defaults.model` |
| **C 必须重启** | 进程级配置，仅重启后生效 | 「需要重启（原因）」+ 状态栏一键重启 | Python 解释器路径、WSL 发行版名称、`workspace` 等 |

实现说明：保存时 Bridge 内存中的 config 引用会即时更新（`state.config`），`config.update` 还会把新配置传播到活跃会话的 `config_snapshot`；仅 C 类变更触发状态栏「需要重启」标记。
