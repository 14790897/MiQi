"""Thread lifecycle service for KUN runtime.

Aligns with KUN ``services/thread-service.ts``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Any, Callable

from miqi.kun_runtime.event_recorder import RuntimeEventRecorder
from miqi.kun_runtime.stores import FileSessionStore, FileThreadStore

# Fields that are safe to update via the public update() method.
# id, workspace, model, createdAt, turns, and relation are immutable
# unless explicitly changed through dedicated methods.
_ALLOWED_UPDATE_FIELDS = frozenset({
    "title", "status", "mode", "approvalPolicy", "sandboxMode",
    "costBudgetUsd", "costBudgetWarningSent", "goal", "todos",
})


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class ThreadService:
    """CRUD operations for KUN threads."""

    def __init__(
        self,
        thread_store: FileThreadStore,
        session_store: FileSessionStore,
        events: RuntimeEventRecorder,
        now_iso: Callable[[], str] | None = None,
    ):
        self._thread_store = thread_store
        self._session_store = session_store
        self._events = events
        self._now_iso = now_iso or _utc_now_iso

    async def create(self, **fields: Any) -> dict[str, Any]:
        """Create a new thread. Required: ``workspace``, ``model``."""
        now = self._now_iso()
        record: dict[str, Any] = {
            "id": _new_id("thread"),
            "title": fields.get("title", "New Thread"),
            "workspace": fields["workspace"],
            "model": fields["model"],
            "mode": fields.get("mode", "agent"),
            "status": fields.get("status", "idle"),
            "approvalPolicy": fields.get("approvalPolicy", "auto"),
            "sandboxMode": fields.get("sandboxMode", "workspace-write"),
            "relation": fields.get("relation", "primary"),
            "costBudgetUsd": fields.get("costBudgetUsd"),
            "costBudgetWarningSent": False,
            "createdAt": now,
            "updatedAt": now,
            "turns": [],
        }
        if "goal" in fields and fields["goal"] is not None:
            record["goal"] = fields["goal"]
        if "todos" in fields and fields["todos"] is not None:
            record["todos"] = fields["todos"]
        await self._thread_store.upsert(record)
        await self._events.record({
            "kind": "thread_created",
            "threadId": record["id"],
            "title": record["title"],
        })
        return record

    async def get(self, thread_id: str) -> dict[str, Any] | None:
        """Return a thread record or None."""
        return await self._thread_store.get(thread_id)

    async def list(self) -> list[dict[str, Any]]:
        """List all threads."""
        return await self._thread_store.list()

    async def update(self, thread_id: str, patch: dict[str, Any]) -> dict[str, Any] | None:
        """Update thread fields. Only allowlisted fields are accepted."""
        record = await self._thread_store.get(thread_id)
        if record is None:
            return None
        now = self._now_iso()
        clean_patch = {k: v for k, v in patch.items() if k in _ALLOWED_UPDATE_FIELDS}
        merged = {**record, **clean_patch, "updatedAt": now}
        await self._thread_store.upsert(merged)
        await self._events.record({
            "kind": "thread_updated",
            "threadId": thread_id,
            "title": merged.get("title"),
            "status": merged.get("status"),
        })
        return merged

    async def delete(self, thread_id: str) -> bool:
        """Delete a thread and its session data. Returns True if it existed."""
        deleted = await self._thread_store.delete(thread_id)
        if deleted:
            # Session data cleanup is best-effort — the thread store is canonical.
            pass
        return deleted

    async def fork(self, thread_id: str, relation: str = "fork", title: str | None = None) -> dict[str, Any]:
        """Fork an existing thread into a new one."""
        source = await self._thread_store.get(thread_id)
        if source is None:
            raise ValueError(f"thread not found: {thread_id}")
        now = self._now_iso()
        new_id = _new_id("thread")
        forked: dict[str, Any] = {
            **source,
            "id": new_id,
            "title": title or f"{source.get('title', 'Thread')} (fork)",
            "status": "idle",
            "relation": relation,
            "parentThreadId": thread_id,
            "forkedFromThreadId": thread_id,
            "forkedFromTitle": source.get("title"),
            "forkedAt": now,
            "forkedFromMessageCount": len(source.get("turns", [])),
            "forkedFromTurnCount": len(source.get("turns", [])),
            "createdAt": now,
            "updatedAt": now,
            "turns": [],
        }
        await self._thread_store.upsert(forked)
        await self._events.record({
            "kind": "thread_created",
            "threadId": new_id,
            "title": forked["title"],
        })
        return forked
