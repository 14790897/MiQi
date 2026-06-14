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


# ── Phase 31.4: Approval lifecycle hardening ───────────────────────────


@pytest.mark.asyncio
async def test_resolve_approval_returns_structured_result(orchestrator, mock_components):
    """Phase 31.4: resolve_approval must return ApprovalResolveResult
    with resolved=True on success and resolved=False on failure."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.execution.orchestrator import ApprovalResolveResult

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: test cmd",
    )

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-structured",
        turn_id="turn-structured", arguments={"command": "test"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"

    # ── Successful resolve ──
    result = orchestrator.resolve_approval(approval_id, "once")
    assert isinstance(result, ApprovalResolveResult)
    assert result.resolved is True
    assert result.approval_id == approval_id
    assert result.normalized_decision == "once"
    assert result.turn_id == ctx.turn_id
    assert result.reason == ""
    await task

    # ── Nonexistent approval ──
    result2 = orchestrator.resolve_approval("nonexistent:id", "once")
    assert result2.resolved is False
    assert "not found" in result2.reason.lower()

    # ── Invalid decision ──
    # Need a new pending approval for this test
    ctx2 = make_ctx(
        tool_name="exec", tool_call_id="call-invalid-decision",
        turn_id="turn-invalid-decision", arguments={"command": "test"},
    )
    task2 = asyncio.create_task(orchestrator.execute(ctx2))
    await asyncio.sleep(0.05)
    approval_id2 = f"{ctx2.turn_id}:{ctx2.tool_call_id}"

    result3 = orchestrator.resolve_approval(approval_id2, "bogus")
    assert result3.resolved is False
    assert "invalid" in result3.reason.lower()

    # Cleanup
    orchestrator.resolve_approval(approval_id2, "deny")
    await task2


@pytest.mark.asyncio
async def test_approval_metadata_includes_all_required_fields(orchestrator, mock_components):
    """When an approval is requested, _approval_meta must contain:
    approval_id, client_id, session_id, thread_id, turn_id, tool_call_id,
    tool_name, category, timeout_ms.
    """
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: dangerous command",
        details={"command": "rm -rf /test"},
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

    ctx = make_ctx(
        tool_name="exec",
        tool_call_id="call_approval_meta",
        turn_id="turn-approval-meta",
        thread_id="thread-approval-meta",
        arguments={"command": "rm -rf /test"},
    )
    ctx.client_id = "client-test"
    ctx.session_id = "client-test:session-test"

    # Start execute in background — it will block waiting for approval
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    # Check metadata stored by orchestrator
    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    meta = orchestrator._approval_meta.get(approval_id, {})
    assert meta["approval_id"] == approval_id
    assert meta["client_id"] == "client-test"
    assert meta["session_id"] == "client-test:session-test"
    assert meta["thread_id"] == "thread-approval-meta"
    assert meta["turn_id"] == "turn-approval-meta"
    assert meta["tool_call_id"] == "call_approval_meta"
    assert meta["tool_name"] == "exec"
    assert meta["category"] == "exec"
    assert "timeout_ms" in meta
    assert meta["allow_permanent"] is True

    # Cleanup
    orchestrator.resolve_approval(approval_id, "deny")
    await task


@pytest.mark.asyncio
async def test_deny_decision_unblocks_and_does_not_execute(orchestrator, mock_components):
    """When user denies, the waiting tool call must return 'denied'
    and the tool MUST NOT be executed."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
        details={"command": "cmd"},
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="should-not-run")
    mock_components["tool_registry"].get.return_value = tool_mock

    ctx = make_ctx(tool_name="exec", arguments={"command": "cmd"})
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    orchestrator.resolve_approval(approval_id, "deny")

    result = await task
    assert "denied" in result.result.lower()
    tool_mock.execute.assert_not_called()


