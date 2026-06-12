"""Tests for ledger mirroring of user turns (Phase 24.3 + hardening)."""

import pytest

from miqi.protocol.commands import UserMessage


@pytest.mark.asyncio
async def test_history_passed_when_ledger_is_none(fake_config, fake_provider, tmp_path):
    """Bug fix: when ledger_runtime is None but history_runtime exists,
    TurnRunner must still receive loaded history — not [] forced by
    the else branch of the wrong if-block."""
    from miqi.protocol.events import TurnCompleteEvent
    from miqi.runtime.session import RuntimeSession

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-history-fallback",
        workspace=tmp_path,
    )
    await runtime.start()
    try:
        # Pre-populate history_runtime with a prior user message so
        # there is real history to load.
        hist = runtime.services.history_runtime
        await hist.start_turn("pre-turn", thread_id="thread-fallback")
        await hist.append_message(
            thread_id="thread-fallback",
            turn_id="pre-turn",
            role="user",
            content="prior message",
        )
        await hist.complete_turn(
            "pre-turn", status="completed", tools_used=[], token_usage={},
        )

        # Disable ledger — this is the scenario under test.
        runtime.services.ledger_runtime = None

        # Spy on turn_runner.run to capture the `history` kwarg.
        original_run = runtime.services.turn_runner.run
        captured_history: list = []

        async def spy_run(turn, user_content, system_prompt, tools, history, cancel_event):
            captured_history.append(history)
            return await original_run(
                turn=turn,
                user_content=user_content,
                system_prompt=system_prompt,
                tools=tools,
                history=history,
                cancel_event=cancel_event,
            )

        runtime.services.turn_runner.run = spy_run

        await runtime.submit(UserMessage(content="hello", thread_id="thread-fallback"))

        while True:
            event = await runtime.next_event(timeout=2)
            if isinstance(event, TurnCompleteEvent):
                break

        # The bug: when ledger is None, the else-branch incorrectly set
        # history=[], discarding the loaded messages. After the fix,
        # history must contain the pre-populated "prior message".
        assert len(captured_history) == 1, "Expected spy to capture history"
        history_messages = captured_history[0]
        assert len(history_messages) > 0, (
            f"Expected non-empty history when history_runtime exists, "
            f"got {history_messages}"
        )
        assert any(
            m.get("content") == "prior message" for m in history_messages
        ), f"Expected 'prior message' in history, got {history_messages}"
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_task_runner_writes_turn_and_messages_to_ledger(fake_config, fake_provider, tmp_path):
    from miqi.protocol.events import TurnCompleteEvent
    from miqi.runtime.session import RuntimeSession

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-ledger-turn",
        workspace=tmp_path,
    )
    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="hello", thread_id="thread-ledger"))

        while True:
            event = await runtime.next_event(timeout=2)
            if isinstance(event, TurnCompleteEvent):
                break

        items = await runtime.services.ledger_runtime.load_items("thread-ledger")
        item_types = [item.item_type for item in items]

        assert "turn_started" in item_types
        assert "turn_completed" in item_types
        assert any(item.item_type == "message" and item.role == "user" and item.content == "hello" for item in items)
        assert any(item.item_type == "message" and item.role == "assistant" for item in items)
    finally:
        await runtime.stop()


@pytest.mark.asyncio
async def test_ledger_provider_messages_match_history_messages(fake_config, fake_provider, tmp_path):
    from miqi.protocol.commands import UserMessage
    from miqi.protocol.events import TurnCompleteEvent
    from miqi.runtime.session import RuntimeSession

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-ledger-compare",
        workspace=tmp_path,
    )
    await runtime.start()
    try:
        await runtime.submit(UserMessage(content="hello", thread_id="thread-compare"))
        while True:
            event = await runtime.next_event(timeout=2)
            if isinstance(event, TurnCompleteEvent):
                break

        history_messages = await runtime.services.history_runtime.load_messages("thread-compare")
        ledger_messages = await runtime.services.ledger_runtime.load_provider_messages("thread-compare")

        assert ledger_messages == history_messages
    finally:
        await runtime.stop()
