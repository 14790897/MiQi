# Runtime 引擎

`miqi/runtime/` 是 MiQi 的核心运行时引擎，负责管理会话生命周期、将任务映射到执行、驱动 LLM 调用与工具循环。

> **Historical**: 旧版 `AgentLoop` (`miqi/agent/loop.py`) 已在 Phase 48 移除，由 RuntimeSession / TaskRunner / TurnRunner 取代。

## RuntimeSession

`RuntimeSession` (`miqi/runtime/session.py`) 管理一次会话的完整运行时生命周期。

### 核心职责

- 通过 `RuntimeServices` 构造运行时服务图（工具注册表、上下文运行时、工具运行时、TurnRunner 等）
- 通过 `RuntimeClient.ask()` 接收用户消息并返回响应
- 管理会话级锁以序列化同一会话内的请求

### 核心参数

| 参数 | 类型 | 说明 |
|------|------|------|
| `provider` | Provider | LLM 提供商实例 |
| `workspace` | Path | 工作区目录 |
| `model` | str | 使用的模型名称 |
| `temperature` | float | 生成多样性控制 |
| `max_tool_iterations` | int | 最大工具调用轮次 |
| `max_tokens` | int | 单次响应最大 Token |

## TaskRunner

`TaskRunner` (`miqi/runtime/task_runner.py`) 将用户任务映射到 TurnRunner 的执行。

### 核心职责

- 接收 UserMessage，管理任务级状态
- 协调多次 TurnRunner 调用以完成一个任务
- 管理任务上下文与结果收集

## TurnRunner

`TurnRunner` (`miqi/runtime/turn_runner.py`) 拥有 provider.chat + 工具调用循环。从旧版 `AgentLoop._run_agent_loop` 提取而来。

### 核心职责

- 调用 LLM provider 进行流式响应
- 将工具调用路由至 ToolRuntime
- 通过 ContextRuntime 构建和压紧消息
- 返回 TurnResult 给 TaskRunner

### 处理流程

1. **接收消息**：从 Bridge 或 CLI 接收用户输入，通过 RuntimeSession 进入
2. **构建上下文**：调用 `ContextRuntime` 组装系统提示词（注入 SOUL.md、Memory、Trace 等）
3. **TurnRunner LLM 调用**：向配置的 Provider 发送请求，流式接收响应
4. **工具执行**：解析 Function Calling 响应，通过 `ToolRuntime` 和 `ToolRegistry` 执行
5. **循环迭代**：将工具结果反馈给 LLM，直到任务完成或达到最大轮次
6. **记忆持久化**：通过 Nudge 系统触发记忆和技能的持久化

## ContextRuntime

`ContextRuntime` (`miqi/runtime/context_runtime.py`) 管理 turn 消息历史和上下文压紧：

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

集成在 `TurnRunner` / `TaskRunner` 中的任务追踪器，负责：

- 自动调用 `task_begin` / `task_end` 标记任务边界
- 记录工具调用链到 `TraceStore`
- 任务结束时自动触发嵌入和索引
- Nudge 间隔可配置（默认 8 轮）

## 子代理支持

`SubagentManager` 允许通过 `SpawnTool` 启动子代理处理子任务：

- 独立的上下文窗口
- 受限的工具权限
- 异步并发执行
- 自动结果收集

## 错误处理

- **重试机制**：LLM 调用失败自动重试
- **工具超时**：每个工具有独立超时控制，由 `ToolRuntime` 管理
- **优雅降级**：工具执行失败不中断对话流程
- **异常上报**：通过 Bridge 事件向 UI 报告错误
