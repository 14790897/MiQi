"""Tests for miqi.execution.orchestrator."""

import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock
from miqi.execution.orchestrator import (
    ToolOrchestrator,
    ToolExecutionContext,
    OrchestrationResult,
)


@pytest.fixture
def mock_components():
    """Create mocked components for the orchestrator.

    Containers are plain MagicMock; only async methods are AsyncMock
    to avoid RuntimeWarning from unawaited coroutines during GC.
    """
    pe = MagicMock()
    pe.check = AsyncMock()
    se = MagicMock()
    se.select = AsyncMock()
    hr = MagicMock()
    hr.run = AsyncMock()
    tr = MagicMock()
    ev = MagicMock()
    ev.emit = AsyncMock()
    return {
        "permission_engine": pe,
        "sandbox_engine": se,
        "hook_runtime": hr,
        "tool_registry": tr,
        "event_emitter": ev,
    }


@pytest.fixture
def orchestrator(mock_components):
    return ToolOrchestrator(
        permission_engine=mock_components["permission_engine"],
        sandbox_engine=mock_components["sandbox_engine"],
        hook_runtime=mock_components["hook_runtime"],
        tool_registry=mock_components["tool_registry"],
        event_emitter=mock_components["event_emitter"],
    )


def make_ctx(**kwargs):
    return ToolExecutionContext(
        tool_name=kwargs.get("tool_name", "read_file"),
        tool_call_id=kwargs.get("tool_call_id", "call_001"),
        arguments=kwargs.get("arguments", {"path": "test.txt"}),
        turn_id=kwargs.get("turn_id", "turn_001"),
        thread_id=kwargs.get("thread_id", "thread_abc"),
        agent_type=kwargs.get("agent_type", "main"),
    )


@pytest.mark.asyncio
async def test_execute_success_path(orchestrator, mock_components):
    """Full success path: hooks → permission → execute."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    mock_components["tool_registry"].get.return_value = MagicMock()
    mock_components["tool_registry"].get.return_value.execute = AsyncMock(
        return_value="file content here"
    )

    ctx = make_ctx()
    result = await orchestrator.execute(ctx)

    # Hooks should have been called
    mock_components["hook_runtime"].run.assert_called()
    # Permission checked
    mock_components["permission_engine"].check.assert_called_once()
    # Tool executed
    mock_components["tool_registry"].get.return_value.execute.assert_called_once()
    # Result set
    assert result.result == "file content here"
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_execute_denied_by_policy(orchestrator, mock_components):
    """Policy denies — should return error without execution."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.DENY,
        reason="Blocked by deny pattern",
    )

    ctx = make_ctx(tool_name="exec", arguments={"command": "sudo rm -rf /"})
    result = await orchestrator.execute(ctx)

    assert "Permission denied" in result.result
    # Tool should NOT have been executed
    mock_components["tool_registry"].get.assert_not_called()


@pytest.mark.asyncio
async def test_execute_approval_required_then_allowed(orchestrator, mock_components):
    """Approval required → wait for user → allow."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    # First call: requires approval
    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: rm file",
        details={"command": "rm file"},
        allow_permanent=True,
    )

    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    mock_components["tool_registry"].get.return_value = MagicMock()
    mock_components["tool_registry"].get.return_value.execute = AsyncMock(
        return_value="done"
    )

    ctx = make_ctx(tool_name="exec", arguments={"command": "rm file"})

    # Start execute in background — it will block waiting for approval
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    # Simulate user approving
    orchestrator.resolve_approval(f"{ctx.turn_id}:{ctx.tool_call_id}", "allow")

    result = await task
    assert result.result == "done"
    # Should have emitted approval request event
    mock_components["event_emitter"].emit.assert_called()


@pytest.mark.asyncio
async def test_execute_approval_timeout(orchestrator, mock_components):
    """Approval times out — should deny."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: dangerous command",
    )

    # Set short timeout for test
    orchestrator.approval_timeout_ms = 100

    ctx = make_ctx(tool_name="exec", arguments={"command": "dangerous"})
    result = await orchestrator.execute(ctx)

    assert "denied" in result.result.lower() or "timeout" in result.result.lower()
    mock_components["tool_registry"].get.assert_not_called()