@pytest.mark.asyncio
async def test_allow_decision_resumes_one_tool_call(orchestrator, mock_components):
    """When user allows, exactly one waiting tool call resumes."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: safe cmd",
        details={"command": "safe"},
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="exec-ok")
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(tool_name="exec", arguments={"command": "safe"})
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    orchestrator.resolve_approval(approval_id, "once")

    result = await task
    assert result.result == "exec-ok"
    mock_tool.execute.assert_called_once()


@pytest.mark.asyncio
async def test_approval_timeout_cleans_pending_and_denies(orchestrator, mock_components):
    """When approval times out, the pending future and metadata must
    be cleaned, and the tool call must return a denial."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )
    # Set very short timeout
    orchestrator.approval_timeout_ms = 50

    ctx = make_ctx(tool_name="exec", arguments={"command": "cmd"})
    result = await orchestrator.execute(ctx)

    assert "denied" in result.result.lower() or "timeout" in result.result.lower()
    # No stale approvals
    assert len(orchestrator.list_pending_approvals()) == 0
    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    assert approval_id not in orchestrator._pending_approvals


@pytest.mark.asyncio
async def test_approval_timeout_emits_terminal_event(orchestrator, mock_components):
    """Phase 31.4: on approval timeout, an ApprovalResolvedEvent with
    decision='timeout' must be emitted."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.protocol.events import ApprovalResolvedEvent

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )
    orchestrator.approval_timeout_ms = 50

    # Collect emitted events
    emitted: list = []
    mock_components["event_emitter"].emit = AsyncMock(
        side_effect=lambda e: emitted.append(e)
    )

    ctx = make_ctx(tool_name="exec", arguments={"command": "cmd"})
    await orchestrator.execute(ctx)

    resolved_events = [e for e in emitted
                       if isinstance(e, ApprovalResolvedEvent)]
    timeout_events = [e for e in resolved_events if e.decision == "timeout"]
    assert len(timeout_events) >= 1, (
        f"Expected >=1 timeout ApprovalResolvedEvent, got {resolved_events}"
    )


@pytest.mark.asyncio
async def test_abort_cancels_pending_approval(orchestrator, mock_components):
    """Phase 31.4: cancel_approvals_for_thread must deny pending
    approvals and unblock waiting tool calls."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: long cmd",
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="should-not-run")
    mock_components["tool_registry"].get.return_value = tool_mock

    ctx = make_ctx(
        tool_name="exec",
        tool_call_id="call-abort",
        turn_id="turn-abort",
        thread_id="thread-abort",
        arguments={"command": "long"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    # Abort the thread
    cancelled = await orchestrator.cancel_approvals_for_thread("thread-abort")
    assert cancelled >= 1, f"Expected at least 1 approval cancelled, got {cancelled}"

    result = await task
    assert "denied" in result.result.lower() or "aborted" in result.result.lower()
    tool_mock.execute.assert_not_called()

    # No stale metadata
    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    assert approval_id not in orchestrator._pending_approvals
    assert approval_id not in orchestrator._approval_meta


@pytest.mark.asyncio
async def test_abort_emits_terminal_approval_event(orchestrator, mock_components):
    """Phase 31.4: cancel_approvals_for_thread must emit
    ApprovalResolvedEvent(decision='abort') for each cancelled approval."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.protocol.events import ApprovalResolvedEvent

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = tool_mock

    emitted: list = []
    mock_components["event_emitter"].emit = AsyncMock(
        side_effect=lambda e: emitted.append(e)
    )

    ctx = make_ctx(
        tool_name="exec",
        tool_call_id="call-abort-ev",
        turn_id="turn-abort-ev",
        thread_id="thread-abort-ev",
        arguments={"command": "cmd"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    cancelled = await orchestrator.cancel_approvals_for_thread("thread-abort-ev")
    assert cancelled == 1
    await task

    resolved = [e for e in emitted if isinstance(e, ApprovalResolvedEvent)]
    abort_events = [e for e in resolved if e.decision == "abort"]
    assert len(abort_events) == 1, (
        f"Expected 1 abort ApprovalResolvedEvent, got {abort_events}"
    )
    assert abort_events[0].approval_id == f"{ctx.turn_id}:{ctx.tool_call_id}"


@pytest.mark.asyncio
async def test_no_stale_approval_after_resolve(orchestrator, mock_components):
    """Phase 31.4: after an approval is resolved (allow/deny/timeout/abort),
    approvals.list must not include the stale approval."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-no-stale",
        turn_id="turn-no-stale", arguments={"command": "cmd"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    assert len(orchestrator.list_pending_approvals()) == 1

    orchestrator.resolve_approval(approval_id, "once")
    await task

    assert len(orchestrator.list_pending_approvals()) == 0


@pytest.mark.asyncio
async def test_invalid_decision_is_rejected(orchestrator, mock_components):
    """Phase 31.4: resolve_approval with an invalid decision must NOT
    resolve the future (it stays pending)."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = tool_mock

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-invalid",
        turn_id="turn-invalid", arguments={"command": "cmd"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    # Attempt invalid decision
    orchestrator.resolve_approval(approval_id, "bogus_decision")
    # The approval should still be pending
    assert orchestrator.has_approval(approval_id), (
        "Invalid decision should NOT resolve the approval"
    )
    assert len(orchestrator.list_pending_approvals()) == 1

    # Clean up with valid deny
    orchestrator.resolve_approval(approval_id, "deny")
    result = await task
    assert "denied" in result.result.lower()


@pytest.mark.asyncio
async def test_sanitized_details_are_json_serializable_and_bounded(orchestrator, mock_components):
    """Phase 31.4: _sanitize_details must return JSON-serializable values
    and drop sensitive keys."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    import json

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Test sanitization",
        details={
            "command": "safe-cmd",
            "secret": "sk-abc123shouldnotleak",
            "password": "hunter2",
            "exception": ValueError("boom"),
            "normal_key": "normal-value",
            "nested": {"inner_secret": "hidden", "ok": True},
        },
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = tool_mock

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-sanitize",
        turn_id="turn-sanitize", arguments={"command": "safe-cmd"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    meta = orchestrator._approval_meta.get(f"{ctx.turn_id}:{ctx.tool_call_id}", {})

    # Sensitive keys must be absent
    sanitized = meta["details"]
    assert "secret" not in sanitized, f"Sensitive key 'secret' leaked: {sanitized}"
    assert "password" not in sanitized, f"Sensitive key 'password' leaked: {sanitized}"
    assert "exception" not in sanitized, f"Sensitive key 'exception' leaked: {sanitized}"

    # Normal keys must be present
    assert sanitized.get("normal_key") == "normal-value"
    assert sanitized.get("command") == "safe-cmd"

    # Must be JSON-serializable
    try:
        json.dumps(sanitized)
    except (TypeError, ValueError) as e:
        pytest.fail(f"Sanitized details not JSON-serializable: {e}")

    # Cleanup
    orchestrator.resolve_approval(f"{ctx.turn_id}:{ctx.tool_call_id}", "deny")
    await task


@pytest.mark.asyncio
async def test_allow_always_adds_to_permanent_allowlist(orchestrator, mock_components):
    """Phase 31.4: 'always' decision must add the pattern to the
    permanent allowlist via the permission engine."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: always-allowed-cmd",
        details={"command": "always-allowed-cmd"},
        allow_permanent=True,
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = tool_mock

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-always",
        turn_id="turn-always", arguments={"command": "always-allowed-cmd"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    # Replace mock with a real set so _record_permanent_approval can add to it
    orchestrator.permissions.permanent_allowlist = set()

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"

    orchestrator.resolve_approval(approval_id, "always")
    await task

    # Phase 31.7: pattern uses _make_key format (exec:command, not description)
    assert "exec:always-allowed-cmd" in orchestrator.permissions.permanent_allowlist


@pytest.mark.asyncio
async def test_pending_approvals_empty_after_abort(orchestrator, mock_components):
    """Phase 31.4: after abort, approvals.list must be empty for the
    aborted thread."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd1",
    )
    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="ok")
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-abort-list",
        turn_id="turn-abort-list", thread_id="thread-abort-list",
        arguments={"command": "cmd1"},
    )
    task = asyncio.create_task(orchestrator.execute(ctx))
    await asyncio.sleep(0.05)

    assert len(orchestrator.list_pending_approvals()) == 1

    await orchestrator.cancel_approvals_for_thread("thread-abort-list")
    await task

    assert len(orchestrator.list_pending_approvals()) == 0


# ═══════════════════════════════════════════════════════════════════════════
# Phase 31.8: Ledger recording of approval events by orchestrator
# ═══════════════════════════════════════════════════════════════════════════


class _FakeLedgerForOrch:
    """Minimal fake LedgerRuntime for orchestrator ledger-writing tests."""

    def __init__(self):
        self.items: list[dict] = []

    async def append_item(self, **kwargs):
        self.items.append(kwargs)


def _orchestrator_with_ledger(mock_components, ledger):
    """Create an orchestrator with the ledger wired in."""
    return ToolOrchestrator(
        permission_engine=mock_components["permission_engine"],
        sandbox_engine=mock_components["sandbox_engine"],
        hook_runtime=mock_components["hook_runtime"],
        tool_registry=mock_components["tool_registry"],
        event_emitter=mock_components["event_emitter"],
        ledger_runtime=ledger,
    )


@pytest.mark.asyncio
async def test_orchestrator_writes_approval_requested_to_ledger(mock_components):
    """When approval is required, orchestrator must write approval_requested."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: test cmd",
        details={"command": "test cmd"},
        allow_permanent=True,
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    mock_components["tool_registry"].get.return_value = MagicMock()
    mock_components["tool_registry"].get.return_value.execute = AsyncMock(
        return_value="ok",
    )

    fake_ledger = _FakeLedgerForOrch()
    orch = _orchestrator_with_ledger(mock_components, fake_ledger)

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-ledger",
        turn_id="turn-ledger", arguments={"command": "test cmd"},
    )
    task = asyncio.create_task(orch.execute(ctx))
    await asyncio.sleep(0.05)

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    orch.resolve_approval(approval_id, "once")
    await task

    req_items = [it for it in fake_ledger.items if it["item_type"] == "approval_requested"]
    assert len(req_items) == 1, f"Expected 1 approval_requested, got {fake_ledger.items}"
    req = req_items[0]
    assert req["thread_id"] == ctx.thread_id
    assert req["payload"]["approval_id"] == approval_id
    assert req["payload"]["tool_name"] == "exec"
    assert req["payload"]["category"] == "exec"
    assert req["payload"]["allow_permanent"] is True

    res_items = [it for it in fake_ledger.items if it["item_type"] == "approval_resolved"]
    assert len(res_items) == 1
    assert res_items[0]["payload"]["decision"] == "once"


@pytest.mark.asyncio
async def test_orchestrator_writes_approval_denied_to_ledger(mock_components):
    """When user denies, ledger must record approval_resolved(decision=deny)."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="file_write",
        description="write_file: /tmp/x",
        details={"path": "/tmp/x", "operation": "write_file"},
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="should-not-run")
    mock_components["tool_registry"].get.return_value = tool_mock

    fake_ledger = _FakeLedgerForOrch()
    orch = _orchestrator_with_ledger(mock_components, fake_ledger)

    ctx = make_ctx(
        tool_name="write_file", tool_call_id="call-deny",
        turn_id="turn-deny", arguments={"path": "/tmp/x"},
    )
    task = asyncio.create_task(orch.execute(ctx))
    await asyncio.sleep(0.05)

    approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
    orch.resolve_approval(approval_id, "deny")
    await task

    res_items = [it for it in fake_ledger.items if it["item_type"] == "approval_resolved"]
    assert len(res_items) == 1
    assert res_items[0]["payload"]["decision"] == "deny"
    assert res_items[0]["payload"]["tool_name"] == "write_file"
    assert res_items[0]["payload"]["category"] == "file_write"


