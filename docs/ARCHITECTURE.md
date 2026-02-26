# FeatherFlow Architecture

## System Overview

FeatherFlow follows a "message bus + agent loop + tool system + channel adapters" architecture:

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
- Processing: `AgentLoop.process_*` -> Provider -> optional tool calls
- Output: `OutboundMessage` -> Channel
- Memory update: `MemoryStore.record_turn` updates short-term and long-term state per turn

## Key Design Points

- RAM-first memory: runtime operates from memory, flushes to disk by thresholds
- Tool registry: decouples tool definitions, validation, and execution
- Provider abstraction: unifies chat interface and reduces upper-layer coupling
- Session compaction: controls context size while preserving readable history

## CLI Architecture

- `commands.py` is the entrypoint and compatibility layer
- Submodules register commands by functional domain to keep files focused