@pytest.mark.asyncio
async def test_execute_context_populated(orchestrator, mock_components):
    """Verify ToolExecutionContext fields are populated after execution."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import FileSystemSandboxPolicy, FileSystemAccessMode, NetworkSandboxPolicy

    mock_components["sandbox_engine"].select.return_value = SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        reason="test",
    )
    mock_components["tool_registry"].get.return_value = MagicMock()
    mock_components["tool_registry"].get.return_value.execute = AsyncMock(
        return_value="ok"
    )

    ctx = make_ctx()
    result = await orchestrator.execute(ctx)

    assert result.permission_decision is not None
    assert result.sandbox_selection is not None
    assert result.result == "ok"
    assert result.duration_ms >= 0


@pytest.mark.asyncio
async def test_unknown_tool_returns_error(orchestrator, mock_components):
    """Unknown tool should return error result."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    mock_components["tool_registry"].get.return_value = None  # Tool not found

    ctx = make_ctx(tool_name="nonexistent_tool")
    result = await orchestrator.execute(ctx)

    assert "Unknown tool" in result.result


@pytest.mark.asyncio
async def test_resolve_approval_deny(orchestrator, mock_components):
    """Resolving approval with 'deny' should deny execution."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )

    ctx = make_ctx(tool_name="exec", arguments={"command": "cmd"})
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    orchestrator.resolve_approval(f"{ctx.turn_id}:{ctx.tool_call_id}", "deny")
    result = await task

    assert "denied" in result.result.lower()


# ── Phase 31.2b: SandboxSelection always injected for exec tool ───────────

@pytest.mark.asyncio
async def test_exec_tool_always_receives_sandbox_selection(
    orchestrator, mock_components,
):
    """Phase 31 blocker fix: for exec tool, orchestrator must always
    inject _sandbox kwarg — even when sandbox_type is NONE.  Without it,
    ExecTool falls back to the legacy path and may use an active sandbox
    against the orchestrator's decision."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )

    # Sandbox engine explicitly returns NONE — the orchestrator chose
    # direct execution after exhausting stronger sandbox types.
    none_selection = SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        timeout_ms=30_000,
        env_passthrough=["MY_VAR"],
        reason="No stronger sandbox available — orchestrator chose NONE",
    )
    mock_components["sandbox_engine"].select.return_value = none_selection

    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="exec-ok")
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(tool_name="exec", arguments={"command": "echo hello"})
    result = await orchestrator.execute(ctx)

    assert result.result == "exec-ok"

    # The critical assertion: _sandbox MUST have been injected even
    # though sandbox_type is NONE.
    call_kwargs = mock_tool.execute.call_args.kwargs
    assert "_sandbox" in call_kwargs, (
        "BUG: orchestrator did NOT inject _sandbox for exec tool "
        "when sandbox_type is NONE.  ExecTool will fall back to the "
        "legacy path and make independent sandbox decisions."
    )
    assert call_kwargs["_sandbox"] is none_selection
    assert call_kwargs["_sandbox"].sandbox_type == SandboxType.NONE


@pytest.mark.asyncio
async def test_non_exec_tool_none_sandbox_not_injected(
    orchestrator, mock_components,
):
    """For non-exec tools, _sandbox with NONE is NOT injected — preserving
    existing behavior for tools that don't consume sandbox selection."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )
    mock_components["sandbox_engine"].select.return_value = SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        reason="test",
    )

    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="read-ok")
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(tool_name="read_file", arguments={"path": "test.txt"})
    result = await orchestrator.execute(ctx)

    assert result.result == "read-ok"
    # For read_file with NONE sandbox, _sandbox should NOT be injected
    call_kwargs = mock_tool.execute.call_args.kwargs
    assert "_sandbox" not in call_kwargs


@pytest.mark.asyncio
async def test_non_exec_tool_bwrap_sandbox_still_injected(
    orchestrator, mock_components,
):
    """For non-exec tools with BWRAP sandbox, _sandbox is still injected
    (existing behavior preserved)."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )
    mock_components["sandbox_engine"].select.return_value = SandboxSelection(
        sandbox_type=SandboxType.BWRAP,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        reason="test",
    )

    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="write-ok")
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(tool_name="write_file", arguments={"path": "test.txt"})
    result = await orchestrator.execute(ctx)

    assert result.result == "write-ok"
    call_kwargs = mock_tool.execute.call_args.kwargs
    assert "_sandbox" in call_kwargs
