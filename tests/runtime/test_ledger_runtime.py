"""Tests for LedgerRuntime — append-only item log (Phase 24)."""

import pytest


@pytest.mark.asyncio
async def test_ledger_appends_and_loads_items_in_sequence(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime

    runtime = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await runtime.initialize()
    try:
        first = await runtime.append_item(
            thread_id="thread-1",
            turn_id="turn-1",
            item_type="turn_started",
            payload={"agent": "main"},
        )
        second = await runtime.append_item(
            thread_id="thread-1",
            turn_id="turn-1",
            item_type="message",
            role="user",
            content="hello",
            payload={"message_fields": {}},
        )

        items = await runtime.load_items("thread-1")

        assert [item.item_id for item in items] == [first.item_id, second.item_id]
        assert [item.seq for item in items] == [1, 2]
        assert items[0].item_type == "turn_started"
        assert items[1].role == "user"
        assert items[1].content == "hello"
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_ledger_is_session_scoped(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime

    db_path = tmp_path / "runtime.db"
    one = LedgerRuntime(db_path, session_id="sess-1")
    two = LedgerRuntime(db_path, session_id="sess-2")
    await one.initialize()
    await two.initialize()
    try:
        await one.append_item(
            thread_id="shared-thread",
            turn_id="turn-1",
            item_type="message",
            role="user",
            content="from one",
            payload={},
        )
        await two.append_item(
            thread_id="shared-thread",
            turn_id="turn-2",
            item_type="message",
            role="user",
            content="from two",
            payload={},
        )

        assert [item.content for item in await one.load_items("shared-thread")] == ["from one"]
        assert [item.content for item in await two.load_items("shared-thread")] == ["from two"]
    finally:
        await one.close()
        await two.close()


@pytest.mark.asyncio
async def test_ledger_reconstructs_provider_messages(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime

    runtime = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await runtime.initialize()
    try:
        await runtime.append_item(
            thread_id="thread-1",
            turn_id="turn-1",
            item_type="message",
            role="user",
            content="hello",
            payload={"message_fields": {}},
        )
        await runtime.append_item(
            thread_id="thread-1",
            turn_id="turn-1",
            item_type="message",
            role="assistant",
            content="hi",
            payload={"message_fields": {"tool_calls": [{"id": "call-1"}]}},
        )

        messages = await runtime.load_provider_messages("thread-1")

        assert messages == [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi", "tool_calls": [{"id": "call-1"}]},
        ]
    finally:
        await runtime.close()
