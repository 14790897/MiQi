"""Tests for exec lifecycle events (Phases 21, 31.5, 31.6)."""

import asyncio

import pytest

from miqi.agent.tools.shell import ExecTool
from miqi.protocol.events import (
    ExecCommandBeginEvent,
    ExecCommandOutputDeltaEvent,
    ExecCommandEndEvent,
)


class _EventCollector:
    """Collects emitted events for assertion."""

    def __init__(self):
        self.events: list = []

    async def emit(self, event):
        self.events.append(event)


# ── Phase 21: basic begin / end events ──────────────────────────────────


@pytest.mark.asyncio
async def test_exec_tool_emits_begin_and_end(tmp_path):
    """ExecTool must emit ExecCommandBeginEvent before execution and
    ExecCommandEndEvent after execution when _event_emitter is passed."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"print('hello')\"",
        _event_emitter=emitter,
        _turn_id="turn-1",
        _tool_call_id="tc-1",
    )

    assert "hello" in output, f"Expected 'hello' in output: {output!r}"

    begin_events = [e for e in emitter.events if isinstance(e, ExecCommandBeginEvent)]
    end_events = [e for e in emitter.events if isinstance(e, ExecCommandEndEvent)]

    assert len(begin_events) == 1, f"Should emit 1 begin event: {emitter.events}"
    assert len(end_events) == 1, f"Should emit 1 end event: {emitter.events}"

    assert begin_events[0].turn_id == "turn-1"
    assert begin_events[0].tool_call_id == "tc-1"
    assert "python" in begin_events[0].command

    assert end_events[0].turn_id == "turn-1"
    assert end_events[0].tool_call_id == "tc-1"
    assert end_events[0].output_size > 0


# ── Phase 31.5: stdout/stderr streaming ─────────────────────────────────

@pytest.mark.asyncio
async def test_stdout_streaming_emits_delta_events(tmp_path):
    """Phase 31.5: stdout chunks must emit ExecCommandOutputDeltaEvent
    with stream='stdout' BEFORE ExecCommandEndEvent."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"import sys; sys.stdout.write('hello'); sys.stdout.flush()\"",
        _event_emitter=emitter,
        _turn_id="t-stream-out",
        _tool_call_id="tc-stream-out",
    )

    assert "hello" in output

    delta_events = [e for e in emitter.events
                    if isinstance(e, ExecCommandOutputDeltaEvent)]
    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]

    # Must have at least one stdout delta
    stdout_deltas = [d for d in delta_events if d.stream == "stdout"]
    assert len(stdout_deltas) >= 1, (
        f"Expected >=1 stdout delta, got {delta_events}"
    )
    assert "hello" in "".join(d.delta for d in stdout_deltas)

    # Must have exactly one end event
    assert len(end_events) == 1

    # Every delta must appear before the end event in the event stream
    last_delta_idx = max(
        emitter.events.index(d) for d in delta_events
    )
    end_idx = emitter.events.index(end_events[0])
    assert last_delta_idx < end_idx, (
        "All delta events must come BEFORE the end event"
    )


@pytest.mark.asyncio
async def test_stderr_streaming_emits_delta_events(tmp_path):
    """Phase 31.5: stderr chunks must emit ExecCommandOutputDeltaEvent
    with stream='stderr'."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"import sys; sys.stderr.write('err-msg'); sys.stderr.flush()\"",
        _event_emitter=emitter,
        _turn_id="t-stream-err",
        _tool_call_id="tc-stream-err",
    )

    delta_events = [e for e in emitter.events
                    if isinstance(e, ExecCommandOutputDeltaEvent)]
    stderr_deltas = [d for d in delta_events if d.stream == "stderr"]
    assert len(stderr_deltas) >= 1, (
        f"Expected >=1 stderr delta, got {delta_events}"
    )
    assert "err-msg" in "".join(d.delta for d in stderr_deltas)

    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1


@pytest.mark.asyncio
async def test_multiple_stdout_chunks_produce_multiple_delta_events(tmp_path):
    """Phase 31.5: a command with enough stdout should produce multiple
    delta events (reading in 4KB chunks)."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    # Write ~10KB of output to guarantee multiple chunks
    await tool.execute(
        "python -c \"for i in range(200): print('x' * 50)\"",
        _event_emitter=emitter,
        _turn_id="t-multi",
        _tool_call_id="tc-multi",
    )

    stdout_deltas = [
        e for e in emitter.events
        if isinstance(e, ExecCommandOutputDeltaEvent) and e.stream == "stdout"
    ]
    assert len(stdout_deltas) >= 2, (
        f"Expected >=2 stdout delta events for ~10KB output, got {len(stdout_deltas)}"
    )


