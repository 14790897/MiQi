"""Runtime ledger - append-only item log for replay and reconstruction.

Phase 24: Records every typed runtime event as immutable rows in a
session-scoped SQLite table with monotonically increasing sequence
numbers. Coexists with HistoryRuntime; designed to become the source
of truth for provider-message reconstruction and debug replay.
"""

from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite


@dataclass(frozen=True)
class LedgerItem:
    """A single immutable item in the runtime ledger."""

    item_id: str
    session_id: str
    thread_id: str
    turn_id: str | None
    seq: int
    item_type: str
    role: str | None
    content: str
    payload: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0


class LedgerRuntime:
    """Append-only runtime item ledger scoped to one session.

    Uses a single persistent aiosqlite connection (opened in initialize(),
    closed in close()) to avoid background-thread leaks on event-loop
    shutdown. All queries are filtered by session_id.
    """

    def __init__(self, db_path: Path, *, session_id: str):
        self.db_path = db_path
        self.session_id = session_id
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._db = await aiosqlite.connect(str(self.db_path))
        await self._db.execute("""
            CREATE TABLE IF NOT EXISTS runtime_ledger_items (
                item_id TEXT PRIMARY KEY,
                session_id TEXT NOT NULL,
                thread_id TEXT NOT NULL,
                turn_id TEXT,
                seq INTEGER NOT NULL,
                item_type TEXT NOT NULL,
                role TEXT,
                content TEXT NOT NULL,
                payload_json TEXT NOT NULL,
                created_at REAL NOT NULL
            )
        """)
        await self._db.execute("""
            CREATE INDEX IF NOT EXISTS idx_runtime_ledger_thread_seq
            ON runtime_ledger_items(session_id, thread_id, seq)
        """)
        await self._db.commit()

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None

    @property
    def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            raise RuntimeError("LedgerRuntime.initialize() must be called before use")
        return self._db

    async def append_item(
        self,
        *,
        thread_id: str,
        item_type: str,
        turn_id: str | None = None,
        role: str | None = None,
        content: str = "",
        payload: dict[str, Any] | None = None,
    ) -> LedgerItem:
        db = self._conn
        async with db.execute(
            """SELECT COALESCE(MAX(seq), 0) + 1
               FROM runtime_ledger_items
               WHERE session_id = ? AND thread_id = ?""",
            (self.session_id, thread_id),
        ) as cursor:
            row = await cursor.fetchone()
        seq = int(row[0])
        item = LedgerItem(
            item_id=str(uuid.uuid4()),
            session_id=self.session_id,
            thread_id=thread_id,
            turn_id=turn_id,
            seq=seq,
            item_type=item_type,
            role=role,
            content=content,
            payload=dict(payload or {}),
            created_at=time.time(),
        )
        await db.execute(
            """INSERT INTO runtime_ledger_items
               (item_id, session_id, thread_id, turn_id, seq, item_type,
                role, content, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                item.item_id,
                item.session_id,
                item.thread_id,
                item.turn_id,
                item.seq,
                item.item_type,
                item.role,
                item.content,
                json.dumps(item.payload),
                item.created_at,
            ),
        )
        await db.commit()
        return item

    async def load_items(self, thread_id: str) -> list[LedgerItem]:
        db = self._conn
        db.row_factory = aiosqlite.Row
        async with db.execute(
            """SELECT * FROM runtime_ledger_items
               WHERE session_id = ? AND thread_id = ?
               ORDER BY seq ASC""",
            (self.session_id, thread_id),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            LedgerItem(
                item_id=row["item_id"],
                session_id=row["session_id"],
                thread_id=row["thread_id"],
                turn_id=row["turn_id"],
                seq=row["seq"],
                item_type=row["item_type"],
                role=row["role"],
                content=row["content"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def load_provider_messages(self, thread_id: str) -> list[dict[str, Any]]:
        messages: list[dict[str, Any]] = []
        for item in await self.load_items(thread_id):
            if item.item_type != "message" or item.role is None:
                continue
            message: dict[str, Any] = {"role": item.role, "content": item.content}
            message.update(item.payload.get("message_fields", {}))
            messages.append(message)
        return messages
