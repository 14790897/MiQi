"""Integration tests: TaskRunner persists history across turns (Phase 17)."""

import pytest

from miqi.protocol.commands import UserMessage
from miqi.protocol.events import AgentMessageEvent, TurnCompleteEvent
from miqi.runtime.session import RuntimeSession


@pytest.mark.asyncio
async def test_task_runner_persists_history_across_turns(
    fake_config, fake_provider, tmp_path,
):
    """Two consecutive UserMessages on the same thread must carry history."""
    captured_histories: list[list[dict]] = []

    async def fake_run(
        *, turn, user_content, system_prompt, tools, history=None, cancel_event=None,
    ):
        from miqi.runtime.turn_runner import TurnResult

        captured_histories.append(history or [])
        return TurnResult(
            final_content=f"reply to {user_content}",
            messages=[],
            tools_used=[],
            token_usage={"prompt_tokens": 5, "completion_tokens": 3},
            messages_delta=[
                {"role": "assistant", "content": f"reply to {user_content}"},
            ],
        )

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-history-main",
        workspace=tmp_path,
    )
    runtime.services.turn_runner.run = fake_run  # type: ignore[attr-defined]

    await runtime.start()
    try:
        # First turn — drain ALL events until timeout
        await runtime.submit(UserMessage(content="first", thread_id="thread-a"))
        events_1: list[object] = []
        # Collect events: stop after we see both AgentMessageEvent and TurnCompleteEvent
        seen_agent = False
        seen_complete = False
        while not (seen_agent and seen_complete):
            ev = await runtime.next_event(timeout=2)
            if ev is None:
                break
            events_1.append(ev)
            if isinstance(ev, AgentMessageEvent):
                seen_agent = True
            if isinstance(ev, TurnCompleteEvent):
                seen_complete = True

        # Verify first turn events
        event_names_1 = [e.__class__.__name__ for e in events_1]
        assert "TurnStartedEvent" in event_names_1, (
            f"Missing TurnStartedEvent in turn 1: {event_names_1}"
        )
        assert "TurnCompleteEvent" in event_names_1, (
            f"Missing TurnCompleteEvent in turn 1: {event_names_1}"
        )
        assert "AgentMessageEvent" in event_names_1, (
            f"Missing AgentMessageEvent in turn 1: {event_names_1}"
        )

        # Second turn — drain ALL events
        await runtime.submit(UserMessage(content="second", thread_id="thread-a"))
        events_2: list[object] = []
        seen_agent_2 = False
        seen_complete_2 = False
        while not (seen_agent_2 and seen_complete_2):
            ev = await runtime.next_event(timeout=2)
            if ev is None:
                break
            events_2.append(ev)
            if isinstance(ev, AgentMessageEvent):
                seen_agent_2 = True
            if isinstance(ev, TurnCompleteEvent):
                seen_complete_2 = True

        # First turn: history should be empty
        assert captured_histories[0] == [], (
            f"Turn 1 should have no prior history: {captured_histories[0]}"
        )
        # Second turn: history from the first turn
        assert captured_histories[1] == [
            {"role": "user", "content": "first"},
            {"role": "assistant", "content": "reply to first"},
        ], f"Turn 2 history mismatch: {captured_histories[1]}"

        # Verify persisted messages
        stored = await runtime.services.history_runtime.load_messages("thread-a")
        assert [m["content"] for m in stored] == [
            "first",
            "reply to first",
            "second",
            "reply to second",
        ], f"Stored messages: {[m['content'] for m in stored]}"
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_task_runner_persists_tool_call_messages(
    fake_config, fake_provider, tmp_path,
):
    """A turn with tool calls must persist user → assistant(tool_calls) →
    tool → assistant(final) in history."""
    from miqi.runtime.turn_runner import TurnResult

    async def fake_run_with_tools(
        *, turn, user_content, system_prompt, tools, history=None, cancel_event=None,
    ):
        return TurnResult(
            final_content="done after tools",
            messages=[],
            tools_used=["read_file"],
            token_usage={},
            messages_delta=[
                {
                    "role": "assistant",
                    "content": None,
                    "tool_calls": [{
                        "id": "tc-1",
                        "type": "function",
                        "function": {"name": "read_file", "arguments": '{"path":"/tmp/x"}'},
                    }],
                },
                {
                    "role": "tool",
                    "tool_call_id": "tc-1",
                    "content": "hello world",
                },
                {
                    "role": "assistant",
                    "content": "done after tools",
                },
            ],
        )

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-tool-history",
        workspace=tmp_path,
    )
    runtime.services.turn_runner.run = fake_run_with_tools  # type: ignore[attr-defined]

    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="read /tmp/x", thread_id="thread-tools"))

        events: list[object] = []
        seen_agent = False
        seen_complete = False
        while not (seen_agent and seen_complete):
            ev = await runtime.next_event(timeout=2)
            if ev is None:
                break
            events.append(ev)
            if isinstance(ev, AgentMessageEvent):
                seen_agent = True
            if isinstance(ev, TurnCompleteEvent):
                seen_complete = True

        assert seen_agent, "Should get final AgentMessageEvent"

        # Verify persisted history order
        stored = await runtime.services.history_runtime.load_messages("thread-tools")
        assert len(stored) == 4, (
            f"Expected 4 messages, got {len(stored)}: {[m['role'] for m in stored]}"
        )
        assert stored[0]["role"] == "user"
        assert stored[0]["content"] == "read /tmp/x"
        assert stored[1]["role"] == "assistant"
        assert "tool_calls" in stored[1], (
            "assistant message should carry tool_calls"
        )
        assert stored[2]["role"] == "tool"
        assert stored[2]["content"] == "hello world"
        assert stored[3]["role"] == "assistant"
        assert stored[3]["content"] == "done after tools"
    finally:
        await runtime.stop()


