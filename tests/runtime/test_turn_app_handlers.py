"""Tests for Codex-style turn AppServer handlers."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry


class _FakeRuntime:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.submissions = []
        self.events = AsyncMock()
        self.services = MagicMock()
        self.services.thread_runtime = MagicMock()
        self.services.thread_runtime.get_thread = AsyncMock(return_value=MagicMock(thread_id="thread-1"))
        self.submit = AsyncMock(side_effect=self._submit)
        self.next_event = AsyncMock()
        self.active_turn_id = MagicMock(return_value="turn-1")
        self.interrupt_turn = AsyncMock(return_value=True)
        self.steer_turn = AsyncMock(return_value=True)

    async def _submit(self, submission):
        self.submissions.append(submission)


def _register_runtime(registry, runtime):
    registry._sessions[runtime.session_id] = runtime
    registry._client_sessions.setdefault("client-1", set()).add(runtime.session_id)
    registry._session_clients.setdefault(runtime.session_id, set()).add("client-1")
    registry._last_activity[runtime.session_id] = 0


# ── turn/start ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_turn_start_returns_initial_turn_and_submits_user_message():
    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    _register_runtime(registry, runtime)

    from miqi.runtime.turn_app_handlers import register_codex_turn_handlers
    server = AppServer(registry)
    register_codex_turn_handlers(server)

    response = await server.dispatch(
        "req-1",
        "turn/start",
        {
            "threadId": "thread-1",
            "clientUserMessageId": "client-msg-1",
            "input": [{"type": "text", "text": "hello"}],
        },
        "client-1",
        runtime.session_id,
    )

    assert "result" in response, response
    turn = response["result"]["turn"]
    assert turn["threadId"] == "thread-1"
    assert turn["status"] == "inProgress"
    assert turn["items"] == []
    assert turn["error"] is None

    submission = runtime.submissions[0]
    assert submission.thread_id == "thread-1"
    assert submission.content == "hello"
    assert submission.input_items == [{"type": "text", "text": "hello"}]
    assert submission.client_user_message_id == "client-msg-1"
    assert submission.turn_id == turn["id"]

    await server.stop()


@pytest.mark.asyncio
async def test_turn_start_rejects_missing_input():
    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    _register_runtime(registry, runtime)

    from miqi.runtime.turn_app_handlers import register_codex_turn_handlers
    server = AppServer(registry)
    register_codex_turn_handlers(server)

    response = await server.dispatch(
        "req-1",
        "turn/start",
        {"threadId": "thread-1", "input": []},
        "client-1",
        runtime.session_id,
    )

    assert response["code"] == "INVALID_PARAMS"
    await server.stop()


# ── turn/interrupt ───────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_turn_interrupt_delegates_to_runtime_interrupt_turn():
    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    _register_runtime(registry, runtime)

    from miqi.runtime.turn_app_handlers import register_codex_turn_handlers
    server = AppServer(registry)
    register_codex_turn_handlers(server)

    response = await server.dispatch(
        "req-1",
        "turn/interrupt",
        {"threadId": "thread-1", "turnId": "turn-1"},
        "client-1",
        runtime.session_id,
    )

    assert response["result"] == {}
    runtime.interrupt_turn.assert_awaited_once_with(thread_id="thread-1", turn_id="turn-1")
    await server.stop()


@pytest.mark.asyncio
async def test_turn_interrupt_rejects_turn_mismatch():
    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    runtime.interrupt_turn = AsyncMock(return_value=False)
    _register_runtime(registry, runtime)

    from miqi.runtime.turn_app_handlers import register_codex_turn_handlers
    server = AppServer(registry)
    register_codex_turn_handlers(server)

    response = await server.dispatch(
        "req-1",
        "turn/interrupt",
        {"threadId": "thread-1", "turnId": "wrong"},
        "client-1",
        runtime.session_id,
    )

    assert response["code"] == "INVALID_REQUEST"
    await server.stop()


# ── turn/steer ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_turn_steer_delegates_to_runtime_steer_turn():
    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    _register_runtime(registry, runtime)

    from miqi.runtime.turn_app_handlers import register_codex_turn_handlers
    server = AppServer(registry)
    register_codex_turn_handlers(server)

    response = await server.dispatch(
        "req-1",
        "turn/steer",
        {
            "threadId": "thread-1",
            "expectedTurnId": "turn-1",
            "clientUserMessageId": "client-msg-2",
            "input": [{"type": "text", "text": "steer"}],
        },
        "client-1",
        runtime.session_id,
    )

    assert response["result"] == {"turnId": "turn-1"}
    runtime.steer_turn.assert_awaited_once()
    args = runtime.steer_turn.await_args.kwargs
    assert args["thread_id"] == "thread-1"
    assert args["expected_turn_id"] == "turn-1"
    assert args["content"] == "steer"
    assert args["client_user_message_id"] == "client-msg-2"
    await server.stop()
