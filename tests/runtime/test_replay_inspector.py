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


@pytest.mark.asyncio
async def test_integrity_detects_duplicate_or_non_monotonic_seq(tmp_path):
    import aiosqlite
    from miqi.runtime.replay_inspector import ReplayInspector
    from miqi.runtime.stored_runtime import StoredRuntimeReader

    db = tmp_path / ".miqi-runtime" / "runtime.db"
    reader = StoredRuntimeReader(db, client_id="client-a")
    await reader._ensure_schema()
    async with aiosqlite.connect(str(db)) as conn:
        await conn.execute(
            """INSERT INTO runtime_threads
               (thread_id, session_id, title, status, created_at, updated_at, metadata_json)
               VALUES ('thread-1', 'client-a:default', 'T', 'active', 1, 1, '{}')"""
        )
        await conn.execute(
            """INSERT INTO runtime_ledger_items
               (item_id, session_id, thread_id, turn_id, seq, item_type, role, content, payload_json, created_at)
               VALUES ('i1', 'client-a:default', 'thread-1', 'turn-1', 2, 'message', 'user', 'hello', '{}', 1)"""
        )
        await conn.execute(
            """INSERT INTO runtime_ledger_items
               (item_id, session_id, thread_id, turn_id, seq, item_type, role, content, payload_json, created_at)
               VALUES ('i2', 'client-a:default', 'thread-1', 'turn-2', 2, 'message', 'user', 'again', '{}', 2)"""
        )
        await conn.commit()

    report = await ReplayInspector(db, client_id="client-a").integrity_report("thread-1")

    assert any(check.name == "ledgerSeqMonotonic" and not check.ok for check in report.checks)


@pytest.mark.asyncio
async def test_integrity_detects_dangling_tool_exec_and_approval(tmp_path):
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
        await ledger.append_item(
            thread_id="thread-1",
            turn_id="turn-1",
            item_type="tool_call_started",
            payload={"tool_call_id": "tc-1", "name": "exec"},
        )
        await ledger.append_item(
            thread_id="thread-1",
            turn_id="turn-1",
            item_type="exec_started",
            payload={"tool_call_id": "tc-1", "command": "sleep 10"},
        )
        await ledger.append_item(
            thread_id="thread-1",
            turn_id="turn-1",
            item_type="approval_requested",
            payload={"approval_id": "ap-1", "tool_call_id": "tc-1"},
        )

        report = await ReplayInspector(db, client_id="client-a").integrity_report("thread-1")

        dangling = next(check for check in report.checks if check.name == "noDanglingOperations")
        assert dangling.ok is False
        assert dangling.details["pendingTools"]
        assert dangling.details["pendingExecs"]
        assert dangling.details["pendingApprovals"]
    finally:
        await ledger.close()
        await threads.close()
