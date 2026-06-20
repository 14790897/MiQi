# 数据流

## 用户消息 → AI 响应的完整链路

```mermaid
sequenceDiagram
    actor User as 👤 用户
    participant ChatConsole as ChatConsole<br/>(React Renderer)
    participant IPC as IPC Handler<br/>(Main Process)
    participant Bridge as BridgeManager<br/>(Python 子进程)
    participant Runtime as RuntimeSession<br/>/TaskRunner/TurnRunner
    participant Context as ContextBuilder
    participant LLM as LLM Provider
    participant Tools as ToolRegistry

    User->>ChatConsole: 输入消息
    ChatConsole->>IPC: ipcRenderer.invoke("chat:send")
    Note over IPC: Zod 参数验证
    IPC->>Bridge: bridge:chat-send
    Note over Bridge: JSON-line 写入 stdin

    Bridge->>Runtime: handle_chat_send()
    Runtime->>Context: build_system_prompt()
    Note over Context: 注入 SOUL.md / Memory / Trace
    Context-->>Agent: system prompt

    loop Turn Loop (TurnRunner)
        Runtime->>LLM: Chat Completion (stream)
        LLM-->>Bridge: 流式文本增量
        Bridge-->>IPC: progress event
        IPC-->>ChatConsole: 实时渲染 Markdown

        alt 需要工具调用
            LLM-->>Runtime: function_call
            Runtime->>Tools: execute_concurrent()

            par 内置工具
                Tools->>Tools: read_file / write_file / web_search
            and MCP 工具
                Tools->>Tools: raspa-mcp / zeopp-backend
            end

            Tools-->>Runtime: 工具结果
            Note over Bridge: tool_progress 心跳
        end
    end

    Runtime-->>Bridge: final event
    Bridge-->>ChatConsole: 完整响应
    ChatConsole-->>User: 渲染结果
```

## 事件类型

Bridge 协议支持三种事件流：

| 事件类型 | 方向 | 说明 |
|----------|------|------|
| `progress` | Backend → Frontend | LLM 流式输出增量文本 |
| `tool_progress` | Backend → Frontend | 工具调用进度（MCP 心跳） |
| `error` | Backend → Frontend | 异常错误信息 |

## 请求/响应模型

```
Request:  前端发起
  {"id": "uuid-001", "method": "chat:send", "params": {...}}

Response: 后端同步响应
  {"id": "uuid-001", "result": {...}}

Event: 后端流式推送
  {"id": "uuid-001", "type": "progress", "data": {"text": "..."}}
```

`id` 字段用于关联请求与对应的流式事件，前端通过 `id` 将事件路由到正确的对话窗口。

## 并发处理

- **多会话并行**：每个会话维护独立的 `RuntimeSession` 实例，互不阻塞
- **工具并行**：`ToolRegistry` 支持批量工具的并发执行
- **MCP 心跳**：长时运行的工具通过心跳机制报告进度
