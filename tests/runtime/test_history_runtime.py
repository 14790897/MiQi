"""Tests for HistoryRuntime — persistent turn and message history."""

from types import SimpleNamespace

import pytest

from miqi.runtime import history_runtime
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
    await runtime.close()


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
    await runtime.close()


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
    await runtime.close()


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
    await runtime.close()


@pytest.mark.asyncio
async def test_append_item_rejects_invalid_role(tmp_path):
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    try:
        with pytest.raises(ValueError, match="Invalid history role"):
            await runtime.append_item(HistoryItem(
                item_id="bad-role",
                thread_id="thread-1",
                turn_id="turn-1",
                role="admin",
                content="should not persist",
            ))

        items = await runtime.load_items("thread-1")
        assert items == []
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_append_item_truncates_large_content_and_payload(
    tmp_path,
    monkeypatch,
):
    monkeypatch.setattr(
        history_runtime,
        "MAX_HISTORY_CONTENT_CHARS",
        32,
        raising=False,
    )
    monkeypatch.setattr(
        history_runtime,
        "MAX_HISTORY_PAYLOAD_JSON_CHARS",
        64,
        raising=False,
    )

    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    try:
        await runtime.append_item(HistoryItem(
            item_id="large-item",
            thread_id="thread-1",
            turn_id="turn-1",
            role="tool",
            content="x" * 128,
            payload={"result": "y" * 256},
        ))

        items = await runtime.load_items("thread-1")
        assert len(items) == 1
        item = items[0]
        assert len(item.content) <= history_runtime.MAX_HISTORY_CONTENT_CHARS
        assert item.content.endswith("<truncated>")
        assert item.payload["truncated"] is True
        assert item.payload["original_size_chars"] > (
            history_runtime.MAX_HISTORY_PAYLOAD_JSON_CHARS
        )
        assert len(item.payload["preview"]) <= (
            history_runtime.MAX_HISTORY_PAYLOAD_JSON_CHARS
        )
    finally:
        await runtime.close()


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
    await runtime.close()


@pytest.mark.asyncio
async def test_compaction_record_stores_audit_metadata(tmp_path):
    """The runtime_compactions row must store messages_before/after and
    tokens_saved, not just replacement_json."""
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    await runtime.append_message(thread_id="t1", turn_id="a", role="user", content="old")
    await runtime.append_message(thread_id="t1", turn_id="a", role="assistant", content="old answer")

    await runtime.replace_messages_with_compaction(
        "t1",
        "compact-1",
        [{"role": "system", "content": "[summary]"}],
        messages_before=2,
        messages_after=1,
        tokens_saved=50,
    )

    # Query the compaction record directly
    import aiosqlite, json
    async with aiosqlite.connect(str(tmp_path / "runtime.db")) as db:
        db.row_factory = aiosqlite.Row
        cursor = await db.execute(
            "SELECT * FROM runtime_compactions WHERE thread_id = ? AND session_id = ?",
            ("t1", "test-session"),
        )
        row = await cursor.fetchone()

    assert row is not None, "Compaction record should exist"
    assert row["messages_before"] == 2
    assert row["messages_after"] == 1
    assert row["tokens_saved"] == 50
    assert json.loads(row["replacement_json"]) == [{"role": "system", "content": "[summary]"}]
    await runtime.close()


@pytest.mark.asyncio
async def test_compaction_replacement_order_does_not_fall_back_to_item_id(
    tmp_path,
    monkeypatch,
):
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    try:
        await runtime.append_message(
            thread_id="t1", turn_id="a", role="user", content="old"
        )

        uuids = iter(["compaction-id", "b-system", "a-user"])
        monkeypatch.setattr(
            history_runtime,
            "time",
            SimpleNamespace(time=lambda: 1000.0),
        )
        monkeypatch.setattr(history_runtime.uuid, "uuid4", lambda: next(uuids))

        await runtime.replace_messages_with_compaction(
            "t1",
            "compact-1",
            [
                {"role": "system", "content": "[summary]"},
                {"role": "user", "content": "recent message"},
            ],
        )

        messages = await runtime.load_messages("t1")
        assert [message["role"] for message in messages] == ["system", "user"]
        assert messages[0]["content"] == "[summary]"
    finally:
        await runtime.close()


# ── Phase 36: history deletion for rollback ──────────────────────────────


