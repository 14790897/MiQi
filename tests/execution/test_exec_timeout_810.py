"""Tests for #810 — exec timeout model upgrade.

Covers: the per-call ``timeout`` parameter (validation, rejection over
the max cap before any subprocess spawns, override of the tool default
and of the SandboxSelection policy timeout), the generic exec heartbeat
(silent long commands keep emitting progress events; chatty commands
suppress them), process-tree kill on timeout, structured timeout
results, and the config wiring (ExecToolConfig fields + orchestrator
default budget).
"""

import asyncio
import json
import os
import re
import subprocess
import time

import pytest

from miqi.agent.tools.shell import ExecTool
from miqi.config.schema import ExecToolConfig
from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
from miqi.protocol.events import ExecCommandOutputDeltaEvent
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
    """Create a SandboxSelection for testing (same shape as the other
    exec-tool test module)."""
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


class _EventRecorder:
    """Minimal event emitter capturing emitted events for assertions."""

    def __init__(self) -> None:
        self.events = []

    async def emit(self, event) -> None:
        self.events.append(event)

    def deltas(self) -> list[ExecCommandOutputDeltaEvent]:
        return [e for e in self.events if isinstance(e, ExecCommandOutputDeltaEvent)]


def _pid_alive(pid: int) -> bool:
    """Cross-platform liveness probe used by the process-tree test."""
    if os.name == "nt":
        # tasklist on a Chinese Windows emits GBK — compare raw bytes
        # instead of decoding.
        out = subprocess.run(
            ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
            capture_output=True,
        ).stdout or b""
        return str(pid).encode("ascii") in out
    try:
        os.kill(pid, 0)
        return True
    except (ProcessLookupError, PermissionError):
        return False


# ── config ─────────────────────────────────────────────────────────────


def test_exec_tool_config_defaults():
    """#810: new timeout-model fields have sane defaults and keep the
    existing 60 s default (the issue's 30 s cap lived in the sandbox
    policy, not in the config)."""
    cfg = ExecToolConfig()
    assert cfg.timeout == 60
    assert cfg.max_timeout == 1800
    assert cfg.idle_timeout == 90
    assert cfg.heartbeat_interval == 30
    assert cfg.kill_grace_seconds == 5


def test_exec_tool_config_custom_values():
    cfg = ExecToolConfig(
        timeout=120, max_timeout=3600, idle_timeout=60,
        heartbeat_interval=15, kill_grace_seconds=10,
    )
    assert cfg.timeout == 120
    assert cfg.max_timeout == 3600
    assert cfg.idle_timeout == 60
    assert cfg.heartbeat_interval == 15
    assert cfg.kill_grace_seconds == 10


# ── tool schema ────────────────────────────────────────────────────────


def test_exec_tool_schema_includes_timeout():
    """The model can request a per-call timeout via the tool schema."""
    tool = ExecTool()
    props = tool.parameters["properties"]
    assert "timeout" in props
    assert props["timeout"]["type"] == "integer"
    assert props["timeout"]["minimum"] == 1


def test_exec_tool_constructor_defaults():
    tool = ExecTool()
    assert tool.timeout == 60
    assert tool.max_timeout == 1800
    assert tool.idle_timeout == 90
    assert tool.heartbeat_interval == 30
    assert tool.kill_grace_seconds == 5


# ── _normalize_timeout ─────────────────────────────────────────────────


def test_normalize_timeout_none_means_default():
    tool = ExecTool()
    assert tool._normalize_timeout(None) == (None, None)


def test_normalize_timeout_valid_request():
    tool = ExecTool()
    ms, err = tool._normalize_timeout(600)
    assert ms == 600_000
    assert err is None


@pytest.mark.parametrize(
    "raw",
    ["abc", 0, -5, 3.7, 999999, 10**9],
)
def test_normalize_timeout_rejects_invalid(raw):
    """Non-integers, values < 1 and requests over max_timeout are
    rejected — never silently clamped."""
    tool = ExecTool()
    ms, err = tool._normalize_timeout(raw)
    assert ms is None
    assert err is not None
    assert "Error" in err


def test_normalize_timeout_uses_instance_max():
    tool = ExecTool(max_timeout=120)
    ms, err = tool._normalize_timeout(121)
    assert ms is None
    assert "120" in err


# ── execute-level validation (no subprocess spawns) ────────────────────


