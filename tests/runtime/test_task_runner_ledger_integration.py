"""Tests for ledger mirroring of user turns (Phase 24.3)."""

import pytest

from miqi.protocol.commands import UserMessage


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
