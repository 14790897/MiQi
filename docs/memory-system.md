# Memory System

MiQi uses a **RAM-first memory architecture** that keeps the hot path in-memory and moves disk writes to checkpoint events. This design avoids per-turn disk I/O, eliminates embedding/vector system dependencies, and keeps memory behavior deterministic and inspectable.

By default, all runtime data below lives under `~/.miqi/workspace/`. If you change `agents.defaults.workspace`, the memory and session paths move with it.

---

## Design Goals

- Keep turn-time memory access in RAM
- Preserve long-term memory across restarts
- Avoid embedding/vector dependencies
- Keep implementation small and auditable

---

## Architecture

Memory is split into three layers:

### 1. Short-Term Working Memory (RAM only)

- Per-session turn window (configurable size)
- Per-session pending item queue
- Used for immediate continuity within a session
- Never persisted to disk

### 2. Long-Term Snapshot Memory (RAM-first)

- In-memory long-term items are updated during turns
- Persisted to `<workspace>/memory/LTM_SNAPSHOT.json` at checkpoint events
- Optional audit log at `<workspace>/memory/LTM_AUDIT.jsonl`

### 2.5. Self-Improvement Lessons (RAM-first)

- In-memory lessons are derived from tool failures and user corrections
- Persisted to `<workspace>/memory/LESSONS.jsonl` at checkpoint events
- Optional audit log at `<workspace>/memory/LESSONS_AUDIT.jsonl`
- See [Self-Improvement](self-improvement.md) for full details

### 3. Session Log Storage (append-only)

- Conversation messages append to `<workspace>/sessions/*.jsonl`
- Periodic compaction rewrites to keep only recent history
- The repository also ships `miqi/session/sqlite_store.py`, an optional SQLite+FTS5 backend module. The current CLI/gateway path still instantiates the JSONL `SessionManager` by default.

---

## Data Model

**Long-term snapshot item:**

```json
{
  "id": "ltm_1739443200123_1",
  "text": "User prefers concise Chinese replies",
  "source": "explicit_user",
  "session_key": "telegram:12345",
  "created_at": "2026-02-13T09:01:10.223000",
  "updated_at": "2026-02-13T09:05:40.119000",
  "hits": 2
}
```

---

## Write Path

On each turn:

1. Update short-term ring buffer in RAM
2. Detect explicit memory intents (e.g. `remember ...`)
3. Upsert long-term snapshot item in RAM
4. Flush to disk when one of these triggers fires:
   - dirty updates ≥ `flushEveryUpdates`
   - elapsed time ≥ `flushIntervalSeconds`
   - explicit immediate flush (stronger durability)
   - process stop

---

## Read Path

During prompt build:

1. Read long-term snapshot items from RAM (normalized lexical relevance + recency scoring)
2. Read top self-improvement lessons from RAM
3. Add human-readable `MEMORY.md` notes if present
4. Add short-term working memory and pending items for the current session

This keeps read latency constant and avoids per-turn disk reads.

---

## Durability Semantics

| Update Type | Durability |
|---|---|
| Normal memory update | Eventual (checkpointed) |
| Explicit memory update (`remember ...`) | Immediate flush |
| Crash window | Up to checkpoint interval for non-immediate updates |

Memory state writes are guarded by an in-process re-entrant lock for concurrent async entrypoints.

---

## Compaction

**Long-term snapshot compaction:**

- Deduplicates by normalized text
- Keeps newest items first
- Enforces max item cap
- Triggers only when snapshot grows beyond cap buffer

**Session compaction:**

- Triggered by message count or file size threshold
- Rewrites session file with metadata + recent N messages only

---

## Failure Behavior

| Scenario | Behavior |
|---|---|
| Corrupt snapshot file | Fallback to empty RAM state for this run |
| Audit write failure | Surfaced in logs; treat as operational issue |
| Session file growth | Bounded by periodic compaction |

---

## Why No Embeddings

This design avoids embedding/vector systems to preserve MiQi's lightweight footprint:

- No extra service dependencies (no Chroma, Qdrant, etc.)
- No vector index build/maintenance cost
- Deterministic, inspectable memory behavior

---

## Management Commands

```bash
miqi memory status
miqi memory list [--limit N] [--session S]
miqi memory delete <id>
miqi memory flush
miqi memory compact [--max-items N]

miqi session compact --session <id>
miqi session compact --all
```

For lesson management, see [Self-Improvement](self-improvement.md#management-commands).
