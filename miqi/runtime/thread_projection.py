"""Codex-style projection over ThreadRuntime, LedgerRuntime, and ReplayRuntime."""

from __future__ import annotations

from miqi.runtime.ledger_runtime import LedgerItem, LedgerRuntime
from miqi.runtime.replay_runtime import ReplayRuntime, TurnTimeline
from miqi.runtime.stored_runtime import StoredThreadBundle
from miqi.runtime.thread_protocol import (
    ItemsView,
    ThreadItemView,
    ThreadStatusView,
    ThreadView,
    TurnView,
)
from miqi.runtime.thread_runtime import RuntimeThread, ThreadRuntime


class ThreadProjectionRuntime:
    """Converts runtime records (threads, ledger, replay) into Codex views."""

    def __init__(
        self,
        threads: ThreadRuntime,
        ledger: LedgerRuntime,
        replay: ReplayRuntime,
    ) -> None:
        self._threads = threads
        self._ledger = ledger
        self._replay = replay

    async def read_thread(
        self,
        thread_id: str,
        *,
        include_turns: bool,
        items_view: ItemsView = "summary",
    ) -> ThreadView:
        thread = await self._require_thread(thread_id)
        turns = await self.list_turns(thread_id, items_view=items_view) if include_turns else []
        return self._thread_view(
            thread,
            turns=turns,
            items_view=items_view if include_turns else "notLoaded",
        )

    async def list_turns(
        self, thread_id: str, *, items_view: ItemsView = "summary"
    ) -> list[TurnView]:
        timelines = await self._replay.get_thread_timeline(thread_id)
        return [self._turn_view(timeline, items_view=items_view) for timeline in timelines]

    async def _require_thread(self, thread_id: str) -> RuntimeThread:
        thread = await self._threads.get_thread(thread_id)
        if thread is None:
            raise KeyError(thread_id)
        return thread

    def _thread_view(
        self,
        thread: RuntimeThread,
        *,
        turns: list[TurnView],
        items_view: ItemsView,
    ) -> ThreadView:
        status = "archived" if thread.status == "archived" else "idle"
        return ThreadView(
            id=thread.thread_id,
            session_id=thread.session_id,
            status=ThreadStatusView(status),
            name=thread.title,
            parent_thread_id=thread.parent_thread_id,
            forked_from_id=getattr(thread, "forked_from_id", None),
            archived=thread.status == "archived",
            ephemeral=bool(getattr(thread, "ephemeral", False)),
            turns=turns,
            created_at=thread.created_at,
            updated_at=thread.updated_at,
            items_view=items_view,
        )

    def _turn_view(self, timeline: TurnTimeline, *, items_view: ItemsView) -> TurnView:
        items: list[ThreadItemView] = []
        if items_view != "notLoaded":
            if timeline.user_input is not None:
                items.append(ThreadItemView(
                    type="userMessage",
                    id=f"{timeline.turn_id}:user",
                    payload={"content": [{"type": "text", "text": timeline.user_input}]},
                ))
            if timeline.assistant_text or timeline.assistant_deltas:
                text = timeline.assistant_text or "".join(timeline.assistant_deltas)
                items.append(ThreadItemView(
                    type="agentMessage",
                    id=f"{timeline.turn_id}:agent",
                    payload={"text": text},
                ))
            if items_view == "full":
                for tool in timeline.tool_calls:
                    items.append(ThreadItemView(
                        type="mcpToolCall" if tool.name.startswith("mcp.") else "commandExecution",
                        id=tool.tool_call_id,
                        payload={
                            "status": tool.status,
                            "tool": tool.name,
                            "result": tool.result,
                        },
                    ))
        return TurnView(
            id=timeline.turn_id,
            thread_id=timeline.thread_id,
            status=timeline.status,
            items_view=items_view,
            items=items,
            started_at=timeline.started_at,
            completed_at=timeline.completed_at,
        )


# ── Stored-record projection (no live RuntimeSession needed) ──────────────


def project_stored_thread(
    bundle: StoredThreadBundle,
    *,
    include_turns: bool,
    items_view: ItemsView = "summary",
) -> ThreadView:
    """Project a stored thread bundle into a Codex ThreadView."""
    turns = (
        project_stored_turns(bundle.thread.thread_id, bundle.ledger_items, items_view=items_view)
        if include_turns
        else []
    )
    status = "archived" if bundle.thread.status == "archived" else "notLoaded"
    return ThreadView(
        id=bundle.thread.thread_id,
        session_id=bundle.thread.session_id,
        status=ThreadStatusView(status),
        name=bundle.thread.title,
        parent_thread_id=bundle.thread.parent_thread_id,
        forked_from_id=getattr(bundle.thread, "forked_from_id", None),
        archived=bundle.thread.status == "archived",
        ephemeral=bool(getattr(bundle.thread, "ephemeral", False)),
        turns=turns,
        created_at=bundle.thread.created_at,
        updated_at=bundle.thread.updated_at,
        items_view=items_view if include_turns else "notLoaded",
    )


def project_stored_turns(
    thread_id: str,
    ledger_items: list[LedgerItem],
    *,
    items_view: ItemsView = "summary",
) -> list[TurnView]:
    """Project ledger items into Codex TurnViews without a live ReplayRuntime."""
    # Group items by turn_id and record first appearance seq
    seen: dict[str, int] = {}
    for item in ledger_items:
        if item.turn_id and item.turn_id not in seen:
            seen[item.turn_id] = item.seq

    turns: list[TurnView] = []
    for turn_id in sorted(seen.keys(), key=lambda tid: seen[tid]):
        items = [item for item in ledger_items if item.turn_id == turn_id]
        # Use ReplayRuntime._build_timeline via __new__ — the method only
        # references self for the @staticmethod _safe_payload, so an
        # uninitialised instance is safe.
        replay = ReplayRuntime.__new__(ReplayRuntime)
        timeline = ReplayRuntime._build_timeline(replay, thread_id, turn_id, items)

        # ThreadProjectionRuntime._turn_view does not reference self.
        proj = ThreadProjectionRuntime.__new__(ThreadProjectionRuntime)
        turns.append(ThreadProjectionRuntime._turn_view(proj, timeline, items_view=items_view))
    return turns