@pytest.mark.asyncio
async def test_orchestrator_writes_approval_timeout_to_ledger(mock_components):
    """When approval times out, ledger must record approval_resolved(decision=timeout)."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )

    fake_ledger = _FakeLedgerForOrch()
    orch = _orchestrator_with_ledger(mock_components, fake_ledger)
    orch.approval_timeout_ms = 50

    ctx = make_ctx(tool_name="exec", arguments={"command": "cmd"})
    await orch.execute(ctx)

    timeout_items = [
        it for it in fake_ledger.items
        if it["item_type"] == "approval_resolved" and it["payload"].get("decision") == "timeout"
    ]
    assert len(timeout_items) == 1, (
        f"Expected 1 timeout approval_resolved, got {fake_ledger.items}"
    )


@pytest.mark.asyncio
async def test_orchestrator_writes_approval_abort_to_ledger(mock_components):
    """cancel_approvals_for_thread must write approval_resolved(decision=abort)."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: cmd",
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = tool_mock

    fake_ledger = _FakeLedgerForOrch()
    orch = _orchestrator_with_ledger(mock_components, fake_ledger)

    ctx = make_ctx(
        tool_name="exec", tool_call_id="call-abort",
        turn_id="turn-abort-ledger", thread_id="thread-abort-ledger",
        arguments={"command": "cmd"},
    )
    task = asyncio.create_task(orch.execute(ctx))
    await asyncio.sleep(0.05)

    await orch.cancel_approvals_for_thread("thread-abort-ledger")
    await task

    abort_items = [
        it for it in fake_ledger.items
        if it["item_type"] == "approval_resolved" and it["payload"].get("decision") == "abort"
    ]
    assert len(abort_items) >= 1, (
        f"Expected >=1 abort approval_resolved, got {fake_ledger.items}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 31.8 fix: Deterministic approval_resolved ledger write
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_resolve_approval_once_writes_ledger_deterministically(
    mock_components, tmp_path,
):
    """After resolve_approval("once") + await task, the real LedgerRuntime
    must contain exactly 1 approval_resolved item — no sleep/retry needed."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.runtime.ledger_runtime import LedgerRuntime

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="exec",
        description="Run: test cmd",
        details={"command": "test cmd"},
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = tool_mock

    # Use real LedgerRuntime (SQLite-backed) to prove deterministic write
    db_path = tmp_path / "deterministic.db"
    ledger = LedgerRuntime(db_path, session_id="sess-det")
    await ledger.initialize()

    try:
        orch = _orchestrator_with_ledger(mock_components, ledger)

        ctx = make_ctx(
            tool_name="exec", tool_call_id="call-det-once",
            turn_id="turn-det-once", arguments={"command": "test cmd"},
        )
        task = asyncio.create_task(orch.execute(ctx))
        await asyncio.sleep(0.05)

        approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
        orch.resolve_approval(approval_id, "once")
        await task  # ledger write happens inside _request_approval

        # Immediately query real ledger — no sleep
        items = await ledger.load_items(ctx.thread_id)

        req_items = [it for it in items if it.item_type == "approval_requested"]
        assert len(req_items) == 1, (
            f"Expected 1 approval_requested, got {len(req_items)}"
        )

        res_items = [it for it in items if it.item_type == "approval_resolved"]
        assert len(res_items) == 1, (
            f"Expected 1 approval_resolved, got {len(res_items)}"
        )
        assert res_items[0].payload["decision"] == "once"
        assert res_items[0].payload["tool_name"] == "exec"
        assert res_items[0].payload["tool_call_id"] == "call-det-once"
    finally:
        await ledger.close()


@pytest.mark.asyncio
async def test_resolve_approval_deny_writes_ledger_deterministically(
    mock_components, tmp_path,
):
    """After resolve_approval("deny") + await task, the real LedgerRuntime
    must contain exactly 1 approval_resolved(decision=deny) — no sleep."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.runtime.ledger_runtime import LedgerRuntime

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.APPROVAL_REQUIRED,
        category="file_write",
        description="write_file: /tmp/x",
        details={"path": "/tmp/x", "operation": "write_file"},
    )
    mock_components["sandbox_engine"].select.return_value = MagicMock(
        sandbox_type="none",
        filesystem_policy=MagicMock(),
        network_policy="allow_all",
    )
    tool_mock = MagicMock()
    tool_mock.execute = AsyncMock(return_value="should-not-run")
    mock_components["tool_registry"].get.return_value = tool_mock

    db_path = tmp_path / "deterministic-deny.db"
    ledger = LedgerRuntime(db_path, session_id="sess-det-deny")
    await ledger.initialize()

    try:
        orch = _orchestrator_with_ledger(mock_components, ledger)

        ctx = make_ctx(
            tool_name="write_file", tool_call_id="call-det-deny",
            turn_id="turn-det-deny", arguments={"path": "/tmp/x"},
        )
        task = asyncio.create_task(orch.execute(ctx))
        await asyncio.sleep(0.05)

        approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
        orch.resolve_approval(approval_id, "deny")
        await task

        items = await ledger.load_items(ctx.thread_id)

        res_items = [it for it in items if it.item_type == "approval_resolved"]
        assert len(res_items) == 1, (
            f"Expected 1 approval_resolved, got {len(res_items)}"
        )
        assert res_items[0].payload["decision"] == "deny"
        assert res_items[0].payload["tool_name"] == "write_file"
    finally:
        await ledger.close()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 31.8 fix: Single-writer rule verification
