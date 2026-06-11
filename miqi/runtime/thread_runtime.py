"""Thread runtime — persistent thread lifecycle manager for RuntimeSession.

Owns thread CRUD operations on a SQLite store: create, rename, archive,
delete, fork, list. One instance per workspace.
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass
from pathlib import Path

import aiosqlite


@dataclass(frozen=True)
class RuntimeThread:
    """A runtime thread record."""

    thread_id: str
    session_id: str
    title: str
    status: str
    parent_thread_id: str | None
    created_at: float
    updated_at: float


class ThreadRuntime:
    """Persistent thread lifecycle manager for RuntimeSession.

    Manages thread records in a SQLite database. One instance per
    workspace, shared across sessions via the common runtime DB.
    """

    def __init__(self, db_path: Path, *, session_id: str):
        self.db_path = db_path
        self.session_id = session_id

    async def initialize(self) -> None:
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute("""
                CREATE TABLE IF NOT EXISTS runtime_threads (
                    thread_id TEXT NOT NULL,
                    session_id TEXT NOT NULL,
                    title TEXT NOT NULL,
                    status TEXT NOT NULL,
                    parent_thread_id TEXT,
                    created_at REAL NOT NULL,
                    updated_at REAL NOT NULL,
                    PRIMARY KEY (session_id, thread_id)
                )
            """)
            await db.commit()

    async def create_thread(
        self,
        *,
        title: str,
        thread_id: str | None = None,
        parent_thread_id: str | None = None,
    ) -> RuntimeThread:
        now = time.time()
        tid = thread_id or f"thread-{str(uuid.uuid4())[:12]}"
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """INSERT INTO runtime_threads
                   (thread_id, session_id, title, status, parent_thread_id,
                    created_at, updated_at)
                   VALUES (?, ?, ?, 'active', ?, ?, ?)""",
                (tid, self.session_id, title, parent_thread_id, now, now),
            )
            await db.commit()
        thread = await self.get_thread(tid)
        assert thread is not None
        return thread

    async def get_thread(self, thread_id: str) -> RuntimeThread | None:
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(
                """SELECT * FROM runtime_threads
                   WHERE thread_id = ? AND session_id = ?""",
                (thread_id, self.session_id),
            )
            row = await cursor.fetchone()
        if row is None:
            return None
        return RuntimeThread(
            thread_id=row["thread_id"],
            session_id=row["session_id"],
            title=row["title"],
            status=row["status"],
            parent_thread_id=row["parent_thread_id"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    async def rename_thread(self, thread_id: str, title: str) -> RuntimeThread:
        await self._update(thread_id, title=title)
        thread = await self.get_thread(thread_id)
        if thread is None:
            raise KeyError(thread_id)
        return thread

    async def archive_thread(self, thread_id: str) -> RuntimeThread:
        await self._update(thread_id, status="archived")
        thread = await self.get_thread(thread_id)
        if thread is None:
            raise KeyError(thread_id)
        return thread

    async def delete_thread(self, thread_id: str) -> None:
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """DELETE FROM runtime_threads
                   WHERE thread_id = ? AND session_id = ?""",
                (thread_id, self.session_id),
            )
            await db.commit()

    async def fork_thread(
        self, parent_thread_id: str, *, title: str
    ) -> RuntimeThread:
        parent = await self.get_thread(parent_thread_id)
        if parent is None:
            raise KeyError(parent_thread_id)
        return await self.create_thread(
            title=title, parent_thread_id=parent_thread_id,
        )

    async def list_threads(
        self, *, include_archived: bool = False,
    ) -> list[RuntimeThread]:
        query = "SELECT * FROM runtime_threads WHERE session_id = ?"
        params: tuple[object, ...] = (self.session_id,)
        if not include_archived:
            query += " AND status = 'active'"
        query += " ORDER BY updated_at DESC"
        async with aiosqlite.connect(str(self.db_path)) as db:
            db.row_factory = aiosqlite.Row
            cursor = await db.execute(query, params)
            rows = await cursor.fetchall()
        return [
            RuntimeThread(
                thread_id=row["thread_id"],
                session_id=row["session_id"],
                title=row["title"],
                status=row["status"],
                parent_thread_id=row["parent_thread_id"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
            for row in rows
        ]

    async def _update(
        self,
        thread_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
    ) -> None:
        thread = await self.get_thread(thread_id)
        if thread is None:
            raise KeyError(thread_id)
        next_title = title if title is not None else thread.title
        next_status = status if status is not None else thread.status
        async with aiosqlite.connect(str(self.db_path)) as db:
            await db.execute(
                """UPDATE runtime_threads
                   SET title = ?, status = ?, updated_at = ?
                   WHERE thread_id = ? AND session_id = ?""",
                (next_title, next_status, time.time(), thread_id, self.session_id),
            )
            await db.commit()
