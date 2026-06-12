"""Tests for ReplayRuntime — ledger-backed turn/message reconstruction (Phase 25)."""

import pytest


# ── Helpers ──────────────────────────────────────────────────────────────


async def _populate_ledger_with_complete_turn(ledger, *, thread_id="thread-1", turn_id="turn-1"):
    """Populate a ledger with a complete turn: start, user msg, deltas, tool, exec, end."""
    import time

    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="turn_started", payload={"agent_name": "main"},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="message", role="user", content="read file",
        payload={"message_fields": {}},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="assistant_delta", content="Let ",
        payload={"index": 0},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="assistant_delta", content="me check.",
        payload={"index": 1},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="tool_call_started",
        payload={"tool_call_id": "tc-1", "name": "read_file", "arguments": {"path": "x.txt"}},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="exec_started",
        payload={"tool_call_id": "tc-1", "command": "cat x.txt", "cwd": "/tmp", "sandbox_type": "none"},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="exec_output_delta", content="hello world",
        payload={"tool_call_id": "tc-1", "stream": "stdout"},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="exec_completed",
        payload={"tool_call_id": "tc-1", "exit_code": 0, "duration_ms": 42, "output_size": 11},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="tool_call_completed",
        payload={
            "tool_call_id": "tc-1", "result": "hello world", "duration_ms": 42,
            "retry_count": 0, "permission_verdict": "allow", "sandbox_type": "none",
        },
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="message", role="assistant", content="Let me check.",
        payload={"message_fields": {}},
    )
    await ledger.append_item(
        thread_id=thread_id, turn_id=turn_id,
        item_type="turn_completed",
        payload={"final_content": "Let me check.", "token_usage": {"input": 10, "output": 5}},
    )


# ── Provider Message Reconstruction ──────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_reconstructs_provider_messages(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await _populate_ledger_with_complete_turn(ledger)

        replay = ReplayRuntime(ledger)
        messages = await replay.get_provider_messages("thread-1")

        roles = [m["role"] for m in messages]
        assert roles == ["user", "assistant"]
        assert messages[0]["content"] == "read file"
        assert messages[1]["content"] == "Let me check."
    finally:
        await ledger.close()


# ── Turn Timeline Reconstruction ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_reconstructs_turn_timeline(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await _populate_ledger_with_complete_turn(ledger)

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-1")

        assert timeline is not None
        assert timeline.turn_id == "turn-1"
        assert timeline.thread_id == "thread-1"
        assert timeline.status == "completed"
        assert timeline.user_input == "read file"
        assert timeline.assistant_text == "Let me check."
        assert timeline.assistant_deltas == ["Let ", "me check."]

        # Tool calls
        assert len(timeline.tool_calls) == 1
        tc = timeline.tool_calls[0]
        assert tc.tool_call_id == "tc-1"
        assert tc.name == "read_file"
        assert tc.arguments == {"path": "x.txt"}
        assert tc.status == "completed"
        assert tc.result == "hello world"
        assert tc.duration_ms == 42
        assert tc.permission_verdict == "allow"

        # Exec commands
        assert len(timeline.exec_commands) == 1
        ex = timeline.exec_commands[0]
        assert ex.tool_call_id == "tc-1"
        assert ex.command == "cat x.txt"
        assert ex.cwd == "/tmp"
        assert ex.output == "hello world"
        assert ex.exit_code == 0
        assert ex.status == "completed"

        assert timeline.started_at is not None
        assert timeline.completed_at is not None
    finally:
        await ledger.close()


