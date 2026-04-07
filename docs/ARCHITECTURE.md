# MiQi Architecture

## System Overview

MiQi follows a "message bus + agent loop + tool system + channel adapters" architecture:

1. Channels receive external messages and publish to `MessageBus.inbound`
2. `AgentLoop` consumes messages, builds context, and calls the LLM
3. External capabilities are executed through `ToolRegistry`
4. Responses are published to `MessageBus.outbound` and delivered by channels

## Core Modules

- `agent/loop.py`: main loop, tool-call orchestration, MCP lifecycle management
- `agent/context.py`: context assembly (session, memory, skills)
- `agent/memory/`:
  - `store.py`: `MemoryStore` facade
  - `snapshot.py`: long-term snapshot memory
  - `lessons.py`: self-improvement lessons
  - `nlp.py`: text normalization and relevance helpers
- `providers/`: multi-provider LLM adapters
- `channels/`: IM and messaging channel adapters
- `cron/`: scheduling and execution service

## Data Flow

- Input: Channel -> `InboundMessage`
- Metadata enrichment: channel adapters can attach routing context (sender identity, mentions, etc.)
- Processing: `AgentLoop.process_*` -> Provider -> optional tool calls
- Output: `OutboundMessage` -> Channel
- Memory update: `MemoryStore.record_turn` updates short-term and long-term state per turn

## Key Design Points

- RAM-first memory: runtime operates from memory, flushes to disk by thresholds
- Tool registry: decouples tool definitions, validation, and execution
- Provider abstraction: unifies chat interface and reduces upper-layer coupling
- Session compaction: controls context size while preserving readable history

## Group Chat Message Filtering

Feishu (and potentially other group-capable channels) supports @mention filtering:

- When `channels.feishu.requireMentionInGroups` is `true` (default), group chat messages
  are only forwarded to the agent if the bot is explicitly @mentioned.
- Private (p2p) chats always pass through.
- The @mention placeholder is stripped from the text before it reaches the agent.

## Task Queue & User Notifications

`AgentLoop` processes messages serially. When busy, new messages enter a pending queue
managed by `TaskTracker`:

- Senders receive a queue position notification (e.g. "You are #2 in queue").
- When a task starts, the sender is notified.
- CLI and system messages bypass the queue.
- Controlled by `channels.sendQueueNotifications` config.

## MCP Tool Progress Reporting

Long-running MCP tool calls support two kinds of progress feedback:

1. **SDK progress** — if the MCP server sends progress events, they are forwarded to the
   user as percentage updates.
2. **Heartbeat** — `MCPToolWrapper` starts a background timer that sends elapsed-time
   messages every `progressIntervalSeconds` (default 15s), independent of the MCP server.
   The heartbeat is cancelled when the tool returns.

## CLI Architecture

- `commands.py` is the entrypoint and compatibility layer
- Submodules register commands by functional domain to keep files focused
