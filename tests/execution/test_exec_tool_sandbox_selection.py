"""Tests for Phase 31.2: ExecTool consumes SandboxSelection from ToolOrchestrator.

These tests verify that ExecTool no longer makes independent sandbox decisions
and instead follows the SandboxSelection injected by ToolOrchestrator.
"""

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
async def test_sandbox_selection_none_overrides_active_sandbox():
    """Phase 31.2b blocker: when orchestrator passes _sandbox=NONE,
    ExecTool MUST do direct execution — even if an active sandbox_manager
    with a running sandbox exists.  The orchestrator's SandboxSelection
    is the single source of truth; ExecTool must not second-guess it."""
    mock_sandbox = _make_mock_sandbox(is_running=True)
    mock_mgr = _make_mock_sandbox_manager(active_sandbox=mock_sandbox)

    tool = ExecTool(timeout=5, sandbox_manager=mock_mgr)
    sel = _make_selection(SandboxType.NONE)

    result = await tool.execute(
        "python -c \"print('direct-not-sandbox')\"",
        _sandbox=sel,
    )

    assert "direct-not-sandbox" in result
    # The sandbox must NOT have been used — orchestrator said NONE.
    mock_sandbox.run_command.assert_not_called()


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
async def test_sandbox_selection_restricted_allows_direct(tmp_path):
    """RESTRICTED sandbox type allows direct execution with enforcement
    when cwd is within workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "python -c \"print('restricted-ok')\"",
        _sandbox=sel,
        working_dir=str(tmp_path),
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


# ── 31.3: SandboxSelection.timeout_ms enforcement ──────────────────────

@pytest.mark.asyncio
async def test_sandbox_selection_timeout_ms_consumed():
    """SandboxSelection.timeout_ms must be used as the actual exec timeout."""
    tool = ExecTool(timeout=60)  # Default 60s — would NOT timeout normally
    sel = _make_selection(SandboxType.NONE, timeout_ms=50)  # 50ms timeout

    result = await tool.execute(
        "python -c \"import time; time.sleep(10)\"",
        _sandbox=sel,
    )

    assert "timed out" in result.lower()


@pytest.mark.asyncio
async def test_sandbox_selection_timeout_ms_not_exceeded():
    """When timeout_ms is long enough, command completes normally."""
    tool = ExecTool(timeout=1)  # 1s default — too short for slow commands
    sel = _make_selection(SandboxType.NONE, timeout_ms=30_000)  # 30s from selection

    result = await tool.execute(
        "python -c \"print('completed')\"",
        _sandbox=sel,
    )

    assert "completed" in result
    assert "timed out" not in result.lower()


# ── 31.3: SandboxSelection.env_passthrough enforcement ─────────────────

@pytest.mark.asyncio
async def test_sandbox_selection_env_passthrough_consumed():
    """SandboxSelection.env_passthrough must allow otherwise-filtered env vars."""
    import os

    test_var = "_MIQI_PHASE31_ENV_TEST_313"
    os.environ[test_var] = "phase31-env-value"
    try:
        tool = ExecTool(timeout=5)

        # Without env_passthrough → the var should still be present
        # (it doesn't match any sensitive pattern)
        sel_no_passthrough = _make_selection(SandboxType.NONE)
        result_no = await tool.execute(
            f"python -c \"import os; print(os.environ.get('{test_var}', 'MISSING'))\"",
            _sandbox=sel_no_passthrough,
        )
        assert "phase31-env-value" in result_no

        # With env_passthrough containing the var → also present
        sel_with = _make_selection(
            SandboxType.NONE, env_passthrough=[test_var],
        )
        result_with = await tool.execute(
            f"python -c \"import os; print(os.environ.get('{test_var}', 'MISSING'))\"",
            _sandbox=sel_with,
        )
        assert "phase31-env-value" in result_with
    finally:
        os.environ.pop(test_var, None)


@pytest.mark.asyncio
async def test_sandbox_selection_env_passthrough_overrides_filter():
    """env_passthrough from SandboxSelection must bypass the credential filter."""
    import os

    # Use a var name that WOULD be filtered by _build_safe_env
    # (starts with a sensitive prefix like OPENAI_)
    test_var = "OPENAI_MIQI_TEST_313"
    os.environ[test_var] = "bypass-value"
    try:
        tool = ExecTool(timeout=5)

        # Without env_passthrough → filtered out (default behavior)
        sel_default = _make_selection(SandboxType.NONE)
        result_default = await tool.execute(
            f"python -c \"import os; print(os.environ.get('{test_var}', 'MISSING'))\"",
            _sandbox=sel_default,
        )
        assert "MISSING" in result_default, (
            f"Expected var to be filtered, got: {result_default!r}"
        )

        # With env_passthrough → must be present
        sel_passthrough = _make_selection(
            SandboxType.NONE, env_passthrough=[test_var],
        )
        result_passthrough = await tool.execute(
            f"python -c \"import os; print(os.environ.get('{test_var}', 'MISSING'))\"",
            _sandbox=sel_passthrough,
        )
        assert "bypass-value" in result_passthrough, (
            f"Expected var to be present via env_passthrough, got: {result_passthrough!r}"
        )
    finally:
        os.environ.pop(test_var, None)


# ── 31.3: RESTRICTED enforcement ───────────────────────────────────────

@pytest.mark.asyncio
async def test_restricted_cwd_outside_workspace_fails(tmp_path):
    """RESTRICTED with cwd outside workspace must fail closed."""
    tool = ExecTool(
        timeout=5,
        working_dir=str(tmp_path),
        restrict_to_workspace=True,
    )
    sel = _make_selection(SandboxType.RESTRICTED)

    # Use a cwd outside the workspace (parent of tmp_path)
    outside_dir = str(tmp_path.parent)

    result = await tool.execute(
        "echo should-not-run",
        working_dir=outside_dir,
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside" in result.lower() or "workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_cwd_within_workspace_succeeds(tmp_path):
    """RESTRICTED with cwd inside workspace must succeed."""
    tool = ExecTool(
        timeout=5,
        working_dir=str(tmp_path),
        restrict_to_workspace=True,
    )
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "python -c \"print('within-workspace')\"",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "within-workspace" in result


# ── 31.3: SandboxSelection policy metadata presence ────────────────────

def test_sandbox_selection_includes_filesystem_policy():
    """SandboxSelection.filesystem_policy must be populated."""
    sel = _make_selection(SandboxType.BWRAP)
    assert sel.filesystem_policy is not None
    assert sel.filesystem_policy.default_mode == FileSystemAccessMode.READ


def test_sandbox_selection_includes_network_policy():
    """SandboxSelection.network_policy must be populated."""
    sel = _make_selection(SandboxType.RESTRICTED)
    assert sel.network_policy == NetworkSandboxPolicy.ALLOW_ALL


def test_sandbox_selection_includes_timeout_ms():
    """SandboxSelection.timeout_ms must be populated."""
    sel = _make_selection(SandboxType.NONE, timeout_ms=45_000)
    assert sel.timeout_ms == 45_000


def test_sandbox_selection_includes_env_passthrough():
    """SandboxSelection.env_passthrough must be populated."""
    sel = _make_selection(SandboxType.NONE, env_passthrough=["PATH", "HOME"])
    assert "PATH" in sel.env_passthrough
    assert "HOME" in sel.env_passthrough


# ── 31.3: SandboxPolicyEngine allow_fallback_to_none ───────────────────

@pytest.mark.asyncio
async def test_sandbox_policy_no_fallback_fails_on_exhaustion():
    """SandboxPolicyEngine with allow_fallback_to_none=False raises SandboxDeniedError."""
    from miqi.execution.sandbox_policy import (
        SandboxPolicyEngine,
        SandboxDeniedError,
    )

    engine = SandboxPolicyEngine(
        bwrap_available=True,
        allow_fallback_to_none=False,
    )

    class FakeCtx:
        tool_name = "exec"
        arguments = {"command": "npm test"}

    # After exhausting all sandbox types (BWRAP→LANDLOCK→RESTRICTED→NONE),
    # the next attempt should raise SandboxDeniedError
    with pytest.raises(SandboxDeniedError):
        await engine.select(FakeCtx(), attempt=4)


# ── 31.3: PermissionProfile fields in SandboxSelection path ────────────

@pytest.mark.asyncio
async def test_permission_profile_filesystem_mode_in_sandbox_selection():
    """When PermissionProfile has filesystem_mode, it should be reflected
    in or at least compatible with the SandboxSelection."""
    from miqi.runtime.permission_profile import PermissionProfile
    from miqi.execution.sandbox_policy import SandboxPolicyEngine

    profile = PermissionProfile(
        workspace=None,  # type: ignore
        filesystem_mode="workspace-readonly",
        network_allowed=False,
    )

    engine = SandboxPolicyEngine()

    class FakeCtx:
        tool_name = "write_file"
        arguments = {"path": "test.txt"}
        permission_profile = profile

    sel = await engine.select(FakeCtx())
    # The selection exists with a valid type
    assert sel.sandbox_type is not None
    assert sel.filesystem_policy is not None
    assert sel.network_policy is not None


# ═══════════════════════════════════════════════════════════════════════════
# Phase 33.3: RESTRICTED policy enforcement — cwd
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_restricted_cwd_enforced_even_without_restrict_config(tmp_path):
    """RESTRICTED must reject cwd outside workspace even when
    restrict_to_workspace=False."""
    tool = ExecTool(
        timeout=5,
        working_dir=str(tmp_path),
        restrict_to_workspace=False,  # ← disabled, but RESTRICTED ignores it
    )
    sel = _make_selection(SandboxType.RESTRICTED)
    outside_dir = str(tmp_path.parent)

    result = await tool.execute(
        "echo should-not-run",
        working_dir=outside_dir,
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside" in result.lower() or "workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_cwd_inside_workspace_allows_safe_command(tmp_path):
    """RESTRICTED with cwd inside workspace must allow a simple safe command."""
    tool = ExecTool(
        timeout=5,
        working_dir=str(tmp_path),
        restrict_to_workspace=True,
    )
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "python -c \"print('safe-command-ok')\"",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "safe-command-ok" in result


@pytest.mark.asyncio
async def test_restricted_no_working_dir_fails_closed():
    """RESTRICTED without a configured working_dir must fail closed."""
    tool = ExecTool(timeout=5, working_dir=None)
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "echo should-not-run",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "workspace" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 33.3: RESTRICTED policy enforcement — file paths
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_restricted_rejects_outside_windows_absolute_path(tmp_path):
    """RESTRICTED must reject commands referencing Windows absolute paths
    outside the workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    outside = str(tmp_path.parent / "outside.txt")
    result = await tool.execute(
        f"type {outside}",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_outside_posix_absolute_path(tmp_path):
    """RESTRICTED must reject commands with POSIX absolute paths
    (/etc/passwd, /tmp/x) which are outside the workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "cat /etc/passwd",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_wsl_absolute_path(tmp_path):
    """RESTRICTED must reject /mnt/c/... paths outside workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "cat /mnt/c/Windows/System32/drivers/etc/hosts",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_allows_workspace_relative_path(tmp_path):
    """RESTRICTED must allow relative paths that stay inside workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    # Create a test file inside workspace
    test_file = tmp_path / "test.txt"
    test_file.write_text("hello-workspace")

    result = await tool.execute(
        "python -c \"print(open('test.txt').read())\"",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "hello-workspace" in result


@pytest.mark.asyncio
async def test_restricted_allows_inside_workspace_absolute_path(tmp_path):
    """RESTRICTED must allow Windows absolute paths that stay inside
    workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    test_file = tmp_path / "inside.txt"
    test_file.write_text("inside-workspace")

    result = await tool.execute(
        f"python -c \"print(open(r'{test_file}').read())\"",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "inside-workspace" in result


@pytest.mark.asyncio
async def test_restricted_rejects_traversal_path(tmp_path):
    """RESTRICTED must reject commands using ../ traversal."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "type ..\\..\\Windows\\System32\\drivers\\etc\\hosts",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_redirect_to_outside(tmp_path):
    """RESTRICTED must reject redirect that writes outside workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)
    outside = str(tmp_path.parent / "out.txt")

    result = await tool.execute(
        f"echo data > {outside}",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_append_redirect_to_outside(tmp_path):
    """RESTRICTED must reject append redirect outside workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)
    outside = str(tmp_path.parent / "append.txt")

    result = await tool.execute(
        f"echo more >> {outside}",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_input_redirect_from_outside(tmp_path):
    """RESTRICTED must reject input redirect from outside workspace."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)
    outside = str(tmp_path.parent / "input.txt")

    result = await tool.execute(
        f"sort < {outside}",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


# ═══════════════════════════════════════════════════════════════════════════
# Phase 33.3: RESTRICTED policy enforcement — network
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_restricted_network_block_all_fails_closed(tmp_path):
    """RESTRICTED with BLOCK_ALL network policy must fail closed —
    direct host execution cannot enforce network isolation."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    from miqi.protocol.permissions import NetworkSandboxPolicy as NSP

    sel = _make_selection(SandboxType.RESTRICTED)
    sel.network_policy = NSP.BLOCK_ALL  # type: ignore[assignment]

    result = await tool.execute(
        "python -c \"print('should-not-run')\"",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "network" in result.lower()


@pytest.mark.asyncio
async def test_restricted_network_allow_all_proceeds(tmp_path):
    """RESTRICTED with ALLOW_ALL network policy must proceed."""
    from miqi.protocol.permissions import NetworkSandboxPolicy as NSP

    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)
    sel.network_policy = NSP.ALLOW_ALL  # type: ignore[assignment]

    result = await tool.execute(
        "python -c \"print('network-allowed')\"",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "network-allowed" in result


# ═══════════════════════════════════════════════════════════════════════════
# Phase 33.3: SandboxPolicyEngine RESTRICTED network default
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_engine_restricted_exec_defaults_to_block_all():
    """SandboxPolicyEngine defaults RESTRICTED exec network_policy to
    BLOCK_ALL when permission_profile has network_allowed=False."""
    from miqi.execution.sandbox_policy import SandboxPolicyEngine
    from miqi.runtime.permission_profile import PermissionProfile

    engine = SandboxPolicyEngine(bwrap_available=False, landlock_available=False)

    profile = PermissionProfile(
        workspace=None,  # type: ignore
        network_allowed=False,
    )

    class FakeCtx:
        tool_name = "exec"
        arguments = {"command": "curl example.com"}
        permission_profile = profile

    sel = await engine.select(FakeCtx())
    # Engine selected RESTRICTED (no bwrap, no landlock)
    assert sel.sandbox_type == SandboxType.RESTRICTED
    # Network should be BLOCK_ALL by default
    assert sel.network_policy == "block_all"


@pytest.mark.asyncio
async def test_engine_restricted_exec_network_allowed_overrides_to_allow_all():
    """When permission_profile.network_allowed=True, RESTRICTED exec
    keeps ALLOW_ALL network policy."""
    from miqi.execution.sandbox_policy import SandboxPolicyEngine
    from miqi.runtime.permission_profile import PermissionProfile

    engine = SandboxPolicyEngine(bwrap_available=False, landlock_available=False)

    profile = PermissionProfile(
        workspace=None,  # type: ignore
        network_allowed=True,
    )

    class FakeCtx:
        tool_name = "exec"
        arguments = {"command": "curl example.com"}
        permission_profile = profile

    sel = await engine.select(FakeCtx())
    assert sel.sandbox_type == SandboxType.RESTRICTED
    assert sel.network_policy == "allow_all"


# ═══════════════════════════════════════════════════════════════════════════
# Phase 33.3: event integrity — RESTRICTED failure
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_restricted_fail_produces_no_output_delta_events(tmp_path):
    """When RESTRICTED fails closed (e.g. cwd outside workspace), no
    ExecCommandOutputDeltaEvent should be emitted — the command never
    ran."""
    from miqi.protocol.events import ExecCommandOutputDeltaEvent

    emitter = _EventCollector()
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)
    outside_dir = str(tmp_path.parent)

    result = await tool.execute(
        "echo should-not-run",
        working_dir=outside_dir,
        _event_emitter=emitter,
        _turn_id="t-fail",
        _tool_call_id="c-fail",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    deltas = [
        e for e in emitter.events
        if isinstance(e, ExecCommandOutputDeltaEvent)
    ]
    assert len(deltas) == 0, (
        f"Expected 0 output delta events for failed command, got {len(deltas)}"
    )


@pytest.mark.asyncio
async def test_restricted_fail_still_emits_begin_and_end_events(tmp_path):
    """When RESTRICTED fails closed, begin + end events must still be
    emitted so the frontend can see the command was attempted and
    rejected."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)
    outside_dir = str(tmp_path.parent)

    await tool.execute(
        "echo should-not-run",
        working_dir=outside_dir,
        _event_emitter=emitter,
        _turn_id="t-fail2",
        _tool_call_id="c-fail2",
        _sandbox=sel,
    )

    begin_events = [e for e in emitter.events
                    if isinstance(e, ExecCommandBeginEvent)]
    end_events = [e for e in emitter.events
                  if isinstance(e, ExecCommandEndEvent)]
    assert len(begin_events) == 1
    assert len(end_events) == 1
    assert begin_events[0].sandbox_type == "restricted"
    # Exit code must be non-zero on failure
    assert end_events[0].exit_code != 0


# ═══════════════════════════════════════════════════════════════════════════
# Phase 33.3: regression — NONE / BWRAP / LANDLOCK unchanged
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_none_path_unaffected_by_restricted_changes(tmp_path):
    """NONE sandbox type must still allow direct execution of any
    command (Phase 33.3 changes should not affect NONE path)."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.NONE)
    outside_dir = str(tmp_path.parent)

    result = await tool.execute(
        "python -c \"print('none-ok')\"",
        working_dir=outside_dir,  # outside workspace — NONE allows it
        _sandbox=sel,
    )

    assert "none-ok" in result


@pytest.mark.asyncio
async def test_bwrap_unavailable_fail_closed_unchanged():
    """Regression: BWRAP selection with no active sandbox still fails
    closed (Phase 31 test)."""
    tool = ExecTool(timeout=5, sandbox_manager=None)
    sel = _make_selection(SandboxType.BWRAP)

    result = await tool.execute(
        "echo should-not-run",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "BWRAP sandbox" in result


@pytest.mark.asyncio
async def test_landlock_unsupported_fail_closed_unchanged():
    """Regression: LANDLOCK selection still fails closed (Phase 31 test)."""
    tool = ExecTool(timeout=5)
    sel = _make_selection(SandboxType.LANDLOCK)

    result = await tool.execute(
        "echo should-not-run",
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "LANDLOCK" in result


# ═══════════════════════════════════════════════════════════════════════════
# Phase 33.3-REVIEW: shell variable / tilde expansion bypass detection
# ═══════════════════════════════════════════════════════════════════════════


@pytest.mark.asyncio
async def test_restricted_rejects_shell_var_with_path(tmp_path):
    """$VAR/path is statically unknowable — must be rejected as unsafe."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "cat $HOME/.ssh/id_rsa",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_braced_shell_var_with_path(tmp_path):
    """${VAR}/path is statically unknowable — must be rejected."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "cat ${HOME}/.ssh/id_rsa",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_tilde_expansion(tmp_path):
    """~/path expands to home dir outside workspace — must be rejected."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "cat ~/outside_file.txt",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_tilde_user_expansion(tmp_path):
    """~user/path expands to another user's home — must be rejected."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "cat ~root/.bashrc",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()


@pytest.mark.asyncio
async def test_restricted_rejects_shell_var_with_traversal(tmp_path):
    """$UNKNOWN_VAR/../../../etc/passwd — shell var + traversal, must reject."""
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))
    sel = _make_selection(SandboxType.RESTRICTED)

    result = await tool.execute(
        "cat $UNKNOWN_VAR/../../../etc/passwd",
        working_dir=str(tmp_path),
        _sandbox=sel,
    )

    assert "NOT executed" in result
    assert "outside workspace" in result.lower()
