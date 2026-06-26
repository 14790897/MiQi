"""Turn lifecycle service for KUN runtime.

Aligns with KUN ``services/turn-service.ts``.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable, Literal

from miqi.kun_runtime.cancellation import CancellationToken, InflightTracker
from miqi.kun_runtime.event_recorder import RuntimeEventRecorder
from miqi.kun_runtime.stores import FileSessionStore, FileThreadStore


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")


def _new_id(prefix: str) -> str:
    import uuid
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


class TurnService:
    """Owns the turn lifecycle: start, finish, abort, steer, compact.

    The agent loop calls into this service instead of mutating state directly.
    """

    def __init__(
        self,
        thread_store: FileThreadStore,
        session_store: FileSessionStore,
        events: RuntimeEventRecorder,
        inflight: InflightTracker,
        now_iso: Callable[[], str] | None = None,
    ):
        self._thread_store = thread_store
        self._session_store = session_store
        self._events = events
        self._inflight = inflight
        self._now_iso = now_iso or _utc_now_iso

        # turnId → CancellationToken
        self._abort_tokens: dict[str, CancellationToken] = {}
        # threadId → list of steered text strings pending drain
        self._steering: dict[str, list[str]] = {}

    # ── Start / Finish / Interrupt ──────────────────────────────────────

    async def start_turn(self, thread_id: str, prompt: str, **kwargs: Any) -> dict[str, Any]:
        """Create a new turn and user item, record events, return turn info."""
        thread = await self._thread_store.get(thread_id)
        if thread is None:
            raise ValueError(f"thread not found: {thread_id}")

        now = self._now_iso()
        turn_id = _new_id("turn")
        user_item_id = f"item_{turn_id}_user"

        turn: dict[str, Any] = {
            "id": turn_id,
            "threadId": thread_id,
            "status": "running",
            "prompt": prompt,
            "model": kwargs.get("model"),
            "reasoningEffort": kwargs.get("reasoningEffort"),
            "mode": kwargs.get("mode"),
            "steering": [],
            "createdAt": now,
            "startedAt": now,
            "items": [],
            "attachmentIds": kwargs.get("attachmentIds", []),
            "activeSkillIds": [],
            "injectedMemoryIds": [],
        }

        user_item: dict[str, Any] = {
            "id": user_item_id,
            "turnId": turn_id,
            "threadId": thread_id,
            "role": "user",
            "status": "completed",
            "kind": "user_message",
            "createdAt": now,
            "finishedAt": now,
            "text": prompt,
        }

        # Persist
        thread.setdefault("turns", []).append(turn)
        thread["status"] = "running"
        thread["updatedAt"] = now
        await self._thread_store.upsert(thread)
        await self._session_store.append_item(thread_id, user_item)

        # Events
        await self._events.record({"kind": "turn_started", "threadId": thread_id, "turnId": turn_id})
        await self._events.record({
            "kind": "item_created", "threadId": thread_id, "turnId": turn_id,
            "itemId": user_item_id, "item": user_item,
        })

        # Set up cancellation and inflight tracking
        self._abort_tokens[turn_id] = CancellationToken()
        self._inflight.begin({"id": turn_id, "kind": "model", "threadId": thread_id, "turnId": turn_id})
        self._steering.setdefault(thread_id, [])

        return {
            "threadId": thread_id,
            "turnId": turn_id,
            "userMessageItemId": user_item_id,
        }

    async def finish_turn(
        self,
        thread_id: str,
        turn_id: str,
        status: Literal["completed", "failed", "aborted"],
        error: str | None = None,
    ) -> None:
        """Close a turn with final status."""
        self._abort_tokens.pop(turn_id, None)
        self._inflight.end(turn_id)

        thread = await self._thread_store.get(thread_id)
        if thread is None:
            return

        now = self._now_iso()
        for turn in thread.get("turns", []):
            if turn.get("id") == turn_id:
                turn["status"] = status
                turn["finishedAt"] = now
                if error:
                    turn["error"] = error
                # Finalize open items
                for item in turn.get("items", []):
                    if item.get("status") in ("pending", "running"):
                        if item.get("kind") == "approval":
                            item["status"] = "expired"
                        elif item.get("kind") == "user_input":
                            item["status"] = "cancelled"
                        else:
                            item["status"] = status if status != "aborted" else "aborted"
                        item["finishedAt"] = now

        thread["status"] = "idle"
        thread["updatedAt"] = now
        await self._thread_store.upsert(thread)

        # Event
        kind_map = {"completed": "turn_completed", "failed": "turn_failed", "aborted": "turn_aborted"}
        event: dict[str, object] = {
            "kind": kind_map[status],
            "threadId": thread_id,
            "turnId": turn_id,
        }
        if error:
            event["message"] = error
        await self._events.record(event)

        if error:
            await self._session_store.append_item(thread_id, {
                "id": f"item_{turn_id}_error",
                "turnId": turn_id,
                "threadId": thread_id,
                "role": "system",
                "status": "failed",
                "kind": "error",
                "createdAt": now,
                "message": error,
            })

    async def interrupt_turn(
        self, thread_id: str, turn_id: str, discard: bool = False
    ) -> dict[str, Any]:
        """Abort a running turn. Optionally discard generated items."""
        token = self._abort_tokens.get(turn_id)
        if token:
            token.cancel()

        self._inflight.end(turn_id)

        if discard:
            items = await self._session_store.load_items(thread_id)
            kept = [i for i in items if i.get("turnId") != turn_id or i.get("kind") == "user_message"]
            await self._session_store.rewrite_items(thread_id, kept)

        thread = await self._thread_store.get(thread_id)
        if thread:
            now = self._now_iso()
            for turn in thread.get("turns", []):
                if turn.get("id") == turn_id:
                    turn["status"] = "aborted"
                    turn["finishedAt"] = now
                    if discard:
                        turn["items"] = [i for i in turn.get("items", []) if i.get("kind") == "user_message"]
            thread["status"] = "idle"
            thread["updatedAt"] = now
            await self._thread_store.upsert(thread)

        await self._events.record({
            "kind": "turn_aborted",
            "threadId": thread_id,
            "turnId": turn_id,
        })
        return {"threadId": thread_id, "turnId": turn_id, "status": "aborted"}

    # ── Steering ────────────────────────────────────────────────────────

    async def steer_turn(self, thread_id: str, turn_id: str, text: str) -> None:
        """Enqueue text to be injected as a user message mid-turn."""
        self._steering.setdefault(thread_id, [])
        self._steering[thread_id].append(text)
        await self._events.record({
            "kind": "turn_steered",
            "threadId": thread_id,
            "turnId": turn_id,
            "text": text,
        })

    def drain_steering(self, thread_id: str) -> list[str]:
        """Drain and clear all pending steering text for *thread_id*."""
        pending = self._steering.pop(thread_id, [])
        return pending

    # ── Items ───────────────────────────────────────────────────────────

    async def apply_item(self, thread_id: str, item: dict[str, Any]) -> None:
        """Append an item to the turn and record an event."""
        await self._session_store.append_item(thread_id, item)
        await self._events.record({
            "kind": "item_created",
            "threadId": thread_id,
            "turnId": item.get("turnId", ""),
            "itemId": item.get("id", ""),
            "item": item,
        })

    async def update_item(
        self, thread_id: str, item_id: str, patch: dict[str, Any]
    ) -> dict[str, Any] | None:
        """Update an item in the session store and record an event."""
        updated = await self._session_store.update_item(thread_id, item_id, patch)
        if updated is None:
            return None
        await self._events.record({
            "kind": "item_updated",
            "threadId": thread_id,
            "turnId": updated.get("turnId", ""),
            "itemId": item_id,
            "item": updated,
        })
        return updated

    async def get_turn(self, thread_id: str, turn_id: str) -> dict[str, Any] | None:
        """Return a turn record or None."""
        thread = await self._thread_store.get(thread_id)
        if thread is None:
            return None
        for turn in thread.get("turns", []):
            if turn.get("id") == turn_id:
                return turn
        return None

    # ── Cancellation ────────────────────────────────────────────────────

    def get_abort_token(self, turn_id: str) -> CancellationToken | None:
        """Return the CancellationToken for *turn_id*, or None."""
        return self._abort_tokens.get(turn_id)