@pytest.mark.asyncio
async def test_execute_rejects_over_limit_before_running(tmp_path):
    """timeout=999999 must be rejected BEFORE the command runs — a
    marker file the command would create must not exist afterwards."""
    tool = ExecTool()
    marker = tmp_path / "should-not-exist.txt"
    result = await tool.execute(
        f"python -c \"import pathlib; pathlib.Path({str(marker)!r}).write_text('ran')\"",
        timeout=999999,
    )
    assert "超过上限" in result
    assert not marker.exists()


@pytest.mark.asyncio
async def test_execute_rejects_non_integer_timeout():
    tool = ExecTool()
    result = await tool.execute("echo hi", timeout="fast")
    assert "必须是整数秒" in result


# ── per-call timeout semantics ─────────────────────────────────────────


@pytest.mark.asyncio
async def test_requested_timeout_overrides_tool_default():
    """A short tool default must not truncate a call that explicitly
    asks for more time."""
    tool = ExecTool(timeout=1)
    result = await tool.execute(
        "python -c \"import time; time.sleep(2); print('done')\"",
        timeout=10,
    )
    assert "done" in result
    assert "超时" not in result


@pytest.mark.asyncio
async def test_requested_timeout_shorter_than_default_enforced():
    """An explicit short timeout must be enforced even when the tool
    default is long."""
    tool = ExecTool(timeout=60)
    result = await tool.execute(
        "python -c \"import time; time.sleep(5)\"",
        timeout=1,
    )
    assert "超时" in result


@pytest.mark.asyncio
async def test_no_timeout_arg_uses_tool_default():
    tool = ExecTool(timeout=1)
    result = await tool.execute("python -c \"import time; time.sleep(5)\"")
    assert "超时" in result


@pytest.mark.asyncio
async def test_requested_timeout_overrides_sandbox_selection():
    """The SandboxSelection policy timeout (30 s hard cap from #810) is
    the fallback — an explicit per-call request wins."""
    tool = ExecTool(timeout=1)
    sel = _make_selection(SandboxType.NONE, timeout_ms=50)  # 50 ms policy cap
    result = await tool.execute(
        "python -c \"print('selected-ok')\"",
        timeout=10,
        _sandbox=sel,
    )
    assert "selected-ok" in result
    assert "超时" not in result


@pytest.mark.asyncio
async def test_requested_timeout_applies_with_sandbox_selection():
    """With a generous selection (30 s), a short explicit request still
    times out — the request is authoritative, not the selection."""
    tool = ExecTool(timeout=60)
    sel = _make_selection(SandboxType.NONE, timeout_ms=30_000)
    result = await tool.execute(
        "python -c \"import time; time.sleep(5)\"",
        timeout=1,
        _sandbox=sel,
    )
    assert "超时" in result


@pytest.mark.asyncio
async def test_requested_timeout_applies_in_restricted_path(tmp_path):
    """RESTRICTED enforcement honours the per-call request over the
    selection's policy timeout."""
    tool = ExecTool(timeout=60, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED, timeout_ms=50)
    result = await tool.execute(
        "python -c \"print('restricted-ok')\"",
        timeout=10,
        working_dir=str(tmp_path),
        _sandbox=sel,
    )
    assert "restricted-ok" in result
    assert "超时" not in result


# ── structured timeout result ──────────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_result_is_structured():
    """Timeout results carry machine-readable metadata (duration,
    timeout budget, termination, retryability) plus a Chinese summary
    with recovery suggestions."""
    tool = ExecTool(timeout=1)
    result = await tool.execute("python -c \"import time; time.sleep(5)\"")
    assert "超时" in result
    meta = json.loads(result[result.index("{"):result.index("}") + 1])
    assert meta["status"] == "timeout"
    assert meta["exit_code"] is None
    assert meta["duration_ms"] >= 1000
    assert meta["timeout_ms"] == 1000
    assert meta["process_terminated"] is True
    assert meta["retryable"] is True
    assert "建议" in result


@pytest.mark.asyncio
async def test_timeout_result_includes_partial_output():
    """The timeout result carries the tail of whatever the command
    printed before it died — the model can see the progress and
    recover."""
    tool = ExecTool(timeout=1)
    result = await tool.execute(
        "python -c \"import time; print('phase-1-done', flush=True); time.sleep(5)\""
    )
    assert "超时" in result
    assert "phase-1-done" in result
    assert "超时前的部分输出" in result


