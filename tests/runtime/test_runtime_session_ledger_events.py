"""Tests for runtime event mirroring into ledger (Phase 24.5 + hardening)."""

import pytest


@pytest.mark.asyncio
async def test_mirror_maps_turn_id_to_real_thread_id(fake_config, fake_provider, tmp_path):
    """Bug fix: events with only turn_id (e.g. ExecCommandBeginEvent)
    must be written to the real thread, not to a ledger keyed by turn_id.

    The fix maintains a turn_id → thread_id map populated by events
    that carry both fields (like TurnStartedEvent).
    """
    from miqi.protocol.events import ContextCompactedEvent, ExecCommandBeginEvent
    from miqi.runtime.session import RuntimeSession

    runtime = RuntimeSession.create(
        config=fake_config,
        provider=fake_provider,
        session_id="sess-thread-map",
        workspace=tmp_path,
    )
    await runtime.start()
    try:
        # Step 1: mirror a ContextCompactedEvent — this carries both
        # turn_id and thread_id AND is in the mirror mapping, so it
        # will be written AND establish the turn→thread mapping.
        await runtime._mirror_event_to_ledger(ContextCompactedEvent(
            turn_id="turn-abc",
            thread_id="real-thread-42",
            messages_before=10,
            messages_after=5,
            tokens_saved=200,
        ))

        # Step 2: mirror an ExecCommandBeginEvent — this has turn_id
        # but NO thread_id. It should resolve thread_id from the map.
        await runtime._mirror_event_to_ledger(ExecCommandBeginEvent(
            turn_id="turn-abc",
            tool_call_id="tc-1",
            command="echo hi",
            cwd="/tmp",
            sandbox_type="none",
        ))

        # Both items must be stored under "real-thread-42",
        # NOT under "turn-abc".
        items = await runtime.services.ledger_runtime.load_items("real-thread-42")
        item_types = [item.item_type for item in items]
        assert "context_compacted" in item_types, f"Expected context_compacted, got {item_types}"
        assert "exec_started" in item_types, (
            f"Expected exec_started under real-thread-42, got {item_types}"
        )

        # Verify NOT stored under the turn_id as thread_id.
        items_wrong = await runtime.services.ledger_runtime.load_items("turn-abc")
        assert len(items_wrong) == 0, (
            f"Expected no items under 'turn-abc', got {len(items_wrong)}"
        )
    finally:
        await runtime.stop()


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
