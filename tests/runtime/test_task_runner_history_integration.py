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
