"""Tests for Phase 31.2: ExecTool consumes SandboxSelection from ToolOrchestrator.

These tests verify that ExecTool no longer makes independent sandbox decisions
and instead follows the SandboxSelection injected by ToolOrchestrator.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.agent.tools.shell import ExecTool
from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
from miqi.protocol.events import ExecCommandBeginEvent, ExecCommandEndEvent
from miqi.protocol.permissions import (
    FileSystemAccessMode,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
)


# ── helpers ────────────────────────────────────────────────────────────

def _make_selection(
    sandbox_type: SandboxType = SandboxType.NONE,
    *,
    timeout_ms: int = 30_000,
    env_passthrough: list[str] | None = None,
) -> SandboxSelection:
    """Create a SandboxSelection for testing."""
    return SandboxSelection(
        sandbox_type=sandbox_type,
        filesystem_policy=FileSystemSandboxPolicy(
            default_mode=FileSystemAccessMode.READ,
        ),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        env_passthrough=env_passthrough or [],
        timeout_ms=timeout_ms,
        reason=f"Test selection: {sandbox_type.value}",
    )


def _make_mock_sandbox(*, is_running: bool = True, run_result=None):
    """Create a mock BwrapSandbox."""
    sandbox = MagicMock()
    sandbox.is_running = is_running
    sandbox.get_sandbox_env = MagicMock(return_value={})
    if run_result is None:
        run_result = (0, "hello from sandbox", "")
    sandbox.run_command = AsyncMock(return_value=run_result)
    return sandbox


def _make_mock_sandbox_manager(*, active_sandbox=None):
    """Create a mock SandboxManager."""
    mgr = MagicMock()
    mgr.active_sandbox = active_sandbox
    return mgr


class _EventCollector:
    """Collects emitted events for assertion."""

    def __init__(self):
        self.events: list = []

    async def emit(self, event):
        self.events.append(event)


# ── 31.2: SandboxSelection consumption ─────────────────────────────────

@pytest.mark.asyncio
async def test_sandbox_selection_none_allows_direct_execution():
    """When _sandbox is NONE, the orchestrator explicitly allows direct execution."""
    tool = ExecTool(timeout=5)
    sel = _make_selection(SandboxType.NONE)

    result = await tool.execute(
        "python -c \"print('direct-ok')\"",
        _sandbox=sel,
    )

    assert "direct-ok" in result


@pytest.mark.asyncio
async def test_sandbox_selection_bwrap_with_active_sandbox():
    """When _sandbox is BWRAP and sandbox is active, use sandbox execution."""
    mock_sandbox = _make_mock_sandbox(is_running=True)
    mock_mgr = _make_mock_sandbox_manager(active_sandbox=mock_sandbox)

    tool = ExecTool(timeout=5, sandbox_manager=mock_mgr)
    sel = _make_selection(SandboxType.BWRAP)

    result = await tool.execute(
        "echo hello",
        _sandbox=sel,
    )

    assert "hello from sandbox" in result
    mock_sandbox.run_command.assert_called_once()


@pytest.mark.asyncio
async def test_sandbox_selection_bwrap_unavailable_no_manager_fails_closed():
    """BWRAP selected but no sandbox_manager → fail closed, NO direct execution."""
    tool = ExecTool(timeout=5, sandbox_manager=None)
    sel = _make_selection(SandboxType.BWRAP)

    result = await tool.execute(
        "echo should-not-run",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "BWRAP sandbox" in result


@pytest.mark.asyncio
async def test_sandbox_selection_bwrap_no_active_sandbox_fails_closed():
    """BWRAP selected, sandbox_manager exists but no active sandbox → fail closed."""
    mock_mgr = _make_mock_sandbox_manager(active_sandbox=None)

    tool = ExecTool(timeout=5, sandbox_manager=mock_mgr)
    sel = _make_selection(SandboxType.BWRAP)

    result = await tool.execute(
        "echo should-not-run",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "BWRAP sandbox" in result


@pytest.mark.asyncio
async def test_sandbox_selection_bwrap_sandbox_not_running_fails_closed():
    """BWRAP selected, sandbox exists but is_running=False → fail closed."""
    mock_sandbox = _make_mock_sandbox(is_running=False)
    mock_mgr = _make_mock_sandbox_manager(active_sandbox=mock_sandbox)

    tool = ExecTool(timeout=5, sandbox_manager=mock_mgr)
    sel = _make_selection(SandboxType.BWRAP)

    result = await tool.execute(
        "echo should-not-run",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "BWRAP sandbox" in result


@pytest.mark.asyncio
async def test_sandbox_selection_landlock_unsupported():
    """LANDLOCK is not implemented → fail closed with clear message."""
    tool = ExecTool(timeout=5)
    sel = _make_selection(SandboxType.LANDLOCK)

    result = await tool.execute(
        "echo should-not-run",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "LANDLOCK" in result


@pytest.mark.asyncio
async def test_sandbox_selection_restricted_allows_direct():
    """RESTRICTED sandbox type allows direct execution with enforcement."""
    tool = ExecTool(timeout=5)
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "python -c \"print('restricted-ok')\"",
        _sandbox=sel,
    )

    assert "restricted-ok" in result


# ── 31.2: Legacy path (no SandboxSelection) ────────────────────────────

@pytest.mark.asyncio
async def test_legacy_path_direct_execution():
    """Without _sandbox and without sandbox_manager → legacy direct execution."""
    tool = ExecTool(timeout=5)

    result = await tool.execute("python -c \"print('legacy')\"")

    assert "legacy" in result


@pytest.mark.asyncio
async def test_legacy_path_with_sandbox_manager():
    """Without _sandbox but with sandbox_manager and active sandbox → legacy sandbox path."""
    mock_sandbox = _make_mock_sandbox(is_running=True)
    mock_mgr = _make_mock_sandbox_manager(active_sandbox=mock_sandbox)

    tool = ExecTool(timeout=5, sandbox_manager=mock_mgr)

    result = await tool.execute("echo hello")

    assert "hello from sandbox" in result
    mock_sandbox.run_command.assert_called_once()


# ── 31.2: Event correctness ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_begin_event_sandbox_type_from_selection():
    """Begin event sandbox_type must come from SandboxSelection, not sandbox_manager."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, sandbox_manager=None)  # no sandbox_manager
    sel = _make_selection(SandboxType.BWRAP)  # but selection says BWRAP

    await tool.execute(
        "python -c \"print('ok')\"",
        _event_emitter=emitter,
        _turn_id="t1",
        _tool_call_id="c1",
        _sandbox=sel,
    )

    begin = [e for e in emitter.events if isinstance(e, ExecCommandBeginEvent)]
    assert len(begin) == 1
    # Must use the SandboxSelection type, NOT "none" from missing sandbox_manager
    assert begin[0].sandbox_type == "bwrap"


