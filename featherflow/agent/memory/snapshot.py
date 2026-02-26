"""Snapshot storage for long-term memory items."""

from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from featherflow.agent.memory.nlp import TextProcessor
from featherflow.utils.helpers import timestamp


class SnapshotStore:
    """Manages the RAM-first long-term memory snapshot (LTM_SNAPSHOT.json)."""

    DEFAULT_MAX_LTM_ITEMS = 300
    DEFAULT_COMPACT_TRIGGER_RATIO = 1.1

    def __init__(self, memory_dir: Path, audit_file: Path):
        self.snapshot_file = memory_dir / "LTM_SNAPSHOT.json"
        self.audit_file = audit_file
        self._snapshot: dict[str, Any] = {"version": 1, "updated_at": timestamp(), "items": []}
        self._dirty = False
        self._audit_buffer: list[dict[str, Any]] = []

    @property
    def items(self) -> list[dict[str, Any]]:
        return self._snapshot.get("items", [])

    @property
    def dirty(self) -> bool:
        return self._dirty

    @dirty.setter
    def dirty(self, value: bool) -> None:
        self._dirty = value

    @property
    def has_pending_audits(self) -> bool:
        return bool(self._audit_buffer)

    @property
    def updated_at(self) -> str:
        return self._snapshot.get("updated_at", "")

    def load(self) -> None:
        """Load snapshot from disk."""
        if self.snapshot_file.exists():
            try:
                data = json.loads(self.snapshot_file.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    items = data.get("items", [])
                    if not isinstance(items, list):
                        items = []
                    cleaned_items = []
                    for item in items:
                        if not isinstance(item, dict):
                            continue
                        text = TextProcessor.clean_text(str(item.get("text", "")), max_len=280)
                        if not text:
                            continue
                        cleaned_items.append(
                            {
                                "id": str(item.get("id", f"ltm_{len(cleaned_items) + 1}")),
                                "text": text,
                                "source": str(item.get("source", "unknown")),
                                "session_key": str(item.get("session_key", "")),
                                "created_at": str(item.get("created_at", timestamp())),
                                "updated_at": str(item.get("updated_at", timestamp())),
                                "hits": int(item.get("hits", 1)),
                            }
                        )
                    self._snapshot = {
                        "version": int(data.get("version", 1)),
                        "updated_at": str(data.get("updated_at", timestamp())),
                        "items": cleaned_items,
                    }
            except Exception:
                self._snapshot = {"version": 1, "updated_at": timestamp(), "items": []}

    def flush(self) -> None:
        """Persist snapshot and audit buffer to disk."""
        now = timestamp()
        if self._dirty:
            data = {
                "version": int(self._snapshot.get("version", 1)),
                "updated_at": now,
                "items": self._snapshot.get("items", []),
            }
            tmp = self.snapshot_file.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.snapshot_file)
            self._snapshot["updated_at"] = now

        if self._audit_buffer:
            with open(self.audit_file, "a", encoding="utf-8") as f:
                for event in self._audit_buffer:
                    f.write(json.dumps(event, ensure_ascii=False) + "\n")
            self._audit_buffer = []

        self._dirty = False

    def remember(
        self,
        text: str,
        session_key: str | None = None,
        source: str = "explicit_user",
    ) -> bool:
        """Add or update a long-term memory item. Returns True if added/updated."""
        cleaned = TextProcessor.clean_text(text, max_len=280)
        if not cleaned:
            return False

        norm = TextProcessor.normalize_text(cleaned)
        now = timestamp()
        items = self._snapshot["items"]

        existing = None
        for item in items:
            if TextProcessor.normalize_text(item.get("text", "")) == norm:
                existing = item
                break

        if existing:
            previous = existing.get("text", "")
            existing["text"] = cleaned
            existing["updated_at"] = now
            if session_key:
                existing["session_key"] = session_key
            existing["hits"] = int(existing.get("hits", 0)) + 1
            self._audit_buffer.append(
                {
                    "type": "memory_update",
                    "at": now,
                    "id": existing.get("id", ""),
                    "source": source,
                    "before": previous,
                    "after": cleaned,
                }
            )
        else:
            item_id = f"ltm_{int(time.time() * 1000)}_{len(items) + 1}"
            items.append(
                {
                    "id": item_id,
                    "text": cleaned,
                    "source": source,
                    "session_key": session_key or "",
                    "created_at": now,
                    "updated_at": now,
                    "hits": 1,
                }
            )
            self._audit_buffer.append(
                {
                    "type": "memory_add",
                    "at": now,
                    "id": item_id,
                    "source": source,
                    "text": cleaned,
                }
            )

        self._snapshot["updated_at"] = now
        self._dirty = True

        compact_trigger = int(self.DEFAULT_MAX_LTM_ITEMS * self.DEFAULT_COMPACT_TRIGGER_RATIO)
        if len(items) > max(self.DEFAULT_MAX_LTM_ITEMS, compact_trigger):
            self.compact(max_items=self.DEFAULT_MAX_LTM_ITEMS)

        return True

    def compact(self, max_items: int = DEFAULT_MAX_LTM_ITEMS) -> int:
        """Compact long-term snapshot by deduplicating and capping size. Returns removed count."""
        max_items = max(1, max_items)
        items = self._snapshot.get("items", [])
        if not items:
            return 0

        dedup: dict[str, dict[str, Any]] = {}
        for item in sorted(items, key=lambda x: x.get("updated_at", ""), reverse=True):
            norm = TextProcessor.normalize_text(item.get("text", ""))
            if norm and norm not in dedup:
                dedup[norm] = item

        compacted = list(dedup.values())[:max_items]
        removed = len(items) - len(compacted)
        if removed <= 0:
            return 0

        self._snapshot["items"] = compacted
        self._snapshot["updated_at"] = timestamp()
        self._dirty = True
        self._audit_buffer.append(
            {"type": "memory_compact", "at": timestamp(), "removed": removed, "kept": len(compacted)}
        )
        return removed

    def select_items(
        self, session_key: str | None, limit: int, current_message: str | None = None
    ) -> list[dict[str, Any]]:
        """Select long-term items for prompt context."""
        items = self._snapshot.get("items", [])
        if session_key:
            scoped = [
                item for item in items
                if not item.get("session_key") or item.get("session_key") == session_key
            ]
        else:
            scoped = list(items)

        return TextProcessor.select_items_by_relevance(scoped, current_message, limit)

    def list_items(self, session_key: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """List snapshot items sorted by recency/hits."""
        items = self._snapshot.get("items", [])
        if session_key:
            scoped = [
                item for item in items
                if not item.get("session_key") or item.get("session_key") == session_key
            ]
        else:
            scoped = list(items)
        scoped.sort(
            key=lambda x: (str(x.get("updated_at", "")), int(x.get("hits", 0))),
            reverse=True,
        )
        return [dict(item) for item in scoped[: max(1, limit)]]

    def delete_item(self, item_id: str) -> bool:
        """Delete a long-term snapshot item by id."""
        normalized_id = item_id.strip()
        if not normalized_id:
            return False
        items = self._snapshot.get("items", [])
        kept = [item for item in items if str(item.get("id", "")) != normalized_id]
        if len(kept) == len(items):
            return False
        self._snapshot["items"] = kept
        now = timestamp()
        self._snapshot["updated_at"] = now
        self._dirty = True
        self._audit_buffer.append({"type": "memory_delete", "at": now, "id": normalized_id})
        return True
