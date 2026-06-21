"""SQLite persistence layer for agent jobs and spawn edges.

Phase 52: opt-in store used by AgentJobRuntime and AgentControl to persist
job state and parent/child agent edges across process restarts.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Union


@dataclass
class AgentJobRow:
    """Persistent representation of an AgentJob."""

    job_id: str
    agent_type: str | None
    task: str | None
    thread_id: str | None
    parent_thread_id: str | None
    status: str
    result: str | None
    error: str | None
    created_at: float | None
    completed_at: float | None


@dataclass
class AgentEdgeRow:
    """Persistent representation of a spawn edge."""

    parent_agent_id: str
    child_agent_id: str
    child_thread_id: str | None
    created_at: float | None


class AgentGraphStore:
    """Synchronous SQLite persistence for agent jobs and spawn edges.

    Store methods open/close a connection per call so callers do not need
    to manage connection lifecycle.  The store is opt-in: when ``None`` is
    passed to consumers, behaviour is unchanged.
    """

    def __init__(self, db_path: Union[str, Path]):
        self._db_path = Path(db_path)
        self._ensure_tables()

    def _ensure_tables(self) -> None:
        """Create tables and apply SQLite pragmas."""
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        with sqlite3.connect(self._db_path) as conn:
            conn.execute("PRAGMA journal_mode=WAL")
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_agent_jobs (
                    job_id TEXT PRIMARY KEY,
                    agent_type TEXT,
                    task TEXT,
                    thread_id TEXT,
                    parent_thread_id TEXT,
                    status TEXT,
                    result TEXT,
                    error TEXT,
                    created_at REAL,
                    completed_at REAL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS runtime_agent_edges (
                    parent_agent_id TEXT,
                    child_agent_id TEXT,
                    child_thread_id TEXT,
                    created_at REAL,
                    PRIMARY KEY (parent_agent_id, child_agent_id)
                )
                """
            )
            conn.commit()

    def _connect(self) -> sqlite3.Connection:
        conn = sqlite3.connect(self._db_path)
        conn.execute("PRAGMA foreign_keys=ON")
        return conn

    def save_job(
        self,
        *,
        job_id: str,
        agent_type: str | None,
        task: str | None,
        thread_id: str | None,
        parent_thread_id: str | None,
        status: str,
        result: str | None,
        error: str | None,
        created_at: float | None,
        completed_at: float | None,
    ) -> None:
        """Insert or replace a full job row."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO runtime_agent_jobs
                (job_id, agent_type, task, thread_id, parent_thread_id,
                 status, result, error, created_at, completed_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    job_id,
                    agent_type,
                    task,
                    thread_id,
                    parent_thread_id,
                    status,
                    result,
                    error,
                    created_at,
                    completed_at,
                ),
            )
            conn.commit()

    def update_job_status(
        self,
        *,
        job_id: str,
        status: str,
        result: str | None,
        error: str | None,
        completed_at: float | None,
    ) -> None:
        """Update the mutable status fields of a job row."""
        with self._connect() as conn:
            conn.execute(
                """
                UPDATE runtime_agent_jobs
                SET status = ?, result = ?, error = ?, completed_at = ?
                WHERE job_id = ?
                """,
                (status, result, error, completed_at, job_id),
            )
            conn.commit()

    def load_jobs(self) -> list[AgentJobRow]:
        """Return all persisted jobs ordered by creation time (newest first)."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT job_id, agent_type, task, thread_id, parent_thread_id,
                       status, result, error, created_at, completed_at
                FROM runtime_agent_jobs
                ORDER BY created_at DESC
                """
            )
            rows = cursor.fetchall()
        return [
            AgentJobRow(
                job_id=r[0],
                agent_type=r[1],
                task=r[2],
                thread_id=r[3],
                parent_thread_id=r[4],
                status=r[5],
                result=r[6],
                error=r[7],
                created_at=r[8],
                completed_at=r[9],
            )
            for r in rows
        ]

    def get_job(self, job_id: str) -> AgentJobRow | None:
        """Return a single job row, or ``None`` if not found."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT job_id, agent_type, task, thread_id, parent_thread_id,
                       status, result, error, created_at, completed_at
                FROM runtime_agent_jobs
                WHERE job_id = ?
                """,
                (job_id,),
            )
            row = cursor.fetchone()
        if row is None:
            return None
        return AgentJobRow(
            job_id=row[0],
            agent_type=row[1],
            task=row[2],
            thread_id=row[3],
            parent_thread_id=row[4],
            status=row[5],
            result=row[6],
            error=row[7],
            created_at=row[8],
            completed_at=row[9],
        )

    def add_edge(
        self,
        *,
        parent_agent_id: str,
        child_agent_id: str,
        child_thread_id: str | None,
    ) -> None:
        """Insert a parent→child spawn edge if it does not already exist."""
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO runtime_agent_edges
                (parent_agent_id, child_agent_id, child_thread_id, created_at)
                VALUES (?, ?, ?, ?)
                """,
                (parent_agent_id, child_agent_id, child_thread_id, time.time()),
            )
            conn.commit()

    def get_children(self, parent_agent_id: str) -> list[AgentEdgeRow]:
        """Return all spawn edges for a given parent agent."""
        with self._connect() as conn:
            cursor = conn.execute(
                """
                SELECT parent_agent_id, child_agent_id, child_thread_id, created_at
                FROM runtime_agent_edges
                WHERE parent_agent_id = ?
                ORDER BY created_at ASC
                """,
                (parent_agent_id,),
            )
            rows = cursor.fetchall()
        return [
            AgentEdgeRow(
                parent_agent_id=r[0],
                child_agent_id=r[1],
                child_thread_id=r[2],
                created_at=r[3],
            )
            for r in rows
        ]

    def get_tree(self, root_agent_id: str) -> list[str]:
        """Return a flat list of descendant agent IDs starting from ``root_agent_id``.

        The result includes the root ID as its first element.
        """
        result: list[str] = []
        stack = [root_agent_id]
        while stack:
            current = stack.pop()
            if current not in result:
                result.append(current)
            for edge in self.get_children(current):
                if edge.child_agent_id not in result:
                    stack.append(edge.child_agent_id)
        return result
