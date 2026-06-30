"""Tests for Codex-style thread/shellCommand handler."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.protocol.commands import RunUserShellCommand
from miqi.protocol.events import TurnCompleteEvent
from miqi.runtime.app_server import AppServer, ClientSessionRegistry


class _FakeRuntime:
    def __init__(self, session_id: str):
        self.session_id = session_id
        self.submissions = []
        self.services = MagicMock()
        self.services.thread_runtime = MagicMock()
        self.services.thread_runtime.get_thread = AsyncMock(return_value=MagicMock(thread_id="thread-1"))
        self._reservations: dict[str, str] = {}
        self._events: asyncio.Queue = asyncio.Queue()
        self.active_turn_id = MagicMock(return_value=None)
        self.submit = AsyncMock(side_effect=self._submit)

    async def _submit(self, submission):
        self.submissions.append(submission)

    async def try_reserve_turn(self, thread_id: str, turn_id: str) -> bool:
        if thread_id in self._reservations:
            return False
        self._reservations[thread_id] = turn_id
        return True

    async def release_turn_reservation(self, thread_id: str) -> None:
        self._reservations.pop(thread_id, None)

    async def next_event(self, timeout=None):
        return await self._events.get()

    def feed_event(self, event):
        self._events.put_nowait(event)


def _register_runtime(registry, runtime):
    registry._sessions[runtime.session_id] = runtime
    registry._client_sessions.setdefault("client-1", set()).add(runtime.session_id)
    registry._session_clients.setdefault(runtime.session_id, set()).add("client-1")
    registry._last_activity[runtime.session_id] = 0


@pytest.mark.asyncio
async def test_thread_shell_command_rejects_missing_command():
    from miqi.runtime.shell_command_app_handlers import register_shell_command_handlers

    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    _register_runtime(registry, runtime)
    server = AppServer(registry)
    register_shell_command_handlers(server)

    response = await server.dispatch(
        "req-1",
        "thread/shellCommand",
        {"threadId": "thread-1", "command": "   "},
        "client-1",
        runtime.session_id,
    )

    assert response["code"] == "INVALID_PARAMS"
    assert runtime.submissions == []
    await server.stop()


@pytest.mark.asyncio
async def test_thread_shell_command_rejects_unknown_thread():
    from miqi.runtime.shell_command_app_handlers import register_shell_command_handlers

    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    runtime.services.thread_runtime.get_thread = AsyncMock(return_value=None)
    _register_runtime(registry, runtime)
    server = AppServer(registry)
    register_shell_command_handlers(server)

    response = await server.dispatch(
        "req-1",
        "thread/shellCommand",
        {"threadId": "missing", "command": "echo hi"},
        "client-1",
        runtime.session_id,
    )

    assert response["code"] == "NOT_FOUND"
    assert runtime.submissions == []
    await server.stop()


@pytest.mark.asyncio
async def test_thread_shell_command_active_turn_submits_auxiliary_command():
    from miqi.runtime.shell_command_app_handlers import register_shell_command_handlers

    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    runtime.active_turn_id = MagicMock(return_value="turn-active")
    _register_runtime(registry, runtime)
    server = AppServer(registry)
    register_shell_command_handlers(server)

    response = await server.dispatch(
        "req-1",
        "thread/shellCommand",
        {"threadId": "thread-1", "command": "echo active"},
        "client-1",
        runtime.session_id,
    )

    assert response["result"] == {}
    assert len(runtime.submissions) == 1
    submission = runtime.submissions[0]
    assert isinstance(submission, RunUserShellCommand)
    assert submission.turn_id == "turn-active"
    assert submission.standalone is False
    assert not server._background_tasks
    await server.stop()


@pytest.mark.asyncio
async def test_thread_shell_command_idle_thread_starts_standalone_turn():
    from miqi.runtime.shell_command_app_handlers import register_shell_command_handlers

    registry = ClientSessionRegistry()
    runtime = _FakeRuntime("client-1:default")
    _register_runtime(registry, runtime)
    server = AppServer(registry)
    register_shell_command_handlers(server)

    response = await server.dispatch(
        "req-1",
        "thread/shellCommand",
        {"threadId": "thread-1", "command": "echo standalone"},
        "client-1",
        runtime.session_id,
    )

    assert response["result"] == {}
    assert len(runtime.submissions) == 1
    submission = runtime.submissions[0]
    assert isinstance(submission, RunUserShellCommand)
    assert submission.standalone is True
    assert submission.turn_id
    assert len(server._background_tasks) == 1

    runtime.feed_event(TurnCompleteEvent(
        turn_id=submission.turn_id,
        thread_id="thread-1",
        outcome="success",
    ))
    for _ in range(100):
        if not server._background_tasks:
            break
        await asyncio.sleep(0.01)
    assert not server._background_tasks
    assert "thread-1" not in runtime._reservations
    await server.stop()
