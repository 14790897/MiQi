"""History runtime — persistent turn, message, and compaction history.

Owns SQLite storage for turn records, history items (messages),
compaction records, and provides load/append/query/replace methods
used by TaskRunner and ContextRuntime. One instance per workspace,
scoped to a single session for cross-session isolation.

Phase 19: adds runtime_compactions table and
replace_messages_with_compaction() for persistent context compaction.

Phase 22 hardening: uses a single persistent aiosqlite connection
instead of per-method connect() to prevent background-thread leaks
when the event loop shuts down.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite
from loguru import logger


VALID_HISTORY_ROLES = frozenset({
    "system",
    "user",
    "assistant",
    "tool",
    "developer",
    "unknown",
})
MAX_HISTORY_CONTENT_CHARS = 1_000_000
MAX_HISTORY_PAYLOAD_JSON_CHARS = 1_000_000
_TRUNCATED_SUFFIX = "<truncated>"


@dataclass(frozen=True)
class HistoryItem:
    """A single message or event in thread history."""

    item_id: str
    thread_id: str
    turn_id: str
    role: str
    content: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = field(default_factory=time.time)


@dataclass(frozen=True)
class TurnRecord:
    """Record of a single turn's lifecycle."""

    turn_id: str
    thread_id: str
    status: str
    started_at: float
    completed_at: float | None = None
    tools_used: list[str] = field(default_factory=list)
    token_usage: dict[str, int] = field(default_factory=dict)