@pytest.mark.asyncio
async def test_history_delete_turn_messages(tmp_path):
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="s1")
    await runtime.initialize()
    try:
        await runtime.append_message(
            thread_id="t1", turn_id="turn-1", role="user", content="one"
        )
        await runtime.append_message(
            thread_id="t1", turn_id="turn-2", role="user", content="two"
        )
        removed = await runtime.delete_turn_items("t1", ["turn-2"])
        assert removed == 1
        messages = await runtime.load_messages("t1")
        assert [m["content"] for m in messages] == ["one"]
    finally:
        await runtime.close()


# ── Issue #84: get_turn must degrade on corrupted JSON columns ────────────


@pytest.mark.asyncio
async def test_get_turn_degrades_on_corrupted_tools_used_json(tmp_path):
    """A corrupted tools_used_json must degrade to [], not crash get_turn.

    Parity with load_items, which already skips corrupted payload_json with a
    warning. Without the fix, get_turn raises json.JSONDecodeError and the whole
    turn record fails to load.
    """
    import aiosqlite

    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    try:
        await runtime.start_turn("turn-1", thread_id="thread-1")
        await runtime.complete_turn(
            "turn-1", status="completed",
            tools_used=["read_file"],
            token_usage={"prompt_tokens": 10},
        )

        # Corrupt the tools_used_json column directly in the DB.
        async with aiosqlite.connect(tmp_path / "runtime.db") as conn:
            await conn.execute(
                "UPDATE runtime_turns SET tools_used_json = ? WHERE turn_id = ?",
                ("{not valid json", "turn-1"),
            )
            await conn.commit()

        # The DB connection caches state; reopen on a fresh runtime so the
        # corruption is read back.
        await runtime.close()
        runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
        await runtime.initialize()

        turn = await runtime.get_turn("turn-1")

        # Degrades instead of crashing: turn still loads, tools_used falls back.
        assert turn is not None
        assert turn.status == "completed"
        assert turn.tools_used == []
        # Untouched column still loads.
        assert turn.token_usage == {"prompt_tokens": 10}
    finally:
        await runtime.close()


@pytest.mark.asyncio
async def test_get_turn_degrades_on_corrupted_token_usage_json(tmp_path):
    """A corrupted token_usage_json must degrade to {}, not crash get_turn."""
    import aiosqlite

    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    try:
        await runtime.start_turn("turn-1", thread_id="thread-1")
        await runtime.complete_turn(
            "turn-1", status="completed",
            tools_used=["read_file"],
            token_usage={"prompt_tokens": 10},
        )

        async with aiosqlite.connect(tmp_path / "runtime.db") as conn:
            await conn.execute(
                "UPDATE runtime_turns SET token_usage_json = ? WHERE turn_id = ?",
                ("<<broken>>", "turn-1"),
            )
            await conn.commit()

        await runtime.close()
        runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
        await runtime.initialize()

        turn = await runtime.get_turn("turn-1")

        assert turn is not None
        assert turn.token_usage == {}
        # Untouched column still loads.
        assert turn.tools_used == ["read_file"]
    finally:
        await runtime.close()


# ── Issue #85: compaction must not crash on a message missing 'role' ──────


@pytest.mark.asyncio
async def test_replace_messages_with_compaction_skips_missing_role(tmp_path):
    """A replacement message missing the 'role' key must not crash compaction.

    Without the fix, msg["role"] raises KeyError, the compaction transaction
    rolls back, and the user sees no compaction effect at all. The same loop
    already used msg.get("content") — role should be accessed the same way.
    """
    runtime = HistoryRuntime(tmp_path / "runtime.db", session_id="test-session")
    await runtime.initialize()
    await runtime.append_message(thread_id="t1", turn_id="a", role="user", content="old")

    # A replacement batch where one message is missing 'role' (e.g. legacy /
    # abnormally-written data). The other message is well-formed.
    await runtime.replace_messages_with_compaction(
        "t1",
        "compact-1",
        [
            {"content": "no role here"},          # missing role
            {"role": "system", "content": "[summary]"},
        ],
    )
    try:
        messages = await runtime.load_messages("t1")
        # Compaction completes: the well-formed message survives; the missing-role
        # one gets a default role rather than crashing the whole transaction.
        assert {"role": "system", "content": "[summary]"} in messages
        assert len(messages) == 2
        roles = [m["role"] for m in messages]
        assert "unknown" in roles, f"missing-role msg should default to 'unknown', got {roles}"
    finally:
        await runtime.close()
