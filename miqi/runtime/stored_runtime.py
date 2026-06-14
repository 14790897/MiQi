"""Stored runtime access for unloaded Codex-style threads.

This module reads the runtime SQLite database without requiring a live
RuntimeSession. All lookups are scoped by client_id.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import aiosqlite

from miqi.runtime.ledger_runtime import LedgerItem
from miqi.runtime.thread_runtime import RuntimeThread


class StoredThreadError(Exception):
    """Base class for stored-thread lookup failures."""


class StoredThreadNotFound(StoredThreadError):
    """Raised when no owned stored thread matches the request."""


class StoredThreadAmbiguous(StoredThreadError):
    """Raised when the same thread id exists in multiple owned sessions."""


class StoredThreadUnauthorized(StoredThreadError):
    """Raised when the requested session does not belong to the client."""


def session_belongs_to_client(session_id: str, client_id: str) -> bool:
    return session_id == client_id or session_id.startswith(f"{client_id}:")


@dataclass(frozen=True)
class StoredThreadBundle:
    thread: RuntimeThread
    ledger_items: list[LedgerItem] = field(default_factory=list)


class StoredRuntimeReader:
    """Read stored runtime rows from a workspace runtime DB.

    The reader opens short-lived SQLite connections per operation. This keeps
    it independent from live RuntimeSession lifecycle and avoids owning a
    background aiosqlite thread longer than needed.
    """

    def __init__(self, db_path: Path, *, client_id: str):
        self.db_path = Path(db_path)
        self.client_id = client_id

    async def list_threads(
        self,
        *,
        include_archived: bool = False,
        session_id: str | None = None,
        cwd: str | None = None,
        search_term: str | None = None,
    ) -> list[RuntimeThread]:
        rows: list[RuntimeThread] = []
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                "SELECT * FROM runtime_threads ORDER BY updated_at DESC"
            )
            db_rows = await cursor.fetchall()
        for row in db_rows:
            thread = self._thread_from_row(row)
            if not session_belongs_to_client(thread.session_id, self.client_id):
                continue
            if session_id is not None and thread.session_id != session_id:
                continue
            if not include_archived and thread.status == "archived":
                continue
            if cwd is not None and thread.cwd != cwd:
                continue
            if search_term:
                haystack = " ".join([
                    thread.thread_id,
                    thread.title or "",
                    str(thread.metadata.get("preview", "")),
                ]).lower()
                if search_term.lower() not in haystack:
                    continue
            rows.append(thread)
        return rows

    async def resolve_thread(
        self, thread_id: str, *, session_id: str | None = None
    ) -> RuntimeThread:
        if session_id is not None and not session_belongs_to_client(session_id, self.client_id):
            raise StoredThreadUnauthorized(session_id)

        matches: list[RuntimeThread] = []
        for thread in await self.list_threads(include_archived=True, session_id=session_id):
            if thread.thread_id == thread_id:
                matches.append(thread)

        if not matches:
            raise StoredThreadNotFound(thread_id)
        if len(matches) > 1:
            raise StoredThreadAmbiguous(thread_id)
        return matches[0]

    async def load_ledger_items(self, thread: RuntimeThread) -> list[LedgerItem]:
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM runtime_ledger_items
                   WHERE session_id = ? AND thread_id = ?
                   ORDER BY seq ASC""",
                (thread.session_id, thread.thread_id),
            )
            rows = await cursor.fetchall()
        items = [self._ledger_from_row(row) for row in rows]
        removed: set[str] = set()
        for item in items:
            if item.item_type == "thread_rollback":
                removed.update(item.payload.get("removed_turn_ids", []))
        return [
            item for item in items
            if item.item_type != "thread_rollback"
            and (item.turn_id is None or item.turn_id not in removed)
        ]

    async def load_bundle(
        self, thread_id: str, *, session_id: str | None = None
    ) -> StoredThreadBundle:
        thread = await self.resolve_thread(thread_id, session_id=session_id)
        return StoredThreadBundle(
            thread=thread,
            ledger_items=await self.load_ledger_items(thread),
        )

    async def import_document(
        self,
        document: dict[str, Any],
        *,
        session_id: str,
        thread_id: str | None = None,
        overwrite: bool = False,
    ) -> str:
        if not session_belongs_to_client(session_id, self.client_id):
            raise StoredThreadUnauthorized(session_id)
        from miqi.runtime.thread_export import validate_import_document

        doc = validate_import_document(document)
        raw_thread = dict(doc["thread"])
        target_thread_id = thread_id or raw_thread["thread_id"]

        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            existing = await db.execute(
                "SELECT 1 FROM runtime_threads WHERE session_id = ? AND thread_id = ?",
                (session_id, target_thread_id),
            )
            if await existing.fetchone() and not overwrite:
                raise StoredThreadError("Thread already exists")

            if overwrite:
                await db.execute(
                    "DELETE FROM runtime_threads WHERE session_id = ? AND thread_id = ?",
                    (session_id, target_thread_id),
                )
                await db.execute(
                    "DELETE FROM runtime_ledger_items WHERE session_id = ? AND thread_id = ?",
                    (session_id, target_thread_id),
                )

            await db.execute(
                """INSERT INTO runtime_threads
                   (thread_id, session_id, title, status, parent_thread_id,
                    created_at, updated_at, forked_from_id, ephemeral, cwd, metadata_json)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    target_thread_id,
                    session_id,
                    raw_thread.get("title") or "Imported thread",
                    raw_thread.get("status") or "active",
                    raw_thread.get("parent_thread_id"),
                    float(raw_thread.get("created_at") or 0.0),
                    float(raw_thread.get("updated_at") or 0.0),
                    raw_thread.get("forked_from_id"),
                    int(bool(raw_thread.get("ephemeral", False))),
                    raw_thread.get("cwd"),
                    json.dumps(raw_thread.get("metadata") or {}),
                ),
            )

            for row in doc.get("ledgerItems", []):
                payload = row.get("payload") or {}
                await db.execute(
                    """INSERT INTO runtime_ledger_items
                       (item_id, session_id, thread_id, turn_id, seq, item_type,
                        role, content, payload_json, created_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                    (
                        row.get("itemId") or row.get("item_id"),
                        session_id,
                        target_thread_id,
                        row.get("turnId") or row.get("turn_id"),
                        int(row.get("seq", 0)),
                        row.get("itemType") or row.get("item_type"),
                        row.get("role"),
                        row.get("content") or "",
                        json.dumps(payload),
                        float(row.get("createdAt") or row.get("created_at") or 0.0),
                    ),
                )
            await db.commit()
        return target_thread_id

    @staticmethod
    def _thread_from_row(row: aiosqlite.Row) -> RuntimeThread:
        return RuntimeThread(
            thread_id=row["thread_id"],
            session_id=row["session_id"],
            title=row["title"],
            status=row["status"],
            parent_thread_id=row["parent_thread_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            forked_from_id=row["forked_from_id"] if "forked_from_id" in row.keys() else None,
            ephemeral=bool(row["ephemeral"]) if "ephemeral" in row.keys() else False,
            cwd=row["cwd"] if "cwd" in row.keys() else None,
            metadata=_safe_json_load(row["metadata_json"] if "metadata_json" in row.keys() else "{}"),
        )

    @staticmethod
    def _ledger_from_row(row: aiosqlite.Row) -> LedgerItem:
        return LedgerItem(
            item_id=row["item_id"],
            session_id=row["session_id"],
            thread_id=row["thread_id"],
            turn_id=row["turn_id"],
            seq=row["seq"],
            item_type=row["item_type"],
            role=row["role"],
            content=row["content"],
            payload=_safe_json_load(row["payload_json"]),
            created_at=row["created_at"],
        )


def _safe_json_load(raw: str) -> dict[str, Any]:
    try:
        value = json.loads(raw or "{}")
    except (json.JSONDecodeError, TypeError):
        return {}
    return value if isinstance(value, dict) else {}
