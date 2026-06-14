"""Tests for ReplayInspector — live-independent replay/debug views."""

from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_stored_inspector_builds_thread_document(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_inspector import ReplayInspector
    from miqi.runtime.thread_runtime import ThreadRuntime

    db = tmp_path / ".miqi-runtime" / "runtime.db"
    threads = ThreadRuntime(db, session_id="client-a:default")
    ledger = LedgerRuntime(db, session_id="client-a:default")
    await threads.initialize()
    await ledger.initialize()
    try:
        await threads.create_thread(title="T", thread_id="thread-1")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="turn_started")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="message", role="user", content="hello")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="assistant_delta", content="hi")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="turn_completed")

        inspector = ReplayInspector(db, client_id="client-a")
        document = await inspector.build_thread_document("thread-1")

        assert document["threadId"] == "thread-1"
        assert document["source"] == "stored"
        assert document["documentHash"].startswith("sha256:")
        assert document["turns"][0]["turn_id"] == "turn-1"
        assert document["integrity"]["ok"] is True
    finally:
        await ledger.close()
        await threads.close()


@pytest.mark.asyncio
async def test_integrity_detects_history_ledger_provider_message_mismatch(tmp_path):
    from miqi.runtime.history_runtime import HistoryItem
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_inspector import ReplayInspector
    from miqi.runtime.stored_runtime import StoredRuntimeReader
    from miqi.runtime.thread_runtime import ThreadRuntime

    db = tmp_path / ".miqi-runtime" / "runtime.db"
    threads = ThreadRuntime(db, session_id="client-a:default")
    ledger = LedgerRuntime(db, session_id="client-a:default")
    await threads.initialize()
    await ledger.initialize()
    try:
        await threads.create_thread(title="T", thread_id="thread-1")
        await ledger.append_item(thread_id="thread-1", turn_id="turn-1", item_type="message", role="user", content="ledger")
        reader = StoredRuntimeReader(db, client_id="client-a")
        await reader._write_history_items(
            "client-a:default",
            "thread-1",
            [HistoryItem("h1", "thread-1", "turn-1", "user", "history", {}, 1.0)],
        )

        inspector = ReplayInspector(db, client_id="client-a")
        report = await inspector.integrity_report("thread-1")

        assert report.ok is False
        assert any(check.name == "providerHistoryMatchesLedger" and not check.ok for check in report.checks)
    finally:
        await ledger.close()
        await threads.close()
