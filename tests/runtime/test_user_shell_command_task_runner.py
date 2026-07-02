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
        from miqi.execution.orchestrator import OrchestrationResult
        return SimpleNamespace(
            result="hello\n",
            duration_ms=12,
            tool_name="exec",
            tool_call_id=tool_call.id,
            status=OrchestrationResult.SUCCESS,
        )


def _services():
    services = MagicMock()
    services.session_id = "client-1:default"
    services.workspace = None
    services.provider = MagicMock()
    from miqi.runtime.services import RuntimeModelSettings
    services.model_settings = RuntimeModelSettings(
        model="test-model",
        temperature=0.0,
        max_tokens=100,
        max_tool_result_chars=12000,
        context_limit_chars=600000,
    )
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


@pytest.mark.asyncio
async def test_standalone_shell_command_writes_ledger_lifecycle():
    """Phase 42 fix: standalone shell command must write turn_started and
    turn_completed to the ledger for replay/debug integrity."""
    events_queue = asyncio.Queue()
    services = _services()
    ledger = MagicMock()
    ledger.append_item = AsyncMock()
    services.ledger_runtime = ledger

    runner = TaskRunner(services=services, event_queue=events_queue)

    await runner.handle(RunUserShellCommand(
        command="echo hello",
        thread_id="thread-1",
        turn_id="turn-shell-1",
        standalone=True,
    ))

    calls = [c.kwargs for c in ledger.append_item.call_args_list]
    item_types = [c["item_type"] for c in calls]
    assert "turn_started" in item_types
    assert "turn_completed" in item_types
    # Verify turn_started comes before turn_completed
    ts_idx = item_types.index("turn_started")
    tc_idx = item_types.index("turn_completed")
    assert ts_idx < tc_idx
    # Verify the completion has the right outcome
    tc_call = calls[tc_idx]
    assert tc_call["thread_id"] == "thread-1"
    assert tc_call["turn_id"] == "turn-shell-1"
    assert tc_call["payload"]["tools_used"] == ["exec"]


@pytest.mark.asyncio
async def test_standalone_shell_command_writes_ledger_on_error():
    """Phase 42 fix: standalone shell command with no tool runtime must write
    a terminal ledger item."""
    events_queue = asyncio.Queue()
    services = _services()
    services.tool_runtime = None  # trigger error path
    ledger = MagicMock()
    ledger.append_item = AsyncMock()
    services.ledger_runtime = ledger

    runner = TaskRunner(services=services, event_queue=events_queue)

    await runner.handle(RunUserShellCommand(
        command="echo hello",
        thread_id="thread-1",
        turn_id="turn-shell-1",
        standalone=True,
    ))

    calls = [c.kwargs for c in ledger.append_item.call_args_list]
    item_types = [c["item_type"] for c in calls]
    # Must have turn_started + error (terminal) — not left incomplete
    assert "turn_started" in item_types
    assert "error" in item_types


@pytest.mark.asyncio
async def test_active_turn_shell_command_receives_cancel_event():
    """Phase 42 fix: active-turn shell command TurnContext must receive
    the thread's cancel_event so AbortTurn can cancel a running exec."""
    events_queue = asyncio.Queue()
    services = _services()

    # Simulate what _handle_user_message does: create a cancel_event for the thread
    cancel_evt = asyncio.Event()
    runner = TaskRunner(services=services, event_queue=events_queue)
    runner._turn_cancel_events["thread-1"] = cancel_evt

    await runner.handle(RunUserShellCommand(
        command="echo hello",
        thread_id="thread-1",
        turn_id="turn-active",
        standalone=False,
    ))

    # The TurnContext passed to execute_one should carry the cancel_event
    turn, _ = services.tool_runtime.calls[0]
    assert getattr(turn, "cancel_event", None) is cancel_evt


@pytest.mark.asyncio
async def test_active_turn_shell_command_without_cancel_event_is_graceful():
    """No cancel_event on the thread → TurnContext.cancel_event stays None. No crash."""
    events_queue = asyncio.Queue()
    services = _services()

    runner = TaskRunner(services=services, event_queue=events_queue)
    # No _turn_cancel_events entry for this thread

    await runner.handle(RunUserShellCommand(
        command="echo hello",
        thread_id="thread-2",
        turn_id="turn-active-2",
        standalone=False,
    ))

    turn, _ = services.tool_runtime.calls[0]
    # Should not blow up — cancel_event is just None
    assert getattr(turn, "cancel_event", None) is None
