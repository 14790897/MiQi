# 配置参考

MiQi Desktop 的全局配置存储在 `~/.miqi/config.json` 中。

## 配置文件位置

| 操作系统 | 路径 |
|----------|------|
| Linux / macOS | `~/.miqi/config.json` |
| Windows | `C:\Users\{username}\.miqi\config.json` |

## 完整配置结构

```json
{
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
    "restrict_to_workspace": true,
    "web": {
      "search_provider": "brave",
      "brave_api_key": ""
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

### tools — 工具配置

| 字段 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `restrict_to_workspace` | bool | true | 文件操作限制在工作区 |
| `web.search_provider` | string | "brave" | 搜索引擎 (brave/ollama/hybrid) |
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
