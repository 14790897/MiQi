"""Tests for HistoryRuntime — persistent turn and message history."""

import pytest

from miqi.runtime.history_runtime import HistoryRuntime, HistoryItem


@pytest.mark.asyncio
async def test_history_runtime_appends_and_loads_messages(tmp_path):
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()

    await runtime.append_item(HistoryItem(
        item_id="i1",
        thread_id="thread-1",
        turn_id="turn-1",
        role="user",
        content="hello",
    ))
    await runtime.append_item(HistoryItem(
        item_id="i2",
        thread_id="thread-1",
        turn_id="turn-1",
        role="assistant",
        content="hi",
    ))

    items = await runtime.load_items("thread-1")

    assert [item.role for item in items] == ["user", "assistant"]
    assert [item.content for item in items] == ["hello", "hi"]


@pytest.mark.asyncio
async def test_history_runtime_records_turn_lifecycle(tmp_path):
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()

    await runtime.start_turn("turn-1", thread_id="thread-1")
    await runtime.complete_turn(
        "turn-1",
        status="completed",
        tools_used=["read_file"],
        token_usage={"prompt_tokens": 10, "completion_tokens": 5},
    )

    turn = await runtime.get_turn("turn-1")

    assert turn is not None
    assert turn.status == "completed"
    assert turn.tools_used == ["read_file"]
    assert turn.token_usage["prompt_tokens"] == 10
    assert turn.completed_at is not None


@pytest.mark.asyncio
async def test_history_runtime_append_message_convenience(tmp_path):
    """append_message() creates an item with auto-generated id."""
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()

    item = await runtime.append_message(
        thread_id="thread-1",
        turn_id="turn-1",
        role="user",
        content="convenience test",
    )

    assert item.item_id
    assert item.role == "user"
    assert item.content == "convenience test"

    items = await runtime.load_items("thread-1")
    assert len(items) == 1


@pytest.mark.asyncio
async def test_history_runtime_load_messages_formats_for_provider(tmp_path):
    """load_messages() returns provider-friendly dicts."""
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()

    await runtime.append_message(
        thread_id="t1", turn_id="turn-1", role="user", content="hello",
    )
    await runtime.append_message(
        thread_id="t1", turn_id="turn-1", role="assistant", content="hi there",
    )

    messages = await runtime.load_messages("t1")
    assert len(messages) == 2
    assert messages[0] == {"role": "user", "content": "hello"}
    assert messages[1] == {"role": "assistant", "content": "hi there"}


# ---------------------------------------------------------------------------
# Phase 19: compaction persistence
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_replace_messages_with_compaction_replaces_visible_history(tmp_path):
    """replace_messages_with_compaction() clears old items and inserts replacement."""
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    await runtime.append_message(thread_id="t1", turn_id="a", role="user", content="old")
    await runtime.append_message(thread_id="t1", turn_id="a", role="assistant", content="old answer")

    await runtime.replace_messages_with_compaction(
        "t1",
        "compact-1",
        [{"role": "system", "content": "[summary]"}],
    )

    messages = await runtime.load_messages("t1")
    assert messages == [{"role": "system", "content": "[summary]"}]
