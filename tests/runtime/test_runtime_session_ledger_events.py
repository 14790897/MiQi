"""Tests for runtime event mirroring into ledger (Phase 24.5)."""

import pytest


@pytest.mark.asyncio
async def test_runtime_session_mirrors_command_rejected_event_to_ledger(fake_config, fake_provider, tmp_path):
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.session import RuntimeSession

    class UnknownSubmission:
        thread_id = "thread-events"

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-ledger-events",
        workspace=tmp_path,
    )
    await runtime.start()
    try:
        await runtime.submit(UnknownSubmission())
        event = await runtime.next_event(timeout=2)

        assert isinstance(event, CommandRejectedEvent)

        # CommandRejectedEvent has no thread_id, so the ledger mirrors it
        # under the fallback key "session".
        items = await runtime.services.ledger_runtime.load_items("session")
        assert any(item.item_type == "command_rejected" for item in items)
    finally:
        await runtime.stop()
