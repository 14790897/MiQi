"""File-based persistent stores for KUN runtime.

Aligns with KUN ``adapters/file/`` stores.

- ``FileThreadStore`` — one JSON file per thread for the thread record.
- ``FileSessionStore`` — append-only JSONL for TurnItems + events per thread.

All paths are relative to a configurable ``data_dir``. Tests should
always pass a ``tmp_path`` to avoid touching real user directories.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

# ═══════════════════════════════════════════════════════════════════════════════
# FileThreadStore
# ═══════════════════════════════════════════════════════════════════════════════


class FileThreadStore:
    """Persist thread records as individual JSON files under ``<data_dir>/threads/``.

    Each thread record is stored as ``<thread_id>.json``.  On ``upsert`` the file
    is atomically rewritten.  Thread listing scans the directory.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir) / "threads"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _path(self, thread_id: str) -> Path:
        # Sanitize: thread IDs are typically alphanumeric, but guard against
        # directory traversal.
        safe = thread_id.replace("\\", "_").replace("/", "_")
        return self._dir / f"{safe}.json"

    async def get(self, thread_id: str) -> dict[str, Any] | None:
        """Return the thread record or None."""
        path = self._path(thread_id)
        if not path.exists():
            return None
        try:
            record = json.loads(path.read_text(encoding="utf-8"))
            # Backward compatibility: normalize legacy "agent" mode → "edit"
            if record.get("mode") == "agent":
                record["mode"] = "edit"
            return record
        except (json.JSONDecodeError, OSError):
            return None

    async def upsert(self, record: dict[str, Any]) -> None:
        """Create or replace a thread record. ``record`` must contain ``id``."""
        thread_id = str(record.get("id", ""))
        if not thread_id:
            raise ValueError("thread record must have a non-empty id")
        path = self._path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        raw = json.dumps(record, ensure_ascii=False, indent=2)
        # Atomic write: write to temp, chmod, then rename
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(raw, encoding="utf-8")
        os.chmod(tmp, 0o600)  # restrict to owner only
        os.replace(tmp, path)

    async def delete(self, thread_id: str) -> bool:
        """Delete a thread record. Returns True if it existed."""
        path = self._path(thread_id)
        if not path.exists():
            return False
        path.unlink()
        return True

    async def list(self) -> list[dict[str, Any]]:
        """Return all thread summaries, newest-first by modification time."""
        results: list[dict[str, Any]] = []
        for path in sorted(
            self._dir.glob("*.json"),
            key=lambda p: p.stat().st_mtime if p.exists() else 0,
            reverse=True,
        ):
            try:
                record = json.loads(path.read_text(encoding="utf-8"))
                if isinstance(record, dict) and record.get("id"):
                    results.append(record)
            except (json.JSONDecodeError, OSError):
                continue
        return results


# ═══════════════════════════════════════════════════════════════════════════════
# FileSessionStore
# ═══════════════════════════════════════════════════════════════════════════════


class FileSessionStore:
    """Append-only JSONL storage for TurnItems and runtime events.

    Items are stored in ``<data_dir>/sessions/<thread_id>.jsonl``.
    Events are stored in ``<data_dir>/sessions/<thread_id>.events.jsonl``.

    Both files are append-only. ``rewriteItems`` does a full rewrite.
    """

    def __init__(self, data_dir: str | Path) -> None:
        self._dir = Path(data_dir) / "sessions"
        self._dir.mkdir(parents=True, exist_ok=True)

    def _items_path(self, thread_id: str) -> Path:
        safe = thread_id.replace("\\", "_").replace("/", "_")
        return self._dir / f"{safe}.jsonl"

    def _events_path(self, thread_id: str) -> Path:
        safe = thread_id.replace("\\", "_").replace("/", "_")
        return self._dir / f"{safe}.events.jsonl"

    # ── items ────────────────────────────────────────────────────────────

    async def load_items(self, thread_id: str) -> list[dict[str, Any]]:
        """Load all TurnItems for *thread_id* in append order."""
        path = self._items_path(thread_id)
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    items.append(data)
            except json.JSONDecodeError:
                continue
        return items

    async def append_item(self, thread_id: str, item: dict[str, Any]) -> None:
        """Append a single TurnItem to the items file."""
        path = self._items_path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(item, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        os.chmod(path, 0o600)  # restrict to owner only

    async def update_item(
        self, thread_id: str, item_id: str, patch: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update a specific item by id. Currently a full rewrite — efficient
        enough for typical conversation sizes.
        """
        items = await self.load_items(thread_id)
        updated: dict[str, Any] | None = None
        changed = False
        for i, item in enumerate(items):
            if item.get("id") == item_id:
                items[i] = {**item, **patch}
                updated = items[i]
                changed = True
                break
        if not changed:
            return None
        await self._rewrite_items_file(thread_id, items)
        return updated

    async def rewrite_items(self, thread_id: str, items: list[dict[str, Any]]) -> None:
        """Replace all items for *thread_id* with *items* (used for history healing)."""
        await self._rewrite_items_file(thread_id, items)

    async def _rewrite_items_file(self, thread_id: str, items: list[dict[str, Any]]) -> None:
        path = self._items_path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            for item in items:
                f.write(json.dumps(item, ensure_ascii=False) + "\n")
        os.chmod(tmp, 0o600)  # restrict to owner only
        os.replace(tmp, path)

    # ── events ───────────────────────────────────────────────────────────

    async def append_event(self, thread_id: str, event: dict[str, Any]) -> None:
        """Append a single runtime event to the events file."""
        path = self._events_path(thread_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        line = json.dumps(event, ensure_ascii=False) + "\n"
        with open(path, "a", encoding="utf-8") as f:
            f.write(line)
        os.chmod(path, 0o600)  # restrict to owner only

    async def load_events_since(self, thread_id: str, since_seq: int = 0) -> list[dict[str, Any]]:
        """Load events with seq > *since_seq*."""
        path = self._events_path(thread_id)
        if not path.exists():
            return []
        events: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
                if isinstance(data, dict):
                    seq = data.get("seq", 0)
                    if isinstance(seq, int) and seq > since_seq:
                        events.append(data)
            except json.JSONDecodeError:
                continue
        return events