@pytest.mark.asyncio
async def test_final_result_still_contains_stdout_stderr(tmp_path):
    """Phase 31.5: even with streaming, the final tool result must
    still contain the aggregated stdout/stderr."""
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"print('result-out'); import sys; sys.stderr.write('result-err\\n')\"",
        _event_emitter=_EventCollector(),
        _turn_id="t-agg",
        _tool_call_id="tc-agg",
    )

    assert "result-out" in output
    assert "result-err" in output


# ── Phase 31.6: timeout kills subprocess ────────────────────────────────

@pytest.mark.asyncio
async def test_timeout_kills_subprocess(tmp_path):
    """Phase 31.6: when a command exceeds its timeout, the subprocess
    must be killed and a single end event emitted."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))

    output = await tool.execute(
        # Sleep long — will be killed by 50ms timeout
        "python -c \"import time; time.sleep(30)\"",
        _event_emitter=emitter,
        _turn_id="t-timeout",
        _tool_call_id="tc-timeout",
        _sandbox=_make_none_selection(timeout_ms=50),
    )

    assert "timed out" in output.lower()

    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1, (
        f"Expected exactly 1 end event after timeout, got {len(end_events)}"
    )
    assert end_events[0].exit_code != 0, (
        "Timeout should produce non-zero exit_code"
    )


# ── Phase 31.6: cancel_event kills subprocess ───────────────────────────

@pytest.mark.asyncio
async def test_cancel_event_kills_running_subprocess(tmp_path):
    """Phase 31.6: when cancel_event is set during execution, the
    subprocess must be killed and a single end event emitted."""
    emitter = _EventCollector()
    cancel_event = asyncio.Event()
    tool = ExecTool(timeout=30, working_dir=str(tmp_path))

    async def cancel_after_delay():
        await asyncio.sleep(0.3)
        cancel_event.set()

    cancel_task = asyncio.create_task(cancel_after_delay())

    output = await tool.execute(
        "python -c \"import time; time.sleep(60)\"",
        _event_emitter=emitter,
        _turn_id="t-cancel",
        _tool_call_id="tc-cancel",
        _cancel_event=cancel_event,
    )

    await cancel_task

    assert "cancelled" in output.lower()

    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1, (
        f"Expected exactly 1 end event after cancel, got {len(end_events)}"
    )
    assert end_events[0].exit_code != 0, (
        "Cancellation should produce non-zero exit_code"
    )


@pytest.mark.asyncio
async def test_cancel_before_start_returns_safely(tmp_path):
    """Phase 31.6: if cancel_event is already set before execution,
    return cancelled result without spawning a subprocess."""
    emitter = _EventCollector()
    cancel_event = asyncio.Event()
    cancel_event.set()  # already cancelled

    tool = ExecTool(timeout=5, working_dir=str(tmp_path))

    output = await tool.execute(
        "echo should-not-run",
        _event_emitter=emitter,
        _turn_id="t-pre-cancel",
        _tool_call_id="tc-pre-cancel",
        _cancel_event=cancel_event,
    )

    assert "cancelled" in output.lower()

    # Should still get begin + end events
    begin_events = [e for e in emitter.events
                    if isinstance(e, ExecCommandBeginEvent)]
    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(begin_events) == 1
    assert len(end_events) == 1


# ── Phase 31.5: duration_ms ─────────────────────────────────────────────

@pytest.mark.asyncio
async def test_duration_ms_greater_than_zero(tmp_path):
    """Phase 31.5: ExecCommandEndEvent.duration_ms must reflect real
    wall-clock time, not the old hard-coded 0."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    # Sleep for ~200ms to guarantee measurable duration
    await tool.execute(
        "python -c \"import time; time.sleep(0.2)\"",
        _event_emitter=emitter,
        _turn_id="t-dur",
        _tool_call_id="tc-dur",
    )

    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].duration_ms > 0, (
        f"duration_ms must be > 0 for a 200ms sleep, got {end_events[0].duration_ms}"
    )
    # Should be at least ~100ms (sleep was 200ms)
    assert end_events[0].duration_ms >= 100, (
        f"duration_ms too low: {end_events[0].duration_ms}"
    )


# ── Phase 31.6: no duplicate end events on error ────────────────────────

