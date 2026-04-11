"""SQLite + FTS5 session storage, inspired by Hermes Agent's hermes_state.py.

Key design decisions (matching Hermes):
- WAL mode for concurrent readers + one writer
- FTS5 virtual table for fast text search across all session messages
- Compression-triggered session splitting via parent_session_id chains
- Write contention handled via random jitter + BEGIN IMMEDIATE retry
- Schema versioning with automatic migrations
"""
from __future__ import annotations

import json
import logging
import random
import re
import sqlite3
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

SCHEMA_VERSION = 2

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS schema_version (
    version INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS sessions (
    id TEXT PRIMARY KEY,
    source TEXT NOT NULL DEFAULT 'cli',
    user_id TEXT,
    model TEXT,
    system_prompt TEXT,
    parent_session_id TEXT,
    started_at REAL NOT NULL,
    ended_at REAL,
    end_reason TEXT,
    message_count INTEGER DEFAULT 0,
    tool_call_count INTEGER DEFAULT 0,
    input_tokens INTEGER DEFAULT 0,
    output_tokens INTEGER DEFAULT 0,
    title TEXT,
    FOREIGN KEY (parent_session_id) REFERENCES sessions(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES sessions(id),
    role TEXT NOT NULL,
    content TEXT,
    tool_call_id TEXT,
    tool_calls TEXT,
    tool_name TEXT,
    timestamp REAL NOT NULL,
    token_count INTEGER,
    finish_reason TEXT
);

CREATE INDEX IF NOT EXISTS idx_sessions_source ON sessions(source);
CREATE INDEX IF NOT EXISTS idx_sessions_parent ON sessions(parent_session_id);
CREATE INDEX IF NOT EXISTS idx_sessions_started ON sessions(started_at DESC);
CREATE INDEX IF NOT EXISTS idx_messages_session ON messages(session_id, timestamp);
"""

FTS_SQL = """
CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts
USING fts5(
    content,
    content=messages,
    content_rowid=id
);

CREATE TRIGGER IF NOT EXISTS messages_fts_insert AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_delete AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
END;

CREATE TRIGGER IF NOT EXISTS messages_fts_update AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, content) VALUES('delete', old.id, old.content);
    INSERT INTO messages_fts(rowid, content) VALUES (new.id, new.content);
END;
"""


class SessionDB:
    """SQLite-backed session storage with FTS5 search.

    Thread-safe for concurrent reads, serialised writes via WAL + jitter retry.
    """

    # Write-contention tuning (matches Hermes values)
    _WRITE_MAX_RETRIES = 15
    _WRITE_RETRY_MIN_S = 0.020   # 20 ms
    _WRITE_RETRY_MAX_S = 0.150   # 150 ms
    _CHECKPOINT_EVERY_N_WRITES = 50

    # Title length limit
    MAX_TITLE_LENGTH = 100

    def __init__(self, db_path: Path):
        self.db_path = db_path
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

        self._lock = threading.Lock()
        self._write_count = 0
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=1.0,
            isolation_level=None,   # autocommit; we manage transactions ourselves
        )
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA foreign_keys=ON")
        self._init_schema()

    # ── Core write helper ──────────────────────────────────────────────────

    def _execute_write(self, fn: Callable[[sqlite3.Connection], T]) -> T:
        """Execute a write transaction with BEGIN IMMEDIATE and jitter retry."""
        last_err: Optional[Exception] = None
        for attempt in range(self._WRITE_MAX_RETRIES):
            try:
                with self._lock:
                    self._conn.execute("BEGIN IMMEDIATE")
                    try:
                        result = fn(self._conn)
                        self._conn.commit()
                    except BaseException:
                        try:
                            self._conn.rollback()
                        except Exception:
                            pass
                        raise
                self._write_count += 1
                if self._write_count % self._CHECKPOINT_EVERY_N_WRITES == 0:
                    self._try_wal_checkpoint()
                return result
            except sqlite3.OperationalError as exc:
                err_msg = str(exc).lower()
                if "locked" in err_msg or "busy" in err_msg:
                    last_err = exc
                    if attempt < self._WRITE_MAX_RETRIES - 1:
                        jitter = random.uniform(
                            self._WRITE_RETRY_MIN_S,
                            self._WRITE_RETRY_MAX_S,
                        )
                        time.sleep(jitter)
                        continue
                raise
        raise last_err or sqlite3.OperationalError("database is locked after max retries")

    def _try_wal_checkpoint(self) -> None:
        try:
            with self._lock:
                self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
        except Exception:
            pass

    def close(self) -> None:
        with self._lock:
            if self._conn:
                try:
                    self._conn.execute("PRAGMA wal_checkpoint(PASSIVE)")
                except Exception:
                    pass
                self._conn.close()
                self._conn = None  # type: ignore[assignment]

    # ── Schema init & migration ────────────────────────────────────────────

    def _init_schema(self) -> None:
        cursor = self._conn.cursor()
        cursor.executescript(SCHEMA_SQL)

        cursor.execute("SELECT version FROM schema_version LIMIT 1")
        row = cursor.fetchone()
        if row is None:
            cursor.execute("INSERT INTO schema_version (version) VALUES (?)", (SCHEMA_VERSION,))
        else:
            current = row[0] if not isinstance(row, sqlite3.Row) else row["version"]
            if current < 2:
                # v2: add finish_reason column to messages
                try:
                    cursor.execute("ALTER TABLE messages ADD COLUMN finish_reason TEXT")
                except sqlite3.OperationalError:
                    pass
                cursor.execute("UPDATE schema_version SET version = 2")

        # Unique title index
        try:
            cursor.execute(
                "CREATE UNIQUE INDEX IF NOT EXISTS idx_sessions_title_unique "
                "ON sessions(title) WHERE title IS NOT NULL"
            )
        except sqlite3.OperationalError:
            pass

        # FTS5 setup
        try:
            cursor.execute("SELECT * FROM messages_fts LIMIT 0")
        except sqlite3.OperationalError:
            cursor.executescript(FTS_SQL)

        self._conn.commit()

    # ── Session lifecycle ──────────────────────────────────────────────────

    def create_session(
        self,
        session_id: str,
        source: str = "cli",
        model: Optional[str] = None,
        system_prompt: Optional[str] = None,
        user_id: Optional[str] = None,
        parent_session_id: Optional[str] = None,
    ) -> str:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                """INSERT OR IGNORE INTO sessions
                   (id, source, user_id, model, system_prompt, parent_session_id, started_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (session_id, source, user_id, model, system_prompt, parent_session_id, time.time()),
            )
        self._execute_write(_do)
        return session_id

    def end_session(self, session_id: str, end_reason: str = "normal") -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                "UPDATE sessions SET ended_at = ?, end_reason = ? WHERE id = ?",
                (time.time(), end_reason, session_id),
            )
        self._execute_write(_do)

    def ensure_session(self, session_id: str, source: str = "cli", model: Optional[str] = None) -> None:
        """Create session row if it doesn't exist (recovery helper)."""
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                "INSERT OR IGNORE INTO sessions (id, source, model, started_at) VALUES (?, ?, ?, ?)",
                (session_id, source, model, time.time()),
            )
        self._execute_write(_do)

    def update_token_counts(
        self,
        session_id: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute(
                """UPDATE sessions SET
                   input_tokens = input_tokens + ?,
                   output_tokens = output_tokens + ?
                   WHERE id = ?""",
                (input_tokens, output_tokens, session_id),
            )
        self._execute_write(_do)

    def get_session(self, session_id: str) -> Optional[dict[str, Any]]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
        return dict(row) if row else None

    def get_session_title(self, session_id: str) -> Optional[str]:
        with self._lock:
            cursor = self._conn.execute(
                "SELECT title FROM sessions WHERE id = ?", (session_id,)
            )
            row = cursor.fetchone()
        return row["title"] if row else None

    @staticmethod
    def sanitize_title(title: Optional[str]) -> Optional[str]:
        if not title:
            return None
        cleaned = re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]', '', title)
        cleaned = re.sub(
            r'[\u200b-\u200f\u2028-\u202e\u2060-\u2069\ufeff\ufffc\ufff9-\ufffb]',
            '', cleaned,
        )
        cleaned = re.sub(r'\s+', ' ', cleaned).strip()
        if not cleaned:
            return None
        if len(cleaned) > SessionDB.MAX_TITLE_LENGTH:
            raise ValueError(f"Title too long ({len(cleaned)} chars, max {SessionDB.MAX_TITLE_LENGTH})")
        return cleaned

    def set_session_title(self, session_id: str, title: str) -> bool:
        title = self.sanitize_title(title)  # type: ignore[assignment]

        def _do(conn: sqlite3.Connection) -> int:
            if title:
                cursor = conn.execute(
                    "SELECT id FROM sessions WHERE title = ? AND id != ?",
                    (title, session_id),
                )
                if cursor.fetchone():
                    raise ValueError(f"Title '{title}' already in use")
            cursor = conn.execute(
                "UPDATE sessions SET title = ? WHERE id = ?",
                (title, session_id),
            )
            return cursor.rowcount

        return self._execute_write(_do) > 0

    def list_sessions(
        self,
        source: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
        include_children: bool = False,
    ) -> list[dict[str, Any]]:
        """List sessions with preview and last active timestamp."""
        where: list[str] = []
        params: list[Any] = []
        if not include_children:
            where.append("s.parent_session_id IS NULL")
        if source:
            where.append("s.source = ?")
            params.append(source)
        where_sql = f"WHERE {' AND '.join(where)}" if where else ""
        query = f"""
            SELECT s.*,
                COALESCE(
                    (SELECT SUBSTR(REPLACE(REPLACE(m.content, X'0A', ' '), X'0D', ' '), 1, 63)
                     FROM messages m
                     WHERE m.session_id = s.id AND m.role = 'user' AND m.content IS NOT NULL
                     ORDER BY m.timestamp, m.id LIMIT 1),
                    ''
                ) AS _preview_raw,
                COALESCE(
                    (SELECT MAX(m2.timestamp) FROM messages m2 WHERE m2.session_id = s.id),
                    s.started_at
                ) AS last_active
            FROM sessions s
            {where_sql}
            ORDER BY s.started_at DESC
            LIMIT ? OFFSET ?
        """
        params.extend([limit, offset])
        with self._lock:
            cursor = self._conn.execute(query, params)
            rows = cursor.fetchall()
        result = []
        for row in rows:
            s = dict(row)
            raw = s.pop("_preview_raw", "").strip()
            s["preview"] = (raw[:60] + "...") if len(raw) > 60 else raw
            result.append(s)
        return result

    def session_count(self, source: Optional[str] = None) -> int:
        with self._lock:
            if source:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM sessions WHERE source = ?", (source,)
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) FROM sessions")
            return cursor.fetchone()[0]

    def delete_session(self, session_id: str) -> bool:
        def _do(conn: sqlite3.Connection) -> bool:
            cursor = conn.execute("SELECT COUNT(*) FROM sessions WHERE id = ?", (session_id,))
            if cursor.fetchone()[0] == 0:
                return False
            conn.execute(
                "UPDATE sessions SET parent_session_id = NULL WHERE parent_session_id = ?",
                (session_id,),
            )
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            return True
        return self._execute_write(_do)

    # ── Message storage ────────────────────────────────────────────────────

    def append_message(
        self,
        session_id: str,
        role: str,
        content: Optional[str] = None,
        tool_name: Optional[str] = None,
        tool_calls: Any = None,
        tool_call_id: Optional[str] = None,
        token_count: Optional[int] = None,
        finish_reason: Optional[str] = None,
    ) -> int:
        tool_calls_json = json.dumps(tool_calls) if tool_calls else None
        num_tool_calls = 0
        if tool_calls is not None:
            num_tool_calls = len(tool_calls) if isinstance(tool_calls, list) else 1

        def _do(conn: sqlite3.Connection) -> int:
            cursor = conn.execute(
                """INSERT INTO messages
                   (session_id, role, content, tool_call_id, tool_calls, tool_name,
                    timestamp, token_count, finish_reason)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    session_id, role, content, tool_call_id, tool_calls_json,
                    tool_name, time.time(), token_count, finish_reason,
                ),
            )
            msg_id = cursor.lastrowid
            if num_tool_calls > 0:
                conn.execute(
                    """UPDATE sessions SET message_count = message_count + 1,
                       tool_call_count = tool_call_count + ? WHERE id = ?""",
                    (num_tool_calls, session_id),
                )
            else:
                conn.execute(
                    "UPDATE sessions SET message_count = message_count + 1 WHERE id = ?",
                    (session_id,),
                )
            return msg_id

        return self._execute_write(_do)

    def get_messages(self, session_id: str) -> list[dict[str, Any]]:
        """Load all messages for a session, ordered by timestamp."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT * FROM messages WHERE session_id = ? ORDER BY timestamp, id",
                (session_id,),
            )
            rows = cursor.fetchall()
        result = []
        for row in rows:
            msg = dict(row)
            if msg.get("tool_calls"):
                try:
                    msg["tool_calls"] = json.loads(msg["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    msg["tool_calls"] = []
            result.append(msg)
        return result

    def get_messages_as_conversation(self, session_id: str) -> list[dict[str, Any]]:
        """Load messages in OpenAI conversation format."""
        with self._lock:
            cursor = self._conn.execute(
                "SELECT role, content, tool_call_id, tool_calls, tool_name "
                "FROM messages WHERE session_id = ? ORDER BY timestamp, id",
                (session_id,),
            )
            rows = cursor.fetchall()
        messages = []
        for row in rows:
            msg: dict[str, Any] = {"role": row["role"], "content": row["content"]}
            if row["tool_call_id"]:
                msg["tool_call_id"] = row["tool_call_id"]
            if row["tool_name"]:
                msg["tool_name"] = row["tool_name"]
            if row["tool_calls"]:
                try:
                    msg["tool_calls"] = json.loads(row["tool_calls"])
                except (json.JSONDecodeError, TypeError):
                    msg["tool_calls"] = []
            messages.append(msg)
        return messages

    def message_count(self, session_id: Optional[str] = None) -> int:
        with self._lock:
            if session_id:
                cursor = self._conn.execute(
                    "SELECT COUNT(*) FROM messages WHERE session_id = ?", (session_id,)
                )
            else:
                cursor = self._conn.execute("SELECT COUNT(*) FROM messages")
            return cursor.fetchone()[0]

    def clear_messages(self, session_id: str) -> None:
        def _do(conn: sqlite3.Connection) -> None:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
            conn.execute(
                "UPDATE sessions SET message_count = 0, tool_call_count = 0 WHERE id = ?",
                (session_id,),
            )
        self._execute_write(_do)

    # ── Full-text search ───────────────────────────────────────────────────

    @staticmethod
    def _sanitize_fts5_query(query: str) -> str:
        """Sanitize user input for safe use in FTS5 MATCH queries."""
        _quoted_parts: list[str] = []

        def _preserve_quoted(m: re.Match) -> str:  # type: ignore[type-arg]
            _quoted_parts.append(m.group(0))
            return f"\x00Q{len(_quoted_parts) - 1}\x00"

        sanitized = re.sub(r'"[^"]*"', _preserve_quoted, query)
        sanitized = re.sub(r'[+{}()\"^]', " ", sanitized)
        sanitized = re.sub(r"\*+", "*", sanitized)
        sanitized = re.sub(r"(^|\s)\*", r"\1", sanitized)
        sanitized = re.sub(r"(?i)^(AND|OR|NOT)\b\s*", "", sanitized.strip())
        sanitized = re.sub(r"(?i)\s+(AND|OR|NOT)\s*$", "", sanitized.strip())
        sanitized = re.sub(r"\b(\w+(?:[.-]\w+)+)\b", r'"\1"', sanitized)
        for i, quoted in enumerate(_quoted_parts):
            sanitized = sanitized.replace(f"\x00Q{i}\x00", quoted)
        return sanitized.strip()

    def search_messages(
        self,
        query: str,
        source_filter: Optional[list[str]] = None,
        role_filter: Optional[list[str]] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict[str, Any]]:
        """Full-text search across session messages using FTS5."""
        if not query or not query.strip():
            return []
        query = self._sanitize_fts5_query(query)
        if not query:
            return []

        where: list[str] = ["messages_fts MATCH ?"]
        params: list[Any] = [query]

        if source_filter:
            ph = ",".join("?" for _ in source_filter)
            where.append(f"s.source IN ({ph})")
            params.extend(source_filter)
        if role_filter:
            ph = ",".join("?" for _ in role_filter)
            where.append(f"m.role IN ({ph})")
            params.extend(role_filter)

        where_sql = " AND ".join(where)
        params.extend([limit, offset])

        sql = f"""
            SELECT
                m.id,
                m.session_id,
                m.role,
                snippet(messages_fts, 0, '>>>', '<<<', '...', 40) AS snippet,
                m.timestamp,
                m.tool_name,
                s.source,
                s.model,
                s.started_at AS session_started
            FROM messages_fts
            JOIN messages m ON m.id = messages_fts.rowid
            JOIN sessions s ON s.id = m.session_id
            WHERE {where_sql}
            ORDER BY rank
            LIMIT ? OFFSET ?
        """
        with self._lock:
            try:
                cursor = self._conn.execute(sql, params)
            except sqlite3.OperationalError:
                return []
            return [dict(row) for row in cursor.fetchall()]

    # ── Export ─────────────────────────────────────────────────────────────

    def export_session(self, session_id: str) -> Optional[dict[str, Any]]:
        session = self.get_session(session_id)
        if not session:
            return None
        messages = self.get_messages(session_id)
        return {**session, "messages": messages}
