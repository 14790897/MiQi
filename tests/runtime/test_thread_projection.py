"""Tests for ThreadProjectionRuntime — converts runtime data into Codex views."""

import time

import pytest

from miqi.runtime.ledger_runtime import LedgerItem, LedgerRuntime
from miqi.runtime.replay_runtime import ReplayRuntime
from miqi.runtime.stored_runtime import StoredThreadBundle
from miqi.runtime.thread_projection import (
    ThreadProjectionRuntime,
    project_stored_thread,
    project_stored_turns,
)
from miqi.runtime.thread_runtime import RuntimeThread, ThreadRuntime


@pytest.mark.asyncio
async def test_projection_reads_thread_without_turns(tmp_path):
    db = tmp_path / "runtime.db"
    threads = ThreadRuntime(db, session_id="s1")
    ledger = LedgerRuntime(db, session_id="s1")
    await threads.initialize()
    await ledger.initialize()
    try:
        await threads.create_thread(title="Example", thread_id="thread-1")
        projection = ThreadProjectionRuntime(threads, ledger, ReplayRuntime(ledger))
        view = await projection.read_thread("thread-1", include_turns=False)
        data = view.to_dict()
        assert data["id"] == "thread-1"
        assert data["turns"] == []
        assert data["itemsView"] == "notLoaded"
    finally:
        await ledger.close()
        await threads.close()


@pytest.mark.asyncio
async def test_projection_reads_turn_summary_items(tmp_path):
    db = tmp_path / "runtime.db"
    threads = ThreadRuntime(db, session_id="s1")
    ledger = LedgerRuntime(db, session_id="s1")
    await threads.initialize()
    await ledger.initialize()
    try:
        await threads.create_thread(title="Example", thread_id="thread-1")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="turn_started")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="message", role="user", content="hello")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="assistant_delta", content="hi")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="turn_completed")
        projection = ThreadProjectionRuntime(threads, ledger, ReplayRuntime(ledger))
        turns = await projection.list_turns("thread-1", items_view="summary")
        assert len(turns) == 1
        data = turns[0].to_dict()
        assert data["status"] == "completed"
        assert data["items"][0]["type"] == "userMessage"
        assert data["items"][1]["type"] == "agentMessage"
    finally:
        await ledger.close()
        await threads.close()


# ── Stored projection tests ────────────────────────────────────────────────


def _item(seq: int, item_type: str, *, turn_id: str | None = None, role=None, content="", payload=None):
    return LedgerItem(
        item_id=f"item-{seq}",
        session_id="client-a:default",
        thread_id="thread-1",
        turn_id=turn_id,
        seq=seq,
        item_type=item_type,
        role=role,
        content=content,
        payload=payload or {},
        created_at=1000.0 + seq,
    )


def test_project_stored_thread_without_turns_is_not_loaded():
    thread = RuntimeThread(
        thread_id="thread-1",
        session_id="client-a:default",
        title="Stored",
        status="active",
        parent_thread_id=None,
        created_at=time.time(),
        updated_at=time.time(),
    )
    view = project_stored_thread(
        StoredThreadBundle(thread=thread, ledger_items=[]),
        include_turns=False,
    )
    data = view.to_dict()
    assert data["status"] == {"type": "notLoaded"}
    assert data["itemsView"] == "notLoaded"
    assert data["turns"] == []


def test_project_stored_turns_reconstructs_user_and_agent_messages():
    ledger_items = [
        _item(1, "turn_started", turn_id="turn-1"),
        _item(2, "message", turn_id="turn-1", role="user", content="hello"),
        _item(3, "assistant_delta", turn_id="turn-1", content="hi"),
        _item(4, "turn_completed", turn_id="turn-1"),
    ]
    turns = project_stored_turns("thread-1", ledger_items, items_view="summary")
    data = turns[0].to_dict()
    assert data["id"] == "turn-1"
    assert data["status"] == "completed"
    assert data["items"][0]["type"] == "userMessage"
    assert data["items"][1]["type"] == "agentMessage"


def test_project_stored_thread_archived_status():
    thread = RuntimeThread(
        thread_id="thread-archived",
        session_id="client-a:default",
        title="Archived",
        status="archived",
        parent_thread_id=None,
        created_at=time.time(),
        updated_at=time.time(),
    )
    view = project_stored_thread(
        StoredThreadBundle(thread=thread, ledger_items=[]),
        include_turns=False,
    )
    data = view.to_dict()
    assert data["status"] == {"type": "archived"}
    assert data["archived"] is True