@pytest.mark.asyncio
async def test_no_duplicate_end_event_on_command_error(tmp_path):
    """Phase 31.6: a command that fails (non-zero exit) must still emit
    exactly one end event."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    await tool.execute(
        "python -c \"import sys; sys.exit(2)\"",
        _event_emitter=emitter,
        _turn_id="t-error",
        _tool_call_id="tc-error",
    )

    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1, (
        f"Expected exactly 1 end event on command error, got {len(end_events)}"
    )


@pytest.mark.asyncio
async def test_no_duplicate_end_event_on_launch_failure(tmp_path):
    """Phase 31.6: a command that fails to launch (bad executable) must
    still emit exactly one end event."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    await tool.execute(
        "nonexistent_command_xyz_123",
        _event_emitter=emitter,
        _turn_id="t-launch-fail",
        _tool_call_id="tc-launch-fail",
    )

    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1, (
        f"Expected exactly 1 end event on launch failure, got {len(end_events)}"
    )


# ── Phase 31.6+ resource cleanup ───────────────────────────────────────

@pytest.mark.asyncio
async def test_normal_completion_with_cancel_event_no_pending_cancel_wait(tmp_path):
    """When a command completes normally but a cancel_event was passed,
    the internal cancel_wait task must be cancelled (not left pending)."""
    emitter = _EventCollector()
    cancel_event = asyncio.Event()
    tool = ExecTool(timeout=10, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"print('normal-exit')\"",
        _event_emitter=emitter,
        _turn_id="t-clean-normal",
        _tool_call_id="tc-clean-normal",
        _cancel_event=cancel_event,
    )

    assert "normal-exit" in output

    # Must emit exactly one begin + one end event.
    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1
    assert end_events[0].exit_code == 0


