# 数据流

## 用户消息 → AI 响应的完整链路

```
User Input (ChatConsole)
  │
  ▼
ipcRenderer.invoke("chat:send", { message, sessionId })
  │  [Zod 验证请求参数]
  ▼
Main Process → IPC Handler (bridge:chat-send)
  │
  ▼
BridgeManager.send(message)
  │  [JSON-line 写入 Bridge 子进程 stdin]
  ▼
Bridge Server (miqi/bridge/server.py)
  │  handle_chat_send() → AgentLoop.process_direct()
  ▼
ContextBuilder.build_system_prompt()
  │  [注入 SOUL.md / IDENTITY.md / Memory / Trace 上下文]
  ▼
LLM Provider (OpenAI / Anthropic / Gemini / ...)
  │  [流式响应 + Function Calling]
  ▼
Tool Execution
  │  ToolRegistry.execute_concurrent()
  │  ├── 内置工具 (read_file, write_file, web_search, exec, ...)
  │  └── MCP 工具 (raspa-mcp, zeopp-backend, ...)
  ▼
Streaming Events → stdout JSON-line
  │  progress / final / error events
  ▼
BridgeManager.parseLine() → ipcMain.emit()
  │
  ▼
React Renderer
  │  ChatConsole 实时渲染 Markdown + 代码高亮
  │  工具调用进度实时更新
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

- **多会话并行**：每个会话维护独立的 `AgentLoop` 实例，互不阻塞
- **工具并行**：`ToolRegistry` 支持批量工具的并发执行
- **MCP 心跳**：长时运行的工具通过心跳机制报告进度