# ---------------------------------------------------------------------------
# Phase 19: auto-compact before turn
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_short_history_does_not_trigger_compact(
    fake_config, fake_provider, tmp_path,
):
    """When history is short, should_auto_compact returns False and no
    ContextCompactedEvent is emitted."""
    from miqi.protocol.events import ContextCompactedEvent, TurnCompleteEvent

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-no-compact",
        workspace=tmp_path,
    )

    # Make should_auto_compact always return False
    runtime.services.context_runtime.should_auto_compact = lambda msgs, lim: False

    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="hello", thread_id="thread-x"))

        events: list[object] = []
        seen_complete = False
        while not seen_complete:
            ev = await runtime.next_event(timeout=2)
            if ev is None:
                break
            events.append(ev)
            if isinstance(ev, TurnCompleteEvent):
                seen_complete = True

        # No ContextCompactedEvent should appear
        compact_events = [e for e in events if isinstance(e, ContextCompactedEvent)]
        assert len(compact_events) == 0, (
            f"Should not compact short history: {compact_events}"
        )
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_task_runner_auto_compacts_before_large_turn(
    fake_config, fake_provider, tmp_path,
):
    """When should_auto_compact returns True, the turn emits ContextCompactedEvent
    before AgentMessageEvent."""
    from unittest.mock import AsyncMock

    from miqi.protocol.events import ContextCompactedEvent, TurnCompleteEvent
    from miqi.runtime.context_runtime import CompactionResult

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-auto-compact",
        workspace=tmp_path,
    )

    # Override auto-compact trigger
    runtime.services.context_runtime.should_auto_compact = lambda msgs, lim: True
    runtime.services.context_runtime.compact_thread = AsyncMock(return_value=CompactionResult(
        thread_id="thread-auto",
        messages_before=100,
        messages_after=10,
        tokens_saved=1000,
        replacement_messages=[],
    ))

    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="hello", thread_id="thread-auto"))

        events: list[object] = []
        seen_complete = False
        while not seen_complete:
            ev = await runtime.next_event(timeout=2)
            if ev is None:
                break
            events.append(ev)
            if isinstance(ev, TurnCompleteEvent):
                seen_complete = True

        event_names = [e.__class__.__name__ for e in events]
        assert "ContextCompactedEvent" in event_names, (
            f"Expected ContextCompactedEvent in: {event_names}"
        )
        # ContextCompactedEvent must come before AgentMessageEvent
        compact_idx = event_names.index("ContextCompactedEvent")
        agent_idx = next(
            i for i, n in enumerate(event_names) if n == "AgentMessageEvent"
        )
        assert compact_idx < agent_idx, (
            f"ContextCompactedEvent ({compact_idx}) must precede "
            f"AgentMessageEvent ({agent_idx})"
        )
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_compaction_failure_does_not_crash_runtime(
    fake_config, fake_provider, tmp_path,
):
    """When compact_thread raises, the turn proceeds with unbounded history
    and the runtime does not crash."""
    from unittest.mock import AsyncMock

    from miqi.protocol.events import AgentMessageEvent, TurnCompleteEvent

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-compact-fail",
        workspace=tmp_path,
    )

    # should_auto_compact → True, but compact_thread → crash
    runtime.services.context_runtime.should_auto_compact = lambda msgs, lim: True
    runtime.services.context_runtime.compact_thread = AsyncMock(
        side_effect=RuntimeError("compaction exploded"),
    )

    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="hello", thread_id="thread-fail"))

        events: list[object] = []
        seen_complete = False
        while not seen_complete:
            ev = await runtime.next_event(timeout=2)
            if ev is None:
                break
            events.append(ev)
            if isinstance(ev, TurnCompleteEvent):
                seen_complete = True

        event_names = [e.__class__.__name__ for e in events]
        # Turn should still complete successfully (graceful degradation)
        assert "AgentMessageEvent" in event_names, (
            f"Turn should produce agent message despite compaction failure: {event_names}"
        )
        assert "TurnCompleteEvent" in event_names, (
            f"Turn should complete despite compaction failure: {event_names}"
        )
        # Compaction failure must NOT emit ContextCompactedEvent
        assert "ContextCompactedEvent" not in event_names, (
            f"Failed compaction should not emit compact event: {event_names}"
        )
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_compaction_record_persisted_and_reused(
    fake_config, fake_provider, tmp_path,
):
    """After compaction, replacement messages are persisted and reused
    in the next turn's history. Uses TaskRunner directly for precise control."""
    import asyncio as _asyncio
    from unittest.mock import AsyncMock, MagicMock

    from miqi.runtime.context_runtime import CompactionResult
    from miqi.runtime.history_runtime import HistoryRuntime
    from miqi.runtime.task_runner import TaskRunner

    # Build a real HistoryRuntime
    db_path = tmp_path / ".miqi-runtime" / "runtime.db"
    hist = HistoryRuntime(db_path, session_id="sess-cp")
    await hist.initialize()
    for i in range(10):
        await hist.append_message(
            thread_id="thread-cp", turn_id="pre", role="user",
            content=f"message {i}",
        )

    # Build services with real history_runtime + real context_runtime
    from miqi.runtime.context_runtime import ContextRuntime
    from miqi.runtime.services import RuntimeEventEmitter

    services = MagicMock()
    services.session_id = "sess-cp"
    services.workspace = tmp_path
    services.provider = fake_provider
    services.event_emitter = RuntimeEventEmitter()
    services.agent_loop = MagicMock()
    services.agent_loop.model = "test-model"
    services.agent_loop.temperature = 0.1
    services.agent_loop.max_tokens = 4096
    services.agent_loop.context_limit_chars = 600000
    services.agent_loop.stop = MagicMock()
    services.tool_registry = MagicMock()
    services.tool_registry.get_definitions.return_value = []
    services.orchestrator = MagicMock()
    services.agent_registry = MagicMock()
    services.agent_control = MagicMock()
    services.tool_runtime = MagicMock()
    services.turn_runner = MagicMock()
    services.turn_runner.run = AsyncMock()
    run_result = MagicMock()
    run_result.final_content = "hi"
    run_result.messages_delta = [{"role": "assistant", "content": "hi"}]
    run_result.tools_used = []
    run_result.token_usage = {}
    services.turn_runner.run.return_value = run_result
    services.capability_resolver = None
    services.history_runtime = hist
    services.session_state = None
    services.thread_runtime = None

    # Real ContextRuntime but override compress with async function
    ctx = ContextRuntime()
    async def fake_compress(messages, model, session_id=""):
        return [
            {"role": "system", "content": "[compacted summary]"},
            {"role": "user", "content": "most recent message"},
        ]
    ctx.compress_messages = fake_compress
    ctx.should_auto_compact = lambda messages, token_limit: True
    services.context_runtime = ctx

    events = _asyncio.Queue()
    runner = TaskRunner(services=services, event_queue=events)

    await runner.handle(UserMessage(content="final", thread_id="thread-cp"))

    # Drain events
    event_list: list[object] = []
    while True:
        try:
            ev = await _asyncio.wait_for(events.get(), timeout=0.5)
            event_list.append(ev)
        except _asyncio.TimeoutError:
            break

    event_names = [e.__class__.__name__ for e in event_list]
    assert "ContextCompactedEvent" in event_names, (
        f"Expected ContextCompactedEvent in: {event_names}"
    )

    # Verify persisted history now has compacted messages + new turn
    stored = await hist.load_messages("thread-cp")
    assert len(stored) >= 3, (
        f"Expected at least summary + recent + final, got: "
        f"{[m['role'] for m in stored]}"
    )
    # First message should be the summary
    assert stored[0]["role"] == "system"
    assert "[compacted summary]" in stored[0]["content"]