@pytest.mark.asyncio
async def test_timeout_no_pending_tasks(tmp_path):
    """After a timeout kill, no internal asyncio task (proc_wait,
    stdout/stderr readers) should remain pending."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"import time; time.sleep(30)\"",
        _event_emitter=_EventCollector(),
        _turn_id="t-clean-timeout",
        _tool_call_id="tc-clean-timeout",
        _sandbox=_make_none_selection(timeout_ms=50),
    )

    assert "timed out" in output.lower()


@pytest.mark.asyncio
async def test_cancel_no_pending_tasks(tmp_path):
    """After cancel-event kills a running subprocess, no internal
    asyncio task should remain pending."""
    emitter = _EventCollector()
    cancel_event = asyncio.Event()
    tool = ExecTool(timeout=30, working_dir=str(tmp_path))

    async def cancel_after_delay():
        await asyncio.sleep(0.2)
        cancel_event.set()

    cancel_task = asyncio.create_task(cancel_after_delay())

    output = await tool.execute(
        "python -c \"import time; time.sleep(60)\"",
        _event_emitter=emitter,
        _turn_id="t-clean-cancel",
        _tool_call_id="tc-clean-cancel",
        _cancel_event=cancel_event,
    )

    await cancel_task

    assert "cancelled" in output.lower()
    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(end_events) == 1


# ── Helpers ─────────────────────────────────────────────────────────────

def _make_none_selection(*, timeout_ms: int = 30_000):
    """Create a minimal SandboxSelection(NONE) for tests that need
    to pass _sandbox kwarg."""
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )
    return SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        timeout_ms=timeout_ms,
        env_passthrough=[],
        reason="test",
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 31.8: Ledger writing via _ledger_runtime injection
# ═══════════════════════════════════════════════════════════════════════════


class _FakeLedger:
    """Minimal fake LedgerRuntime that records append_item calls."""

    def __init__(self):
        self.items: list[dict] = []

    async def append_item(self, **kwargs):
        self.items.append(kwargs)


@pytest.mark.asyncio
async def test_exec_tool_writes_ledger_begin_and_end(tmp_path):
    """ExecTool with _ledger_runtime must write exec_started + exec_completed."""
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )

    fake_ledger = _FakeLedger()
    emitter = _EventCollector()

    tool = ExecTool(timeout=5)
    result = await tool.execute(
        "echo hello",
        _event_emitter=emitter,
        _turn_id="turn-1",
        _tool_call_id="call-1",
        _sandbox=SandboxSelection(
            sandbox_type=SandboxType.NONE,
            filesystem_policy=FileSystemSandboxPolicy(),
            network_policy=NetworkSandboxPolicy.ALLOW_ALL,
            timeout_ms=5000,
            env_passthrough=[],
            reason="test",
        ),
        _ledger_runtime=fake_ledger,
        _thread_id="thread-1",
    )

    assert "hello" in result

    # Verify ledger items
    item_types = [it["item_type"] for it in fake_ledger.items]
    assert "exec_started" in item_types, f"Missing exec_started in {item_types}"
    assert "exec_completed" in item_types, f"Missing exec_completed in {item_types}"

    started = next(it for it in fake_ledger.items if it["item_type"] == "exec_started")
    assert started["payload"]["command"] == "echo hello"
    assert started["payload"]["sandbox_type"] == "none"
    assert started["thread_id"] == "thread-1"
    assert started["turn_id"] == "turn-1"

    completed = next(it for it in fake_ledger.items if it["item_type"] == "exec_completed")
    assert completed["payload"]["tool_call_id"] == "call-1"
    assert completed["payload"]["exit_code"] == 0
    assert completed["payload"]["cancelled"] is False
    assert completed["payload"]["timed_out"] is False


@pytest.mark.asyncio
async def test_exec_tool_writes_output_deltas_to_ledger(tmp_path):
    """ExecTool must write exec_output_delta for each stdout/stderr chunk."""
    import asyncio as _asyncio

    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )

    fake_ledger = _FakeLedger()
    emitter = _EventCollector()

    tool = ExecTool(timeout=5)
    result = await tool.execute(
        "echo line1 && echo line2",
        _event_emitter=emitter,
        _turn_id="turn-delta",
        _tool_call_id="call-delta",
        _sandbox=SandboxSelection(
            sandbox_type=SandboxType.NONE,
            filesystem_policy=FileSystemSandboxPolicy(),
            network_policy=NetworkSandboxPolicy.ALLOW_ALL,
            timeout_ms=5000,
            env_passthrough=[],
            reason="test",
        ),
        _ledger_runtime=fake_ledger,
        _thread_id="thread-delta",
    )

    # Verify delta items exist
    deltas = [it for it in fake_ledger.items if it["item_type"] == "exec_output_delta"]
    assert len(deltas) >= 1, f"Expected at least 1 output delta, got {len(deltas)}"
    for d in deltas:
        assert d["payload"]["tool_call_id"] == "call-delta"
        assert d["payload"]["stream"] in ("stdout", "stderr")


@pytest.mark.asyncio
async def test_exec_tool_launch_failure_recorded_in_ledger():
    """When process launch fails, exec_completed must be written with exit_code=1."""
    fake_ledger = _FakeLedger()
    emitter = _EventCollector()

    tool = ExecTool(timeout=5)
    # Use a command that will fail to launch (invalid shell syntax on Windows)
    result = await tool.execute(
        "nonexistent_command_xyz_12345",
        _event_emitter=emitter,
        _turn_id="turn-fail",
        _tool_call_id="call-fail",
        _sandbox=_none_sandbox(),
        _ledger_runtime=fake_ledger,
        _thread_id="thread-fail",
    )

    # exec_completed should still be written
    completed = [it for it in fake_ledger.items if it["item_type"] == "exec_completed"]
    assert len(completed) >= 1, f"Expected exec_completed for failed launch, got {fake_ledger.items}"
    # exit_code may be 1 or non-zero (depends on shell)
    assert completed[0]["payload"]["tool_call_id"] == "call-fail"


@pytest.mark.asyncio
async def test_exec_tool_cancelled_before_start_recorded(tmp_path):
    """When cancel_event is already set before execution, exec_completed
    must be written with cancelled=True and exit_code=-1."""
    fake_ledger = _FakeLedger()
    emitter = _EventCollector()
    cancel_evt = asyncio.Event()
    cancel_evt.set()  # Already cancelled before start

    tool = ExecTool(timeout=5)
    result = await tool.execute(
        "echo should_not_run",
        _event_emitter=emitter,
        _turn_id="turn-cancel",
        _tool_call_id="call-cancel",
        _cancel_event=cancel_evt,
        _sandbox=_none_sandbox(),
        _ledger_runtime=fake_ledger,
        _thread_id="thread-cancel",
    )

    assert "cancelled" in result.lower()

    # exec_completed should have cancelled=True
    completed = [it for it in fake_ledger.items if it["item_type"] == "exec_completed"]
    assert len(completed) == 1
    assert completed[0]["payload"]["cancelled"] is True
    assert completed[0]["payload"]["exit_code"] == -1


def _none_sandbox():
    """Helper: SandboxSelection for NONE (direct execution)."""
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )
    return SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        timeout_ms=5000,
        env_passthrough=[],
        reason="test",
    )
