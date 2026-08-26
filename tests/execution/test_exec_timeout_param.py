"""Tests for exec per-call timeout parameter (issue #810).

Issue #810: the exec tool previously enforced a fixed default timeout
(30-60 s) for every command — long tasks (pip installs, chart rendering,
batch link checks) died mid-run.  The fix adds a model-supplied
``timeout`` argument (seconds, clamped to [1, max_timeout]) that
overrides both the configured default and the orchestrator's
SandboxSelection.timeout_ms, plus a timeout message that names the
configured limit, the actual elapsed time, and a retry hint.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.agent.tools.shell import ExecTool


# ── Schema / construction ──────────────────────────────────────────────


def test_schema_exposes_timeout_param_with_cap():
    """The exec schema must declare the ``timeout`` argument with
    minimum 1 and maximum == max_timeout."""
    tool = ExecTool(timeout=60, max_timeout=300)
    props = tool.parameters["properties"]
    assert "timeout" in props
    assert props["timeout"]["type"] == "integer"
    assert props["timeout"]["minimum"] == 1
    assert props["timeout"]["maximum"] == 300
    assert str(60) in props["timeout"]["description"]  # names the default


def test_execution_timeout_sits_above_cap():
    """The registry-level safety net (ToolRegistry.execute's
    asyncio.wait_for) must sit ABOVE max_timeout so long per-call
    timeouts are not pre-empted by a generic registry error."""
    tool = ExecTool(max_timeout=600)
    assert tool.execution_timeout == 630


def test_validation_rejects_out_of_range_timeout():
    """Schema validation rejects timeout values outside [1, max_timeout]."""
    tool = ExecTool(timeout=60, max_timeout=120)
    assert tool.validate_params({"command": "ls", "timeout": 0})
    assert tool.validate_params({"command": "ls", "timeout": 121})
    assert not tool.validate_params({"command": "ls", "timeout": 1})
    assert not tool.validate_params({"command": "ls", "timeout": 120})
    assert not tool.validate_params({"command": "ls"})


# ── Per-call timeout behaviour (real subprocesses) ─────────────────────


@pytest.mark.subprocess
@pytest.mark.asyncio
async def test_per_call_timeout_overrides_default(require_subprocess, tmp_path):
    """A model-supplied timeout shorter than the configured default must
    actually apply, and the timeout message must carry elapsed time,
    the retry hint, and the cap."""
    tool = ExecTool(timeout=60, max_timeout=600, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"import time; time.sleep(30)\"",
        timeout=1,
    )

    assert "超时" in output
    assert "实际已执行" in output
    assert "timeout 参数" in output
    assert "1–600 秒" in output


@pytest.mark.subprocess
@pytest.mark.asyncio
async def test_per_call_timeout_extends_selection(require_subprocess, tmp_path):
    """A model-supplied timeout longer than the SandboxSelection's
    timeout_ms must win over the selection (issue #810 — the selection
    carries the policy default, not a ceiling)."""
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy,
        NetworkSandboxPolicy,
    )

    tool = ExecTool(timeout=60, max_timeout=600, working_dir=str(tmp_path))
    sel = SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        timeout_ms=50,  # selection would kill this command in 50ms
        env_passthrough=[],
        reason="test",
    )

    output = await tool.execute(
        "python -c \"import time; time.sleep(0.5); print('done-long')\"",
        timeout=30,
        _sandbox=sel,
    )

    assert "done-long" in output
    assert "超时" not in output


@pytest.mark.subprocess
@pytest.mark.asyncio
async def test_per_call_timeout_shortens_selection(require_subprocess, tmp_path):
    """Conversely, a model-supplied timeout shorter than the selection's
    must also win — the per-call value is authoritative both ways."""
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy,
        NetworkSandboxPolicy,
    )

    tool = ExecTool(timeout=60, max_timeout=600, working_dir=str(tmp_path))
    sel = SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        timeout_ms=30_000,
        env_passthrough=[],
        reason="test",
    )

    output = await tool.execute(
        "python -c \"import time; time.sleep(30)\"",
        timeout=1,
        _sandbox=sel,
    )

    assert "超时" in output


@pytest.mark.subprocess
@pytest.mark.asyncio
async def test_per_call_timeout_clamped_to_max(require_subprocess, tmp_path):
    """Values above max_timeout are clamped (backstop — validation already
    rejects them), and the timeout message shows the effective cap."""
    tool = ExecTool(timeout=60, max_timeout=2, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"import time; time.sleep(30)\"",
        timeout=999,
    )

    assert "超时" in output
    assert "命令在 2 秒后超时" in output  # clamped, not 999
    assert "1–2 秒" in output


@pytest.mark.subprocess
@pytest.mark.asyncio
async def test_per_call_timeout_flows_into_sandbox_path(require_subprocess, tmp_path):
    """The per-call timeout must also govern the bwrap sandbox path
    (KUN runtime has no orchestrator-injected selection — timeout_ms=None
    reaches _execute_in_sandbox as the per-call override)."""
    # Sleep-forever process: only the timeout can end it.
    process = await asyncio.create_subprocess_exec(
        "python", "-c", "import time; time.sleep(3600)",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    handle = MagicMock()
    handle.stdout = process.stdout
    handle.stderr = process.stderr
    handle.returncode = None
    handle.wait = AsyncMock(side_effect=process.wait)
    handle.kill = AsyncMock(side_effect=process.kill)
    handle.cleanup = AsyncMock()

    sandbox = MagicMock()
    sandbox.is_running = True
    sandbox.get_sandbox_env = MagicMock(return_value={})
    sandbox.run_command_streaming = AsyncMock(return_value=handle)
    mgr = MagicMock()
    mgr.active_sandbox = sandbox

    tool = ExecTool(
        timeout=60, max_timeout=600,
        working_dir=str(tmp_path), sandbox_manager=mgr,
    )

    try:
        output = await tool.execute(
            "sleep 999",
            timeout=1,
            _sandbox=None,  # KUN path: no selection injected
        )
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()

    assert "超时" in output
    assert "实际已执行" in output
    handle.kill.assert_awaited()
