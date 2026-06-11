"""Tests for permission profile exec/network rules (Phase 21)."""

import pytest

from miqi.execution.orchestrator import ToolExecutionContext
from miqi.execution.permission_engine import PermissionEngine, PermissionVerdict
from miqi.runtime.permission_profile import PermissionProfile


@pytest.mark.asyncio
async def test_permission_profile_allows_prefix_rule(tmp_path):
    """An exec command matching an allow prefix rule should be ALLOWed."""
    engine = PermissionEngine()
    ctx = ToolExecutionContext(
        tool_name="exec",
        tool_call_id="tc-1",
        arguments={"command": "git status --short"},
        turn_id="turn-1",
        thread_id="thread-1",
        agent_type="main",
        permission_profile=PermissionProfile(
            workspace=tmp_path,
            exec_allow_prefixes=[["git", "status"]],
        ),
    )

    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.ALLOW, (
        f"Expected ALLOW, got {decision.verdict}: {decision.reason}"
    )


@pytest.mark.asyncio
async def test_permission_profile_denies_prefix_rule(tmp_path):
    """An exec command matching a deny prefix rule should be DENYed.
    Deny takes priority over allow."""
    engine = PermissionEngine()
    ctx = ToolExecutionContext(
        tool_name="exec",
        tool_call_id="tc-1",
        arguments={"command": "rm -rf /tmp/foo"},
        turn_id="turn-1",
        thread_id="thread-1",
        agent_type="main",
        permission_profile=PermissionProfile(
            workspace=tmp_path,
            exec_deny_prefixes=[["rm", "-rf"]],
            exec_allow_prefixes=[["rm", "-rf"]],  # allow should NOT win
        ),
    )

    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.DENY, (
        f"Expected DENY, got {decision.verdict}: {decision.reason}"
    )
    assert "Denied by permission profile" in decision.reason


@pytest.mark.asyncio
async def test_permission_profile_unmatched_command_falls_through(tmp_path):
    """A command that doesn't match any prefix rule should fall through
    to the normal safe-command / approval-required logic."""
    engine = PermissionEngine()
    ctx = ToolExecutionContext(
        tool_name="exec",
        tool_call_id="tc-1",
        arguments={"command": "echo hello"},
        turn_id="turn-1",
        thread_id="thread-1",
        agent_type="main",
        permission_profile=PermissionProfile(
            workspace=tmp_path,
            exec_allow_prefixes=[["git"]],
        ),
    )

    decision = await engine.check(ctx)
    # "echo" is a safe command prefix → ALLOW
    assert decision.verdict == PermissionVerdict.ALLOW