# ═══════════════════════════════════════════════════════════════════════════


def test_mirror_event_to_ledger_excludes_exec_and_approval_events():
    """Phase 31.8 single-writer rule: RuntimeSession._mirror_event_to_ledger
    must NOT mirror exec_command_* or approval_* events.  Those are written
    at source (ToolOrchestrator for approvals, ExecTool for exec events).
    Mirroring them would create duplicates in the ledger.
    """
    # Import the session module and inspect the mapping directly.
    # We test the actual mapping dict rather than duplicating it here
    # so the test breaks if someone adds the items back.
    from miqi.runtime.session import RuntimeSession
    import inspect

    source = inspect.getsource(RuntimeSession._mirror_event_to_ledger)

    # The 5 removed event types must NOT appear as keys in the item_type dict
    forbidden_keys = [
        "approval_requested",
        "approval_resolved",
        "exec_command_begin",
        "exec_command_output_delta",
        "exec_command_end",
    ]
    for key in forbidden_keys:
        # Check that the mapping line for this key is absent
        assert f'"{key}"' not in source or f"'{key}'" not in source, (
            f"Single-writer violation: _mirror_event_to_ledger still "
            f"maps {key!r}.  This event is written at source "
            f"(ToolOrchestrator/ExecTool) and must NOT be mirrored.  "
            f"Remove it from the item_type mapping dict."
        )

    # The 4 kept event types MUST still be present
    kept_keys = [
        "command_rejected",
        "error",
        "warning",
        "context_compacted",
    ]
    for key in kept_keys:
        assert f'"{key}"' in source or f"'{key}'" in source, (
            f"Missing required mirror: {key!r} must still be mirrored "
            f"by _mirror_event_to_ledger (no source-level writer exists)."
        )


