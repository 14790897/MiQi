# Architecture

## System Overview

MiQi follows a **message bus + agent loop + tool system + channel adapters** architecture:

1. **Channels** receive external messages and publish them to `MessageBus.inbound`
2. **AgentLoop** consumes messages, builds context (session + memory + skills), and calls the LLM
3. External capabilities are executed through **ToolRegistry**
4. Responses are published to `MessageBus.outbound` and delivered back by channels

```
 ┌─────────────────────────────────────────────────────────┐
 │  Channel Adapters (Feishu / Telegram / Discord / ...)   │
 └─────────────────┬───────────────────────────────────────┘
                   │ InboundMessage
                   ▼
 ┌─────────────────────────────────────────────────────────┐
 │  MessageBus (inbound queue / outbound queue)            │
 └─────────────────┬───────────────────────────────────────┘
                   │
                   ▼
 ┌─────────────────────────────────────────────────────────┐
 │  AgentLoop                                              │
 │    ├── ContextBuilder (session + memory + skills)       │
 │    ├── LLM Provider (OpenAI / Anthropic / ...)         │
 │    └── ToolRegistry (filesystem / shell / web / MCP)   │
 └─────────────────────────────────────────────────────────┘
```

## Core Modules

| Module | File | Responsibility |
|---|---|---|
| Agent loop | `agent/loop.py` | Main loop, tool-call orchestration, MCP lifecycle |
| Context builder | `agent/context.py` | Context assembly: session, memory, skills |
| Memory store | `agent/memory/store.py` | `MemoryStore` facade over all memory sub-systems |
| Snapshot memory | `agent/memory/snapshot.py` | Long-term RAM-first snapshot with disk checkpoints |
| Lessons | `agent/memory/lessons.py` | Self-improvement lesson extraction and storage |
| NLP helpers | `agent/memory/nlp.py` | Text normalization and relevance scoring |
| LLM providers | `providers/` | Multi-provider adapters unified under a single interface |
| Channel adapters | `channels/` | IM and messaging platform adapters |
| Tool registry | `agent/tools/registry.py` | Tool registration, discovery, and dispatch |
| Built-in tools | `agent/tools/` | `filesystem`, `shell`, `web`, `papers`, `cron`, `spawn`, `message` |
| Cron service | `cron/service.py` | Scheduled task execution engine |
| Session manager | `session/manager.py` | Session persistence and compaction |
| CLI | `cli/` | Entry point and subcommand modules |

## Data Flow

```
Input:   Channel adapter → InboundMessage (with sender identity, channel metadata)
          ↓
Process: AgentLoop.process_*
          ├── ContextBuilder assembles: session history + memory items + lessons + skill files
          ├── LLM Provider generates response (streaming or blocking)
          └── If tool calls: ToolRegistry dispatches → tool executes → result fed back
          ↓
Output:  OutboundMessage → Channel adapter delivers to user
          ↓
Memory:  MemoryStore.record_turn updates short-term ring buffer and long-term snapshot
```

## Key Design Principles

- **RAM-first memory**: runtime operates entirely from in-memory structures; disk writes happen only at checkpoint events. See [Memory System](memory-system.md).
- **Tool registry**: decouples tool definitions (schema), validation, and execution; MCP tools and built-in tools share the same dispatch interface.
- **Provider abstraction**: all LLM providers implement a unified `BaseProvider` interface; the agent loop calls `provider.chat(messages, tools)` without knowing which backend is in use.
- **Session compaction**: `SessionManager` rewrites session files periodically to keep context size bounded while preserving readable history.

## Group Chat Message Filtering

Feishu (and other group-capable channels) supports @mention filtering:

- When `channels.feishu.requireMentionInGroups` is `true` (default), group chat messages are only forwarded to the agent if the bot is explicitly @mentioned.
- Private (p2p) chats always pass through.
- The @mention placeholder is stripped from the message text before it reaches the agent.

## Task Queue and User Notifications

`AgentLoop` processes messages serially. When busy, new messages enter a pending queue managed by `TaskTracker`:

- Senders receive a queue position notification (e.g. "You are #2 in queue").
- When a task starts, the sender is notified.
- CLI and system messages bypass the queue.
- Controlled by `channels.sendQueueNotifications` config (default `true`).

## MCP Tool Progress Reporting

Long-running MCP tool calls support two kinds of progress feedback:

1. **SDK progress** — if the MCP server sends progress events, they are forwarded to the user as percentage updates.
2. **Heartbeat** — `MCPToolWrapper` starts a background timer that sends elapsed-time messages every `progressIntervalSeconds` (default 15s), independent of the MCP server. The heartbeat is cancelled when the tool returns.

## CLI Architecture

| File | Role |
|---|---|
| `cli/commands.py` | Entry point and compatibility exports |
| `cli/onboard.py` | Onboarding command |
| `cli/agent_cmd.py` | `miqi agent` command |
| `cli/gateway_cmd.py` | `miqi gateway` command |
| `cli/management.py` | channels / memory / session / cron / status / provider commands |
| `cli/config_cmd.py` | `miqi config` subcommands |
