"""Session management for conversation history."""

import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.utils.helpers import LEGACY_DATA_DIR, ensure_dir, safe_filename


@dataclass
class Session:
    """A conversation session stored as append-only JSONL messages."""

    key: str  # channel:chat_id
    messages: list[dict[str, Any]] = field(default_factory=list)
    created_at: datetime = field(default_factory=datetime.now)
    updated_at: datetime = field(default_factory=datetime.now)
    metadata: dict[str, Any] = field(default_factory=dict)
    last_consolidated: int = 0  # Number of messages already archived to memory files
    saved_count: int = 0  # Number of messages already persisted to disk

    def add_message(self, role: str, content: str, **kwargs: Any) -> None:
        """Add a message to the session."""
        msg = {
            "role": role,
            "content": content,
            "timestamp": datetime.now().isoformat(),
            **kwargs,
        }
        self.messages.append(msg)
        self.updated_at = datetime.now()

    def get_history(self, max_messages: int = 500) -> list[dict[str, Any]]:
        """Return unconsolidated history, aligned to a user turn."""
        unconsolidated = self.messages[self.last_consolidated :]
        sliced = unconsolidated[-max_messages:]

        # Drop leading non-user messages to avoid orphaned tool_result blocks.
        for idx, item in enumerate(sliced):
            if item.get("role") == "user":
                sliced = sliced[idx:]
                break

        out: list[dict[str, Any]] = []
        for item in sliced:
            entry: dict[str, Any] = {
                "role": item["role"],
                "content": item.get("content", ""),
            }
            for key in ("tool_calls", "tool_call_id", "name"):
                if key in item:
                    entry[key] = item[key]
            out.append(entry)
        return out

    def clear(self) -> None:
        """Clear all messages and reset archive cursor."""
        self.messages = []
        self.last_consolidated = 0
        self.updated_at = datetime.now()
        # Keep saved_count so save() can detect history shrink and rewrite safely.


