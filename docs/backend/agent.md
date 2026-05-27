# Agent 引擎

`miqi/agent/` 是 MiQi 的核心处理引擎，负责接收消息、构建上下文、调用 LLM 并执行工具。

## AgentLoop

`AgentLoop`（`miqi/agent/loop.py`）是整个系统的中枢，管理一次对话的完整生命周期。

### 核心参数

| 参数 | 类型 | 默认值 | 说明 |
|------|------|--------|------|
| `provider` | Provider | (必填) | LLM 提供商实例 |
| `workspace` | Path | (必填) | 工作区目录 |
| `model` | str | "gpt-4o" | 使用的模型名称 |
| `temperature` | float | 0.1 | 生成多样性控制 |
| `max_tool_iterations` | int | 100 | 最大工具调用轮次 |
| `max_tokens` | int | 16000 | 单次响应最大 Token |
| `memory_window` | int | 100 | 对话记忆窗口 |
| `agent_name` | str | "miqi" | Agent 名称 |

### 处理流程

1. **接收消息**：从 Bridge 或 CLI 接收用户输入
2. **构建上下文**：调用 `ContextBuilder` 组装系统提示词
3. **LLM 调用**：向配置的 Provider 发送请求
4. **工具执行**：解析 Function Calling 响应，通过 `ToolRegistry` 执行
5. **循环迭代**：将工具结果反馈给 LLM，直到任务完成或达到最大轮次
6. **记忆持久化**：通过 Nudge 系统触发记忆和技能的持久化

### 子代理支持

`SubagentManager` 允许 Agent 通过 `SpawnTool` 启动子代理处理子任务：

- 独立的上下文窗口
- 受限的工具权限
- 异步并发执行
- 自动结果收集

## ContextBuilder

`ContextBuilder`（`miqi/agent/context.py`）负责构建发送给 LLM 的系统提示词，注入以下内容：

### 注入项

| 注入项 | 来源 | 说明 |
|--------|------|------|
| 工作区模板 | SOUL.md, IDENTITY.md, AGENTS.md | Agent 人格与行为定义 |
| 记忆指导 | Memory System | 长期记忆使用说明 |
| 技能列表 | Skills System | 可用技能清单与使用指导 |
| 会话搜索 | FTS5 Index | 跨会话上下文召回指导 |
| 历史追踪 | TraceStore | 最多 3 条相似历史任务上下文 |
| Nudge 提醒 | Nudge System | 定期提醒持久化记忆和技能 |

## TaskTracker

集成在 `AgentLoop` 中的任务追踪器，负责：

- 自动调用 `task_begin` / `task_end` 标记任务边界
- 记录工具调用链到 `TraceStore`
- 任务结束时自动触发嵌入和索引
- Nudge 间隔可配置（默认 8 轮）

## 错误处理

- **重试机制**：LLM 调用失败自动重试
- **工具超时**：每个工具有独立超时控制
- **优雅降级**：工具执行失败不中断对话流程
- **异常上报**：通过 Bridge 事件向 UI 报告错误