@pytest.mark.asyncio
async def test_replay_lists_turns(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await _populate_ledger_with_complete_turn(ledger, turn_id="turn-a")
        await _populate_ledger_with_complete_turn(ledger, turn_id="turn-b")

        replay = ReplayRuntime(ledger)
        turns = await replay.list_turns("thread-1")

        assert turns == ["turn-a", "turn-b"]
    finally:
        await ledger.close()


@pytest.mark.asyncio
async def test_replay_get_thread_timeline(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await _populate_ledger_with_complete_turn(ledger, turn_id="turn-a")
        await _populate_ledger_with_complete_turn(ledger, turn_id="turn-b")

        replay = ReplayRuntime(ledger)
        timelines = await replay.get_thread_timeline("thread-1")

        assert len(timelines) == 2
        assert [t.turn_id for t in timelines] == ["turn-a", "turn-b"]
        for t in timelines:
            assert t.status == "completed"
    finally:
        await ledger.close()


# ── Session Isolation ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_session_isolation(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    db_path = tmp_path / "runtime.db"
    ledger_a = LedgerRuntime(db_path, session_id="sess-a")
    ledger_b = LedgerRuntime(db_path, session_id="sess-b")
    await ledger_a.initialize()
    await ledger_b.initialize()
    try:
        await ledger_a.append_item(
            thread_id="shared", turn_id="t1",
            item_type="turn_started", payload={},
        )
        await ledger_b.append_item(
            thread_id="shared", turn_id="t2",
            item_type="turn_started", payload={},
        )

        replay_a = ReplayRuntime(ledger_a)
        replay_b = ReplayRuntime(ledger_b)

        turns_a = await replay_a.list_turns("shared")
        turns_b = await replay_b.list_turns("shared")

        assert turns_a == ["t1"]
        assert turns_b == ["t2"]
    finally:
        await ledger_a.close()
        await ledger_b.close()


# ── Recovery: Aborted Turn ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_aborted_turn_timeline(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-aborted",
            item_type="turn_started", payload={"agent_name": "main"},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-aborted",
            item_type="message", role="user", content="long task",
            payload={"message_fields": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-aborted",
            item_type="tool_call_started",
            payload={"tool_call_id": "tc-1", "name": "slow_tool", "arguments": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-aborted",
            item_type="turn_aborted",
            payload={"reason": "User requested abort."},
        )

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-aborted")

        assert timeline.status == "aborted"
        assert timeline.user_input == "long task"
        assert len(timeline.tool_calls) == 1
        assert timeline.tool_calls[0].status == "pending"
    finally:
        await ledger.close()


# ── Recovery: Errored Turn ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_errored_turn_timeline(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-err",
            item_type="turn_started", payload={"agent_name": "main"},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-err",
            item_type="message", role="user", content="bad request",
            payload={"message_fields": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-err",
            item_type="error",
            content="Internal error occurred.",
            payload={"recoverable": False, "source": "task_runner"},
        )

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-err")

        assert timeline.status == "incomplete"  # No turn_completed/aborted marker
        assert len(timeline.errors) == 1
        assert timeline.errors[0]["source"] == "task_runner"
    finally:
        await ledger.close()


# ── Recovery: Dangling Tool Start ────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_dangling_tool_start_is_pending(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-dangle",
            item_type="turn_started", payload={"agent_name": "main"},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-dangle",
            item_type="tool_call_started",
            payload={"tool_call_id": "tc-dangle", "name": "unfinished_tool", "arguments": {}},
        )

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-dangle")

        assert len(timeline.tool_calls) == 1
        assert timeline.tool_calls[0].status == "pending"
        assert timeline.tool_calls[0].name == "unfinished_tool"
    finally:
        await ledger.close()


# ── Recovery: Dangling Exec Start ────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_dangling_exec_start_is_pending(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-exec-dangle",
            item_type="turn_started", payload={"agent_name": "main"},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-exec-dangle",
            item_type="exec_started",
            payload={"tool_call_id": "tc-ex", "command": "sleep 999", "cwd": "/", "sandbox_type": "none"},
        )

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-exec-dangle")

        assert len(timeline.exec_commands) == 1
        assert timeline.exec_commands[0].status == "pending"
        assert timeline.exec_commands[0].command == "sleep 999"
    finally:
        await ledger.close()


# ── Recovery: Streaming Deltas Merge ─────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_streaming_deltas_merge_to_assistant_text(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-deltas",
            item_type="turn_started", payload={"agent_name": "main"},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-deltas",
            item_type="message", role="user", content="hi",
            payload={"message_fields": {}},
        )
        for i, part in enumerate(["Hello", ", ", "world", "!"]):
            await ledger.append_item(
                thread_id="thread-1", turn_id="turn-deltas",
                item_type="assistant_delta", content=part,
                payload={"index": i},
            )

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-deltas")

        assert timeline.assistant_text == "Hello, world!"
        assert timeline.assistant_deltas == ["Hello", ", ", "world", "!"]
    finally:
        await ledger.close()


# ── Recovery: No Final Message, Deltas Only ──────────────────────────────