class SessionManager:
    """Manages conversation sessions stored as JSONL files."""

    def __init__(
        self,
        workspace: Path,
        compact_threshold_messages: int = 400,
        compact_threshold_bytes: int = 2_000_000,
        compact_keep_messages: int = 300,
    ):
        self.workspace = workspace
        self.sessions_dir = ensure_dir(self.workspace / "sessions")
        self.legacy_sessions_dir = Path.home() / LEGACY_DATA_DIR / "sessions"
        self.compact_threshold_messages = max(1, compact_threshold_messages)
        self.compact_threshold_bytes = max(1, compact_threshold_bytes)
        self.compact_keep_messages = max(1, compact_keep_messages)
        self._cache: dict[str, Session] = {}

    def get_session_dir(self, key: str) -> Path:
        safe_key = safe_filename(key.replace(":", "_"))
        return self.sessions_dir / safe_key

    def _get_session_path(self, key: str) -> Path:
        """Get the file path for a session key."""
        return self.get_session_dir(key) / "conversation.jsonl"

    def _migrate_flat_to_dir(self, key: str) -> None:
        """If old flat .jsonl exists and new dir does not, migrate."""
        safe_key = safe_filename(key.replace(":", "_"))
        old_flat = self.sessions_dir / f"{safe_key}.jsonl"
        new_dir  = self.sessions_dir / safe_key
        if old_flat.exists() and not new_dir.exists():
            new_dir.mkdir(parents=True, exist_ok=True)
            shutil.move(str(old_flat), str(new_dir / "conversation.jsonl"))

    def _get_legacy_session_path(self, key: str) -> Path:
        """Legacy global session path for migration only."""
        safe_key = safe_filename(key.replace(":", "_"))
        return self.legacy_sessions_dir / f"{safe_key}.jsonl"

    def get_or_create(self, key: str) -> Session:
        """Get an existing session from cache/disk or create a new one."""
        if key in self._cache:
            return self._cache[key]

        session = self._load(key)
        if session is None:
            session = Session(key=key)

        self._cache[key] = session
        return session

    def _load(self, key: str) -> Session | None:
        """Load a session from disk."""
        self._migrate_flat_to_dir(key)
        path = self._get_session_path(key)
        if not path.exists():
            legacy_path = self._get_legacy_session_path(key)
            if legacy_path.exists():
                try:
                    shutil.move(str(legacy_path), str(path))
                    logger.info("Migrated session {} from legacy path", key)
                except Exception:
                    logger.exception("Failed to migrate session {}", key)

        if not path.exists():
            return None

        try:
            messages: list[dict[str, Any]] = []
            metadata: dict[str, Any] = {}
            created_at: datetime | None = None
            updated_at: datetime | None = None
            last_consolidated = 0

            with open(path, encoding="utf-8") as f:
                for raw in f:
                    line = raw.strip()
                    if not line:
                        continue

                    data = json.loads(line)
                    if data.get("_type") == "metadata":
                        metadata = data.get("metadata", {})
                        if data.get("created_at"):
                            created_at = datetime.fromisoformat(data["created_at"])
                        if data.get("updated_at"):
                            updated_at = datetime.fromisoformat(data["updated_at"])
                        last_consolidated = int(data.get("last_consolidated", 0) or 0)
                    else:
                        messages.append(data)
                        msg_ts = data.get("timestamp")
                        if isinstance(msg_ts, str):
                            try:
                                updated_at = datetime.fromisoformat(msg_ts)
                            except Exception:
                                pass

            session = Session(
                key=key,
                messages=messages,
                created_at=created_at or datetime.now(),
                updated_at=updated_at or created_at or datetime.now(),
                metadata=metadata,
                last_consolidated=max(0, min(last_consolidated, len(messages))),
                saved_count=len(messages),
            )
            return session
        except Exception as exc:
            logger.warning("Failed to load session {}: {}", key, exc)
            return None

    def save(self, session: Session) -> None:
        """Persist session changes with append-only writes when possible."""
        self._migrate_flat_to_dir(session.key)
        path = self._get_session_path(session.key)
        path.parent.mkdir(parents=True, exist_ok=True)

        should_rewrite = not path.exists() or len(session.messages) < session.saved_count

        if should_rewrite:
            with open(path, "w", encoding="utf-8") as f:
                metadata_line = {
                    "_type": "metadata",
                    "key": session.key,
                    "created_at": session.created_at.isoformat(),
                    "updated_at": session.updated_at.isoformat(),
                    "metadata": session.metadata,
                    "last_consolidated": session.last_consolidated,
                }
                f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
                for msg in session.messages:
                    f.write(json.dumps(msg, ensure_ascii=False) + "\n")
            path.chmod(0o600)  # Restrict to owner only (SEC-07)
            session.saved_count = len(session.messages)
        else:
            new_messages = session.messages[session.saved_count :]
            if new_messages:
                with open(path, "a", encoding="utf-8") as f:
                    for msg in new_messages:
                        f.write(json.dumps(msg, ensure_ascii=False) + "\n")
                path.chmod(0o600)  # Restrict to owner only (SEC-07)
                session.saved_count = len(session.messages)

        self._cache[session.key] = session
        self.compact_if_needed(session.key)

    # ── Tracked files (sidebar) ───────────────────────────────────────

    def _get_tracked_files_path(self, key: str) -> Path:
        """Path to the per-session tracked_files.json."""
        self._migrate_flat_to_dir(key)
        return self.get_session_dir(key) / "tracked_files.json"

    def load_tracked_files(self, key: str) -> dict[str, dict]:
        """Load tracked files map {normalized_path: {op, name, lastSeen}}.

        Returns an empty dict if the file doesn't exist or is corrupt.
        """
        path = self._get_tracked_files_path(key)
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            return data.get("files", {}) if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_tracked_file(self, key: str, file_path: str, op: str = "read",
                          name: str = "") -> None:
        """Upsert a single tracked file entry.

        ``file_path`` is normalised to forward-slash internally.
        ``op`` is one of: read, write, edit, delete.
        """
        files = self.load_tracked_files(key)
        norm = file_path.replace("\\", "/")
        existing = files.get(norm, {})
        # Upgrade: read < edit < write < delete
        rank = {"read": 0, "edit": 1, "write": 2, "delete": 3}
        cur_rank = rank.get(existing.get("op", "read"), 0)
        new_rank = rank.get(op, 0)
        if new_rank >= cur_rank:
            from pathlib import PurePosixPath
            files[norm] = {
                "op": op,
                "name": name or PurePosixPath(norm).name,
                "lastSeen": int(datetime.now().timestamp() * 1000),
            }
        path = self._get_tracked_files_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"version": 1, "files": files}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    def reset_tracked_file_op(self, key: str, file_path: str, op: str = "read") -> None:
        """Force-reset the op of a tracked file entry (ignoring rank).

        Unlike ``save_tracked_file`` this bypasses the rank guard so a
        ``write`` entry can be downgraded back to ``read`` after accept.
        """
        files = self.load_tracked_files(key)
        norm = file_path.replace("\\", "/")
        if norm not in files:
            return
        from pathlib import PurePosixPath
        files[norm]["op"] = op
        files[norm]["lastSeen"] = int(datetime.now().timestamp() * 1000)
        path = self._get_tracked_files_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"version": 1, "files": files}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    def remove_tracked_file(self, key: str, file_path: str) -> None:
        """Remove a single tracked file entry."""
        files = self.load_tracked_files(key)
        norm = file_path.replace("\\", "/")
        files.pop(norm, None)
        path = self._get_tracked_files_path(key)
        if not files:
            path.unlink(missing_ok=True)
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text(
            json.dumps({"version": 1, "files": files}, ensure_ascii=False),
            encoding="utf-8",
        )
        tmp.replace(path)

    def clear_tracked_files(self, key: str) -> None:
        """Remove the entire tracked_files.json for a session."""
        path = self._get_tracked_files_path(key)
        path.unlink(missing_ok=True)

    # ── Archive ───────────────────────────────────────────────────────

    def _get_archived_marker(self, key: str) -> Path:
        """Path to the archive marker file."""
        self._migrate_flat_to_dir(key)
        return self.get_session_dir(key) / ".archived"

    def invalidate(self, key: str) -> None:
        """Remove a session from in-memory cache."""
        self._cache.pop(key, None)

    def archive(self, key: str) -> None:
        """Mark a session as archived."""
        path = self._get_archived_marker(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.touch()
        self.invalidate(key)

    def unarchive(self, key: str) -> None:
        """Remove archived marker from a session."""
        path = self._get_archived_marker(key)
        path.unlink(missing_ok=True)
        self.invalidate(key)

    def list_sessions(self, include_archived: bool = False) -> list[dict[str, Any]]:
        """List sessions sorted by updated time descending.

        Args:
            include_archived: If False (default), exclude archived sessions.
        """
        sessions: list[dict[str, Any]] = []

        # Primary: directory-based sessions
        for path in self.sessions_dir.glob("*/conversation.jsonl"):
            try:
                data = self._read_metadata(path)
                if data is None:
                    continue
                if not include_archived and (path.parent / ".archived").exists():
                    continue
                key = data.get("key") or path.parent.name.replace("_", ":", 1)
                sessions.append(
                    {
                        "key": key,
                        "title": self._extract_title(path) or key,
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "path": str(path),
                    }
                )
            except Exception:
                continue

        # Fallback: old flat .jsonl files not yet migrated
        for path in self.sessions_dir.glob("*.jsonl"):
            try:
                data = self._read_metadata(path)
                if data is None:
                    continue
                key = data.get("key") or path.stem.replace("_", ":", 1)
                sessions.append(
                    {
                        "key": key,
                        "title": self._extract_title(path) or key,
                        "created_at": data.get("created_at"),
                        "updated_at": data.get("updated_at"),
                        "path": str(path),
                    }
                )
            except Exception:
                continue

        return sorted(sessions, key=lambda item: item.get("updated_at", ""), reverse=True)
        """Remove a session from in-memory cache."""
        self._cache.pop(key, None)

    def delete(self, key: str) -> bool:
        """Delete a session from cache and disk."""
        self._cache.pop(key, None)
        self._migrate_flat_to_dir(key)
        session_dir = self.get_session_dir(key)
        if session_dir.exists():
            shutil.rmtree(session_dir)
            return True
        # Fallback: old flat file that was never migrated
        safe_key = safe_filename(key.replace(":", "_"))
        old_flat = self.sessions_dir / f"{safe_key}.jsonl"
        if old_flat.exists():
            old_flat.unlink()
            return True
        return False

    @staticmethod
    def _extract_title(path: Path) -> str:
        """Extract the first user message text (≤ 60 chars) from a conversation file."""
        try:
            for raw in path.read_text(encoding="utf-8").splitlines():
                obj = json.loads(raw)
                if obj.get("role") == "user" and obj.get("content"):
                    return str(obj["content"])[:60]
        except Exception:
            pass
        return ""

    def _read_metadata(self, path: Path) -> dict | None:
        """Read the metadata line from a conversation.jsonl or flat .jsonl file."""
        try:
            with open(path, encoding="utf-8") as f:
                first_line = f.readline().strip()
                if not first_line:
                    return None
                data = json.loads(first_line)
                if data.get("_type") != "metadata":
                    return None
                return data
        except Exception:
            return None

    def compact_if_needed(self, key: str) -> bool:
        """Compact a session file if thresholds are exceeded."""
        session = self.get_or_create(key)
        path = self._get_session_path(key)
        if not path.exists():
            return False

        by_message_count = len(session.messages) >= self.compact_threshold_messages
        by_file_size = path.stat().st_size >= self.compact_threshold_bytes
        if not by_message_count and not by_file_size:
            return False

        return self.compact(key)

    def compact(self, key: str) -> bool:
        """Compact a session by rewriting with only recent messages."""
        path = self._get_session_path(key)
        if not path.exists():
            return False

        session = self.get_or_create(key)
        original_len = len(session.messages)
        if original_len > self.compact_keep_messages:
            drop_count = original_len - self.compact_keep_messages
            session.messages = session.messages[-self.compact_keep_messages :]
            session.last_consolidated = max(0, session.last_consolidated - drop_count)
        session.last_consolidated = min(session.last_consolidated, len(session.messages))

        session.saved_count = len(session.messages)
        session.updated_at = datetime.now()

        with open(path, "w", encoding="utf-8") as f:
            metadata_line = {
                "_type": "metadata",
                "key": session.key,
                "created_at": session.created_at.isoformat(),
                "updated_at": session.updated_at.isoformat(),
                "metadata": session.metadata,
                "last_consolidated": session.last_consolidated,
            }
            f.write(json.dumps(metadata_line, ensure_ascii=False) + "\n")
            for msg in session.messages:
                f.write(json.dumps(msg, ensure_ascii=False) + "\n")

        self._cache[key] = session
        return True

    def compact_all(self) -> int:
        """Compact all existing session files and return compacted count."""
        compacted = 0
        for info in self.list_sessions():
            if self.compact(info["key"]):
                compacted += 1
        return compacted