@pytest.mark.asyncio
async def test_begin_event_sandbox_type_none_selection():
    """Begin event reflects NONE when SandboxSelection type is NONE."""
    emitter = _EventCollector()
    mock_sandbox = _make_mock_sandbox(is_running=True)
    mock_mgr = _make_mock_sandbox_manager(active_sandbox=mock_sandbox)
    tool = ExecTool(timeout=5, sandbox_manager=mock_mgr)

    sel = _make_selection(SandboxType.NONE)

    await tool.execute(
        "python -c \"print('ok')\"",
        _event_emitter=emitter,
        _turn_id="t1",
        _tool_call_id="c1",
        _sandbox=sel,
    )

    begin = [e for e in emitter.events if isinstance(e, ExecCommandBeginEvent)]
    assert len(begin) == 1
    assert begin[0].sandbox_type == "none"


@pytest.mark.asyncio
async def test_legacy_begin_event_no_selection():
    """Without _sandbox, begin event uses legacy sandbox_type logic."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, sandbox_manager=None)

    await tool.execute(
        "python -c \"print('ok')\"",
        _event_emitter=emitter,
        _turn_id="t1",
        _tool_call_id="c1",
    )

    begin = [e for e in emitter.events if isinstance(e, ExecCommandBeginEvent)]
    assert len(begin) == 1
    assert begin[0].sandbox_type == "none"


# ── 31.2: Existing event tests compatibility ───────────────────────────

@pytest.mark.asyncio
async def test_exec_tool_emits_begin_and_end_no_sandbox_selection(tmp_path):
    """Existing behavior: ExecTool emits begin+end events without _sandbox."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"print('hello')\"",
        _event_emitter=emitter,
        _turn_id="turn-1",
        _tool_call_id="tc-1",
    )

    assert "hello" in output

    begin_events = [e for e in emitter.events if isinstance(e, ExecCommandBeginEvent)]
    end_events = [e for e in emitter.events if isinstance(e, ExecCommandEndEvent)]

    assert len(begin_events) == 1
    assert len(end_events) == 1
    assert begin_events[0].turn_id == "turn-1"
    assert end_events[0].turn_id == "turn-1"
    assert end_events[0].output_size > 0


@pytest.mark.asyncio
async def test_exec_tool_emits_begin_and_end_with_sandbox_selection(tmp_path):
    """With _sandbox=NONE, ExecTool still emits begin+end events."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.NONE)

    output = await tool.execute(
        "python -c \"print('hello-selection')\"",
        _event_emitter=emitter,
        _turn_id="turn-2",
        _tool_call_id="tc-2",
        _sandbox=sel,
    )

    assert "hello-selection" in output

    begin_events = [e for e in emitter.events if isinstance(e, ExecCommandBeginEvent)]
    end_events = [e for e in emitter.events if isinstance(e, ExecCommandEndEvent)]

    assert len(begin_events) == 1
    assert len(end_events) == 1
    assert begin_events[0].turn_id == "turn-2"
    assert begin_events[0].sandbox_type == "none"
    assert end_events[0].turn_id == "turn-2"
    assert end_events[0].output_size > 0
