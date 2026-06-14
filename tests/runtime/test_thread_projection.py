"""Tests for ThreadProjectionRuntime — converts runtime data into Codex views."""

import pytest

from miqi.runtime.ledger_runtime import LedgerRuntime
from miqi.runtime.replay_runtime import ReplayRuntime
from miqi.runtime.thread_projection import ThreadProjectionRuntime
from miqi.runtime.thread_runtime import ThreadRuntime


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