# ── heartbeat ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_heartbeat_keeps_silent_command_alive():
    """A silent long-running command emits periodic progress deltas
    (the bridge drain never idles out)."""
    recorder = _EventRecorder()
    tool = ExecTool(timeout=60, heartbeat_interval=1.0, idle_timeout=90)
    result = await tool.execute(
        "python -c \"import time; time.sleep(2.6)\"",
        _event_emitter=recorder,
        _turn_id="t-heartbeat",
        _tool_call_id="tc-heartbeat",
    )
    assert "超时" not in result
    beats = [d.delta for d in recorder.deltas() if "[exec] 命令仍在运行" in d.delta]
    assert len(beats) >= 1
    # heartbeat deltas carry the tool call id so the frontend can attach
    # them to the right inline terminal.
    assert all(d.tool_call_id == "tc-heartbeat" for d in recorder.deltas())


@pytest.mark.asyncio
async def test_heartbeat_idle_warning_after_silence():
    """After idle_timeout of silence the heartbeat text switches to a
    staleness warning (informational — never a kill)."""
    recorder = _EventRecorder()
    tool = ExecTool(timeout=60, heartbeat_interval=1.0, idle_timeout=0.5)
    await tool.execute(
        "python -c \"import time; time.sleep(2.6)\"",
        _event_emitter=recorder,
    )
    beats = [d.delta for d in recorder.deltas() if "已无输出" in d.delta]
    assert len(beats) >= 1


@pytest.mark.asyncio
async def test_heartbeat_suppressed_by_output():
    """A chatty command emits no heartbeats — real output deltas already
    keep the turn alive (no duplicate liveness noise)."""
    recorder = _EventRecorder()
    tool = ExecTool(timeout=60, heartbeat_interval=1.0, idle_timeout=90)
    await tool.execute(
        "python -c \"import time; [(print('tick', i, flush=True), time.sleep(0.4)) for i in range(6)]\"",
        _event_emitter=recorder,
    )
    beats = [d for d in recorder.deltas() if "[exec] 命令仍在运行" in d.delta]
    assert beats == []


@pytest.mark.asyncio
async def test_heartbeat_stops_after_completion():
    """No heartbeat events leak after the command finishes."""
    recorder = _EventRecorder()
    tool = ExecTool(timeout=60, heartbeat_interval=1.0, idle_timeout=90)
    await tool.execute(
        "python -c \"import time; time.sleep(2.2)\"",
        _event_emitter=recorder,
    )
    count_after = len(recorder.deltas())
    await asyncio.sleep(1.5)
    assert len(recorder.deltas()) == count_after


# ── process-tree kill on timeout ───────────────────────────────────────


@pytest.mark.asyncio
async def test_timeout_kills_process_tree():
    """On timeout the whole process tree dies — retrying can never
    collide with a still-running sibling (two pip installs, two
    xelatex on the same .aux)."""
    tool = ExecTool(timeout=3)
    result = await tool.execute(
        "python -c \"import subprocess, sys, time; "
        "p = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(30)']); "
        "print('CHILD_PID', p.pid, flush=True); time.sleep(30)\""
    )
    assert "超时" in result
    m = re.search(r"CHILD_PID (\d+)", result)
    assert m is not None, f"child pid not reported; result={result!r}"
    child_pid = int(m.group(1))
    # taskkill /T needs a moment; poll up to 5 s for the child to die.
    deadline = time.monotonic() + 5.0
    while time.monotonic() < deadline:
        if not _pid_alive(child_pid):
            break
        await asyncio.sleep(0.3)
    assert not _pid_alive(child_pid), (
        f"child process {child_pid} survived the parent timeout kill"
    )


# ── config wiring ──────────────────────────────────────────────────────


def test_orchestrator_default_budget_follows_config():
    """#810 root fix: the sandbox policy default exec budget follows
    tools.exec.timeout instead of the hard-coded 30 s cap."""
    from miqi.execution.factory import create_default_orchestrator

    orchestrator = create_default_orchestrator(
        tool_registry=None, default_exec_timeout_ms=60_000,
    )
    assert orchestrator.sandbox.default_timeout_ms == 60_000

    default_orchestrator = create_default_orchestrator(tool_registry=None)
    assert default_orchestrator.sandbox.default_timeout_ms == 30_000