class HistoryRuntime:
    """Persistent runtime history scoped to one session.

    All queries are filtered by session_id to prevent cross-session
    data access. Threads are implicitly scoped by the session that
    creates them.

    Uses a single persistent aiosqlite connection (opened in initialize(),
    closed in close()) to avoid background-thread leaks on event-loop
    shutdown.
    """

    def __init__(self, db_path: Path, *, session_id: str):
        self.db_path = db_path
        self.session_id = session_id
        self._db: aiosqlite.Connection | None = None

    # ── lifecycle ──────────────────────────────────────────────────────

    async def initialize(self) -> None:
        """Open persistent connection and create tables."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path), timeout=30)
        await self._db.execute("PRAGMA journal_mode=WAL")
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS runtime_turns (
                turn_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                status TEXT NOT NULL,
                started_at REAL NOT NULL,
                completed_at REAL,
                tools_used_json TEXT NOT NULL,
                token_usage_json TEXT NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS runtime_history_items (
                item_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS runtime_compactions (
                compaction_id TEXT PRIMARY KEY,
                thread_id TEXT NOT NULL,
                session_id TEXT NOT NULL,
                turn_id TEXT NOT NULL,
                messages_before INTEGER NOT NULL DEFAULT 0,
                messages_after INTEGER NOT NULL DEFAULT 0,
                tokens_saved INTEGER NOT NULL DEFAULT 0,
                replacement_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        await self._db.commit()

    async def close(self) -> None:
        """Close the persistent database connection.

        Safe to call multiple times; no-op if already closed or never
        initialized.
        """
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        """Return the persistent connection, raising if not initialized."""
        if self._db is None:
            raise RuntimeError(
                "HistoryRuntime.initialize() must be called before use"
            )
        return self._db

    # ── turns ──────────────────────────────────────────────────────────

    async def start_turn(self, turn_id: str, *, thread_id: str) -> None:
        db = self._conn
        await db.execute(
            """INSERT OR REPLACE INTO runtime_turns
               (turn_id, thread_id, session_id, status, started_at,
                completed_at, tools_used_json, token_usage_json)
               VALUES (?, ?, ?, ?, ?, NULL, ?, ?)""",
            (
                turn_id, thread_id, self.session_id, "running",
                time.time(), "[]", "{}",
            ),
        )
        await db.commit()

    async def complete_turn(
        self,
        turn_id: str,
        *,
        status: str,
        tools_used: list[str],
        token_usage: dict[str, int],
    ) -> None:
        db = self._conn
        await db.execute(
            """UPDATE runtime_turns
               SET status = ?, completed_at = ?, tools_used_json = ?,
                   token_usage_json = ?
               WHERE turn_id = ? AND session_id = ?""",
            (
                status,
                time.time(),
                json.dumps(tools_used),
                json.dumps(token_usage),
                turn_id,
                self.session_id,
            ),
        )
        await db.commit()

    async def get_turn(self, turn_id: str) -> TurnRecord | None:
        db = self._conn
        cursor = await db.execute(
            "SELECT * FROM runtime_turns WHERE turn_id = ? AND session_id = ?",
            (turn_id, self.session_id),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        # Issue #84: degrade on corrupted JSON columns instead of crashing
        # the whole turn load (parity with load_items, which already skips
        # corrupted payload_json with a warning).
        try:
            tools_used = json.loads(row["tools_used_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "Corrupted tools_used_json for turn %s, degrading to []: %s",
                turn_id, exc,
            )
            tools_used = []
        if not isinstance(tools_used, list):
            tools_used = []
        try:
            token_usage = json.loads(row["token_usage_json"])
        except (json.JSONDecodeError, TypeError) as exc:
            logger.warning(
                "Corrupted token_usage_json for turn %s, degrading to {}: %s",
                turn_id, exc,
            )
            token_usage = {}
        if not isinstance(token_usage, dict):
            token_usage = {}

        return TurnRecord(
            turn_id=row["turn_id"],
            thread_id=row["thread_id"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            tools_used=tools_used,
            token_usage=token_usage,
        )

    # ── history items ──────────────────────────────────────────────────

    async def append_item(self, item: HistoryItem) -> None:
        db = self._conn
        role = _validate_role(item.role)
        content = _sanitize_content(item.content)
        payload_json = _sanitize_payload(item.payload)
        await db.execute(
            """INSERT INTO runtime_history_items
               (item_id, thread_id, session_id, turn_id, role, content,
                payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.item_id,
                item.thread_id,
                self.session_id,
                item.turn_id,
                role,
                content,
                payload_json,
                item.created_at,
            ),
        )
        await db.commit()

    async def append_message(
        self,
        *,
        thread_id: str,
        turn_id: str,
        role: str,
        content: str,
        payload: dict[str, Any] | None = None,
    ) -> HistoryItem:
        item = HistoryItem(
            item_id=str(uuid.uuid4()),
            thread_id=thread_id,
            turn_id=turn_id,
            role=role,
            content=content,
            payload=payload or {},
        )
        await self.append_item(item)
        return item

    async def load_items(self, thread_id: str) -> list[HistoryItem]:
        db = self._conn
        cursor = await db.execute(
            """SELECT * FROM runtime_history_items
               WHERE thread_id = ? AND session_id = ?
               ORDER BY created_at ASC, rowid ASC""",
            (thread_id, self.session_id),
        )
        rows = await cursor.fetchall()
        results = []
        for row in rows:
            try:
                payload = json.loads(row["payload_json"])
            except (json.JSONDecodeError, TypeError) as exc:
                logger.warning(
                    "Skipping corrupted payload_json for item %s in thread %s: %s",
                    row["item_id"], thread_id, exc,
                )
                payload = {}
            results.append(HistoryItem(
                item_id=row["item_id"],
                thread_id=row["thread_id"],
                turn_id=row["turn_id"],
                role=row["role"],
                content=row["content"],
                payload=payload,
                created_at=row["created_at"],
            ))
        return results

    async def load_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Return provider-compatible message dicts for a thread."""
        items = await self.load_items(thread_id)
        messages: list[dict[str, Any]] = []
        for item in items:
            msg: dict[str, Any] = {"role": item.role, "content": item.content}
            msg.update(item.payload.get("message_fields", {}))
            messages.append(msg)
        return messages

    # ── Phase 36: delete turn items for rollback ───────────────────────

    async def delete_turn_items(self, thread_id: str, turn_ids: list[str]) -> int:
        """Delete all history items for given turn_ids in a thread.

        Returns the number of deleted rows.
        """
        if not turn_ids:
            return 0
        placeholders = ",".join("?" for _ in turn_ids)
        db = self._conn
        cursor = await db.execute(
            f"""DELETE FROM runtime_history_items
                WHERE session_id = ? AND thread_id = ?
                AND turn_id IN ({placeholders})""",
            (self.session_id, thread_id, *turn_ids),
        )
        await db.commit()
        return int(cursor.rowcount or 0)

    async def copy_thread_items(self, source_thread_id: str, dest_thread_id: str) -> int:
        """Copy all history items from source to destination thread.

        Returns the number of copied items.
        """
        source_items = await self.load_items(source_thread_id)
        copied = 0
        for item in source_items:
            await self.append_item(HistoryItem(
                item_id=str(uuid.uuid4()),
                thread_id=dest_thread_id,
                turn_id=item.turn_id,
                role=item.role,
                content=item.content,
                payload=dict(item.payload),
                created_at=item.created_at,
            ))
            copied += 1
        return copied

    # ── Phase 19: compaction persistence ───────────────────────────────

    async def replace_messages_with_compaction(
        self,
        thread_id: str,
        turn_id: str,
        replacement_messages: list[dict[str, Any]],
        *,
        messages_before: int = 0,
        messages_after: int = 0,
        tokens_saved: int = 0,
    ) -> None:
        """Replace all history items for a thread with compacted messages.

        Deletes existing items (scoped by session_id), inserts the
        replacement messages, and records a compaction row with full
        audit metadata.
        """
        db = self._conn
        compaction_id = str(uuid.uuid4())
        # Wrap in transaction so DELETE+INSERT+compaction record are atomic.
        # If the process crashes between DELETE and commit, the transaction
        # is rolled back and no history is lost.
        await db.execute("BEGIN")
        try:
            # Delete existing items for this thread (session-scoped)
            await db.execute(
                "DELETE FROM runtime_history_items WHERE thread_id = ? AND session_id = ?",
                (thread_id, self.session_id),
            )
            # Insert replacement messages
            for msg in replacement_messages:
                await db.execute(
                    """INSERT INTO runtime_history_items
                       (item_id, thread_id, session_id, turn_id, role, content,
                        payload_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        str(uuid.uuid4()),
                        thread_id,
                        self.session_id,
                        turn_id,
                        msg.get("role", "unknown"),
                        msg.get("content") or "",
                        json.dumps(
                            {
                                "message_fields": {
                                    k: v
                                    for k, v in msg.items()
                                    if k not in {"role", "content"}
                                },
                            },
                        ),
                        time.time(),
                    ),
                )
            # Record the compaction with full audit metadata
            await db.execute(
                """INSERT INTO runtime_compactions
                   (compaction_id, thread_id, session_id, turn_id,
                    messages_before, messages_after, tokens_saved,
                    replacement_json, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    compaction_id,
                    thread_id,
                    self.session_id,
                    turn_id,
                    messages_before,
                    messages_after,
                    tokens_saved,
                    json.dumps(replacement_messages),
                    time.time(),
                ),
            )
            await db.commit()
        except Exception:
            await db.execute("ROLLBACK")
            raise


def _validate_role(role: str) -> str:
    if role not in VALID_HISTORY_ROLES:
        raise ValueError(f"Invalid history role: {role!r}")
    return role


def _sanitize_content(content: str) -> str:
    if len(content) <= MAX_HISTORY_CONTENT_CHARS:
        return content
    logger.warning(
        "Truncating history content from {} to {} chars",
        len(content),
        MAX_HISTORY_CONTENT_CHARS,
    )
    return _truncate_text(content, MAX_HISTORY_CONTENT_CHARS)


def _sanitize_payload(payload: dict[str, Any]) -> str:
    """Sanitize and JSON-serialize payload for storage.

    Returns the final JSON string (not dict) so the caller avoids
    a second serialization pass.  Enforces MAX_HISTORY_PAYLOAD_JSON_CHARS
    against the *stored* string, including the truncation-marker framing.
    """
    safe_payload = _json_safe(payload)
    payload_json = json.dumps(safe_payload, ensure_ascii=False)
    if len(payload_json) <= MAX_HISTORY_PAYLOAD_JSON_CHARS:
        return payload_json
    logger.warning(
        "Truncating history payload from {} to {} chars",
        len(payload_json),
        MAX_HISTORY_PAYLOAD_JSON_CHARS,
    )
    # Reserve ~80 chars for the JSON wrapper keys so the final stored
    # string never exceeds the configured limit.
    preview_limit = max(0, MAX_HISTORY_PAYLOAD_JSON_CHARS - 80)
    return json.dumps(
        {
            "truncated": True,
            "original_size_chars": len(payload_json),
            "preview": _truncate_text(payload_json, preview_limit),
        },
        ensure_ascii=False,
    )


def _truncate_text(value: str, limit: int) -> str:
    if limit <= len(_TRUNCATED_SUFFIX):
        return _TRUNCATED_SUFFIX[:limit]
    return value[: limit - len(_TRUNCATED_SUFFIX)] + _TRUNCATED_SUFFIX


def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    if hasattr(value, "value"):
        return _json_safe(value.value)
    return repr(value)