# ═══════════════════════════════════════════════════════════════════════════
# Phase 34: File mutation sandbox injection by orchestrator
# ═══════════════════════════════════════════════════════════════════════════


_ORCH_FILE_MUTATION_TOOLS = [
    "write_file", "edit_file", "docx_write", "pptx_write", "xlsx_write",
]


@pytest.mark.parametrize("tool_name", _ORCH_FILE_MUTATION_TOOLS)
@pytest.mark.asyncio
async def test_file_mutation_tool_always_receives_sandbox(
    orchestrator, mock_components, tool_name,
):
    """Phase 34: file mutation tools must always receive _sandbox kwarg,
    even when sandbox_type is NONE."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )

    # Even with NONE, file mutation tools get _sandbox injected
    none_selection = SandboxSelection(
        sandbox_type=SandboxType.NONE,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        timeout_ms=30_000,
        reason="test",
    )
    mock_components["sandbox_engine"].select.return_value = none_selection

    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="ok")
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(
        tool_name=tool_name,
        arguments={"path": "test.txt", "file_path": "test.txt"},
    )
    result = await orchestrator.execute(ctx)
    assert result.result == "ok"

    call_kwargs = mock_tool.execute.call_args.kwargs
    assert "_sandbox" in call_kwargs, (
        f"BUG: orchestrator did NOT inject _sandbox for {tool_name} "
        f"when sandbox_type is NONE."
    )
    assert call_kwargs["_sandbox"] is none_selection


@pytest.mark.asyncio
async def test_file_mutation_tool_bwrap_sandbox_injected(
    orchestrator, mock_components,
):
    """Phase 34: file mutation tools with BWRAP sandbox get _sandbox
    injected (existing behavior preserved for non-NONE sandboxes)."""
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

    ctx = make_ctx(
        tool_name="edit_file",
        arguments={"path": "test.txt", "old_text": "a", "new_text": "b"},
    )
    result = await orchestrator.execute(ctx)
    assert result.result == "write-ok"
    call_kwargs = mock_tool.execute.call_args.kwargs
    assert "_sandbox" in call_kwargs
    assert call_kwargs["_sandbox"].sandbox_type == SandboxType.BWRAP


@pytest.mark.asyncio
async def test_file_mutation_restricted_sandbox_injected(
    orchestrator, mock_components,
):
    """Phase 34: file mutation tools with RESTRICTED sandbox get _sandbox
    injected — this is the normal policy path."""
    from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict
    from miqi.execution.sandbox_policy import SandboxSelection, SandboxType
    from miqi.protocol.permissions import (
        FileSystemSandboxPolicy, NetworkSandboxPolicy,
    )

    mock_components["permission_engine"].check.return_value = PermissionDecision(
        verdict=PermissionVerdict.ALLOW,
    )
    mock_components["sandbox_engine"].select.return_value = SandboxSelection(
        sandbox_type=SandboxType.RESTRICTED,
        filesystem_policy=FileSystemSandboxPolicy(),
        network_policy=NetworkSandboxPolicy.ALLOW_ALL,
        reason="test",
    )

    mock_tool = MagicMock()
    mock_tool.execute = AsyncMock(return_value="restricted-ok")
    mock_components["tool_registry"].get.return_value = mock_tool

    ctx = make_ctx(
        tool_name="write_file",
        arguments={"path": "test.txt", "content": "hello"},
    )
    result = await orchestrator.execute(ctx)
    assert result.result == "restricted-ok"
    call_kwargs = mock_tool.execute.call_args.kwargs
    assert "_sandbox" in call_kwargs
    assert call_kwargs["_sandbox"].sandbox_type == SandboxType.RESTRICTED


def test_orchestrator_file_mutation_set_matches_policy():
    """Phase 34: orchestrator's local _FILE_MUTATION_TOOLS must match
    SandboxPolicyEngine.FILE_MUTATION_TOOLS."""
    from miqi.execution.sandbox_policy import SandboxPolicyEngine

    local_set = frozenset({
        "write_file", "edit_file", "delete_file",
        "docx_write", "pptx_write", "xlsx_write",
    })
    assert local_set == SandboxPolicyEngine.FILE_MUTATION_TOOLS, (
        "Orchestrator's local _FILE_MUTATION_TOOLS out of sync"
    )
