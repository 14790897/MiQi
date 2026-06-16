"""Tests for TaskRunner handling RunUserShellCommand."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.protocol.commands import RunUserShellCommand
from miqi.protocol.events import TurnCompleteEvent, TurnStartedEvent
from miqi.runtime.task_runner import TaskRunner


class _FakeToolRuntime:
    def __init__(self):
        self.calls = []

    async def execute_one(self, turn, tool_call):
        self.calls.append((turn, tool_call))
        return SimpleNamespace(
            result="hello\n",
            duration_ms=12,
            tool_name="exec",
            tool_call_id=tool_call.id,
        )


def _services():
    services = MagicMock()
    services.session_id = "client-1:default"
    services.workspace = None
    services.provider = MagicMock()
    services.agent_loop = MagicMock()
    services.agent_loop.model = "test-model"
    services.agent_loop.temperature = 0.0
    services.agent_loop.max_tokens = 100
    services.tool_runtime = _FakeToolRuntime()
    services.history_runtime = None
    services.ledger_runtime = None
    return services


def _drain_queue(q: asyncio.Queue) -> list:
    events = []
    while not q.empty():
        events.append(q.get_nowait())
    return events


@pytest.mark.asyncio
async def test_run_user_shell_command_standalone_emits_turn_lifecycle():
    events_queue = asyncio.Queue()
    runner = TaskRunner(services=_services(), event_queue=events_queue)

    await runner.handle(RunUserShellCommand(
        command="echo hello",
        thread_id="thread-1",
        turn_id="turn-shell-1",
        standalone=True,
    ))

    events = _drain_queue(events_queue)
    assert any(isinstance(e, TurnStartedEvent) for e in events)
    assert any(isinstance(e, TurnCompleteEvent) for e in events)
    assert runner.services.tool_runtime.calls
    turn, call = runner.services.tool_runtime.calls[0]
    assert turn.thread_id == "thread-1"
    assert turn.turn_id == "turn-shell-1"
    assert call.name == "exec"
    assert call.arguments["command"] == "echo hello"
    assert call.arguments["_exec_source"] == "userShell"


@pytest.mark.asyncio
async def test_run_user_shell_command_active_turn_does_not_emit_turn_lifecycle():
    events_queue = asyncio.Queue()
    runner = TaskRunner(services=_services(), event_queue=events_queue)

    await runner.handle(RunUserShellCommand(
        command="echo active",
        thread_id="thread-1",
        turn_id="turn-active",
        standalone=False,
    ))

    events = _drain_queue(events_queue)
    assert not any(isinstance(e, TurnStartedEvent) for e in events)
    assert not any(isinstance(e, TurnCompleteEvent) for e in events)
    assert runner.services.tool_runtime.calls


@pytest.mark.asyncio
async def test_run_user_shell_command_empty_command_rejected():
    events_queue = asyncio.Queue()
    runner = TaskRunner(services=_services(), event_queue=events_queue)

    await runner.handle(RunUserShellCommand(
        command="   ",
        thread_id="thread-1",
        turn_id="turn-shell-1",
        standalone=True,
    ))

    events = _drain_queue(events_queue)
    assert events
    assert events[0].type == "command_rejected"
    assert events[0].command_type == "RunUserShellCommand"
