"""Tests for BridgeState runtime session cache (Phase 11.5)."""

import pytest


@pytest.mark.asyncio
async def test_bridge_state_reuses_runtime_session(monkeypatch, fake_config, fake_provider):
    """BridgeState caches and reuses RuntimeSession per session key."""
    from miqi.bridge.server import BridgeState

    state = BridgeState()
    monkeypatch.setattr(state, "load_config", lambda: fake_config)
    monkeypatch.setattr(
        "miqi.providers.factory.make_provider", lambda config: fake_provider,
    )

    first = await state.get_runtime_session("desktop:default")
    second = await state.get_runtime_session("desktop:default")

    assert first is second, "Expected same RuntimeSession for same key"
    await first.stop()


@pytest.mark.asyncio
async def test_bridge_state_creates_distinct_sessions(monkeypatch, fake_config, fake_provider):
    """Different session keys get different RuntimeSession instances."""
    from miqi.bridge.server import BridgeState

    state = BridgeState()
    monkeypatch.setattr(state, "load_config", lambda: fake_config)
    monkeypatch.setattr(
        "miqi.providers.factory.make_provider", lambda config: fake_provider,
    )

    session_a = await state.get_runtime_session("desktop:session-a")
    session_b = await state.get_runtime_session("desktop:session-b")

    assert session_a is not session_b
    await session_a.stop()
    await session_b.stop()


@pytest.mark.asyncio
async def test_bridge_state_isolates_sessions_by_caller(monkeypatch, fake_config, fake_provider):
    """Different callers with same session key get different RuntimeSessions."""
    from miqi.bridge.server import BridgeState

    state = BridgeState()
    monkeypatch.setattr(state, "load_config", lambda: fake_config)
    monkeypatch.setattr(
        "miqi.providers.factory.make_provider", lambda config: fake_provider,
    )

    session_alice = await state.get_runtime_session("desktop:default", caller_id="alice")
    session_bob = await state.get_runtime_session("desktop:default", caller_id="bob")

    assert session_alice is not session_bob, "Different callers must get isolated sessions"
    await session_alice.stop()
    await session_bob.stop()


@pytest.mark.asyncio
async def test_bridge_state_default_caller_shares_sessions(monkeypatch, fake_config, fake_provider):
    """Without explicit caller_id, sessions are shared (Phase 14 prep).

    This is backward-compatible behavior. The current chat.send production
    path does not yet use RuntimeSession, so caller isolation is not
    enforced for the active chat request flow. When Phase 14 routes
    chat.send through RuntimeSession, caller_id must be set from the
    authenticated request context.
    """
    from miqi.bridge.server import BridgeState

    state = BridgeState()
    monkeypatch.setattr(state, "load_config", lambda: fake_config)
    monkeypatch.setattr(
        "miqi.providers.factory.make_provider", lambda config: fake_provider,
    )

    # No caller_id → same key returns same session (shared, backward-compat)
    first = await state.get_runtime_session("desktop:default")
    second = await state.get_runtime_session("desktop:default")

    assert first is second, "Default (no caller_id) sessions are shared"

    # Explicit caller_id → isolation
    isolated = await state.get_runtime_session("desktop:default", caller_id="alice")
    assert isolated is not first, "Explicit caller_id must not share default session"

    await first.stop()
    await isolated.stop()
