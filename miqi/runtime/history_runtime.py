"""History runtime — persistent turn and message history.

Owns SQLite storage for turn records, history items (messages),
and provides load/append/query methods used by TaskRunner and
ContextRuntime. One instance per workspace.
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
    """Persistent runtime history for one workspace.

    Provides:
      - start_turn / complete_turn for turn lifecycle tracking
      - append_item / append_message for message persistence
      - load_items / load_messages for history retrieval
    """

    def __init__(self, db_path: Path):
        self.db_path = db_path

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS runtime_turns (
                    turn_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at REAL NOT NULL,
                    completed_at REAL,
                    tools_used_json TEXT NOT NULL,
                    token_usage_json TEXT NOT NULL
                )
            """)
            await db.execute("""
                CREATE TABLE IF NOT EXISTS runtime_history_items (
                    item_id TEXT PRIMARY KEY,
                    thread_id TEXT NOT NULL,
                    turn_id TEXT NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    payload_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
            """)
            await db.commit()

    async def start_turn(self, turn_id: str, *, thread_id: str) -> None:
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """INSERT OR REPLACE INTO runtime_turns
                   (turn_id, thread_id, status, started_at, completed_at,
                    tools_used_json, token_usage_json)
                   VALUES (?, ?, ?, ?, NULL, ?, ?)""",
                (turn_id, thread_id, "running", time.time(), "[]", "{}"),
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
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """UPDATE runtime_turns
                   SET status = ?, completed_at = ?, tools_used_json = ?,
                       token_usage_json = ?
                   WHERE turn_id = ?""",
                (
                    status,
                    time.time(),
                    json.dumps(tools_used),
                    json.dumps(token_usage),
                    turn_id,
                ),
            )
            await db.commit()

    async def get_turn(self, turn_id: str) -> TurnRecord | None:
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM runtime_turns WHERE turn_id = ?",
                (turn_id,),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return TurnRecord(
            turn_id=row["turn_id"],
            thread_id=row["thread_id"],
            status=row["status"],
            started_at=row["started_at"],
            completed_at=row["completed_at"],
            tools_used=json.loads(row["tools_used_json"]),
            token_usage=json.loads(row["token_usage_json"]),
        )

    async def append_item(self, item: HistoryItem) -> None:
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """INSERT INTO runtime_history_items
                   (item_id, thread_id, turn_id, role, content, payload_json,
                    created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (
                    item.item_id,
                    item.thread_id,
                    item.turn_id,
                    item.role,
                    item.content,
                    json.dumps(item.payload),
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
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM runtime_history_items
                   WHERE thread_id = ?
                   ORDER BY created_at ASC, item_id ASC""",
                (thread_id,),
            )
            rows = await cursor.fetchall()
        return [
            HistoryItem(
                item_id=row["item_id"],
                thread_id=row["thread_id"],
                turn_id=row["turn_id"],
                role=row["role"],
                content=row["content"],
                payload=json.loads(row["payload_json"]),
                created_at=row["created_at"],
            )
            for row in rows
        ]

    async def load_messages(self, thread_id: str) -> list[dict[str, Any]]:
        """Return provider-compatible message dicts for a thread."""
        items = await self.load_items(thread_id)
        messages: list[dict[str, Any]] = []
        for item in items:
            msg: dict[str, Any] = {"role": item.role, "content": item.content}
            msg.update(item.payload.get("message_fields", {}))
            messages.append(msg)
        return messages