@pytest.mark.asyncio
async def test_replay_deltas_without_final_message(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-deltas-only",
            item_type="turn_started", payload={},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-deltas-only",
            item_type="message", role="user", content="q", payload={"message_fields": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-deltas-only",
            item_type="assistant_delta", content="streaming only, ",
            payload={"index": 0},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-deltas-only",
            item_type="assistant_delta", content="no final message.",
            payload={"index": 1},
        )
        # No final message item, no turn_completed

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-deltas-only")

        assert timeline.assistant_text == "streaming only, no final message."
        assert timeline.status == "incomplete"
    finally:
        await ledger.close()


# ── Recovery: Corrupt Payload ────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_corrupt_payload_skipped_gracefully(tmp_path):
    """ReplayRuntime must not crash when a payload_json is invalid JSON."""
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        # Insert a valid item first
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-c",
            item_type="turn_started", payload={"agent_name": "main"},
        )
        # Manually corrupt one row's payload_json in the DB
        import json
        db = ledger._conn
        await db.execute(
            """INSERT INTO runtime_ledger_items
               (item_id, session_id, thread_id, turn_id, seq, item_type,
                role, content, payload_json, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                "corrupt-item-id", "sess-1", "thread-1", "turn-c", 2,
                "tool_call_started", None, "",
                "NOT VALID JSON {{{", 1234567890.0,
            ),
        )
        await db.commit()

        replay = ReplayRuntime(ledger)
        # Must not raise — just skip the corrupt row
        timeline = await replay.get_turn_timeline("thread-1", "turn-c")
        assert timeline is not None
        assert timeline.turn_id == "turn-c"
        # The corrupt tool_call_started should be skipped
        assert len(timeline.tool_calls) == 0
    finally:
        await ledger.close()


# ── Recovery: Empty Thread ───────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_empty_thread_returns_empty(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        replay = ReplayRuntime(ledger)

        turns = await replay.list_turns("nonexistent-thread")
        assert turns == []

        timelines = await replay.get_thread_timeline("nonexistent-thread")
        assert timelines == []

        timeline = await replay.get_turn_timeline("nonexistent-thread", "any-turn")
        assert timeline is None

        messages = await replay.get_provider_messages("nonexistent-thread")
        assert messages == []
    finally:
        await ledger.close()


# ── Reasoning Deltas ─────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_captures_reasoning_deltas(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-reason",
            item_type="turn_started", payload={},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-reason",
            item_type="reasoning_delta", content="Let me think...",
            payload={},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-reason",
            item_type="reasoning_delta", content="The answer is 42.",
            payload={},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-reason",
            item_type="turn_completed", payload={},
        )

        replay = ReplayRuntime(ledger)
        timeline = await replay.get_turn_timeline("thread-1", "turn-reason")

        assert timeline.reasoning_deltas == ["Let me think...", "The answer is 42."]
    finally:
        await ledger.close()


# ── Multi-Turn Thread ────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_replay_multi_turn_thread(tmp_path):
    from miqi.runtime.ledger_runtime import LedgerRuntime
    from miqi.runtime.replay_runtime import ReplayRuntime

    ledger = LedgerRuntime(tmp_path / "runtime.db", session_id="sess-1")
    await ledger.initialize()
    try:
        # Turn 1
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-1",
            item_type="turn_started", payload={},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-1",
            item_type="message", role="user", content="q1", payload={"message_fields": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-1",
            item_type="message", role="assistant", content="a1", payload={"message_fields": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-1",
            item_type="turn_completed", payload={},
        )
        # Turn 2
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-2",
            item_type="turn_started", payload={},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-2",
            item_type="message", role="user", content="q2", payload={"message_fields": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-2",
            item_type="message", role="assistant", content="a2", payload={"message_fields": {}},
        )
        await ledger.append_item(
            thread_id="thread-1", turn_id="turn-2",
            item_type="turn_completed", payload={},
        )

        replay = ReplayRuntime(ledger)

        # list_turns
        assert await replay.list_turns("thread-1") == ["turn-1", "turn-2"]

        # get_thread_timeline
        timelines = await replay.get_thread_timeline("thread-1")
        assert len(timelines) == 2
        assert timelines[0].user_input == "q1"
        assert timelines[1].user_input == "q2"

        # get_provider_messages should include all messages across turns
        messages = await replay.get_provider_messages("thread-1")
        assert len(messages) == 4
        assert [m["content"] for m in messages] == ["q1", "a1", "q2", "a2"]
    finally:
        await ledger.close()
