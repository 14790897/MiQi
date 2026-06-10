"""Tests for miqi.execution.sandbox_policy."""

import pytest
from miqi.execution.sandbox_policy import (
    SandboxPolicyEngine,
    SandboxSelection,
    SandboxType,
    SandboxDeniedError,
)
from miqi.protocol.permissions import (
    FileSystemAccessMode,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
)


class FakeContext:
    def __init__(self, tool_name, arguments=None):
        self.tool_name = tool_name
        self.arguments = arguments or {}


@pytest.mark.asyncio
async def test_read_only_tools_no_sandbox():
    engine = SandboxPolicyEngine()
    ctx = FakeContext("read_file", {"path": "test.py"})
    selection = await engine.select(ctx)
    assert selection.sandbox_type == SandboxType.NONE
    assert selection.reason


@pytest.mark.asyncio
async def test_exec_tool_prefers_bwrap():
    engine = SandboxPolicyEngine(bwrap_available=True)
    ctx = FakeContext("exec", {"command": "npm test"})
    selection = await engine.select(ctx)
    assert selection.sandbox_type == SandboxType.BWRAP


@pytest.mark.asyncio
async def test_exec_tool_falls_back_to_landlock():
    engine = SandboxPolicyEngine(bwrap_available=False, landlock_available=True)
    ctx = FakeContext("exec", {"command": "npm test"})
    selection = await engine.select(ctx)
    assert selection.sandbox_type == SandboxType.LANDLOCK


@pytest.mark.asyncio
async def test_exec_tool_falls_back_to_restricted():
    engine = SandboxPolicyEngine(bwrap_available=False, landlock_available=False)
    ctx = FakeContext("exec", {"command": "npm test"})
    selection = await engine.select(ctx)
    assert selection.sandbox_type == SandboxType.RESTRICTED


@pytest.mark.asyncio
async def test_escalation_on_retry():
    engine = SandboxPolicyEngine(bwrap_available=True)
    ctx = FakeContext("exec", {"command": "npm test"})
    # Attempt 0 → bwrap
    s0 = await engine.select(ctx, attempt=0)
    assert s0.sandbox_type == SandboxType.BWRAP
    # Attempt 1 → landlock (escalated)
    s1 = await engine.select(ctx, attempt=1)
    assert s1.sandbox_type == SandboxType.LANDLOCK
    # Attempt 2 → restricted
    s2 = await engine.select(ctx, attempt=2)
    assert s2.sandbox_type == SandboxType.RESTRICTED
    # Attempt 3 → none (fallback)
    s3 = await engine.select(ctx, attempt=3)
    assert s3.sandbox_type == SandboxType.NONE


@pytest.mark.asyncio
async def test_escalation_past_chain_raises_when_no_fallback():
    engine = SandboxPolicyEngine(
        bwrap_available=True,
        allow_fallback_to_none=False,
    )
    ctx = FakeContext("exec", {"command": "npm test"})
    with pytest.raises(SandboxDeniedError):
        await engine.select(ctx, attempt=4)


@pytest.mark.asyncio
async def test_write_file_uses_restricted():
    engine = SandboxPolicyEngine()
    ctx = FakeContext("write_file", {"path": "/tmp/test.txt"})
    selection = await engine.select(ctx)
    assert selection.sandbox_type == SandboxType.RESTRICTED


@pytest.mark.asyncio
async def test_filesystem_policy_for_exec():
    engine = SandboxPolicyEngine()
    ctx = FakeContext("exec", {"command": "ls"})
    selection = await engine.select(ctx)
    assert selection.filesystem_policy.default_mode == FileSystemAccessMode.READ


@pytest.mark.asyncio
async def test_filesystem_policy_for_write():
    engine = SandboxPolicyEngine()
    ctx = FakeContext("write_file", {"path": "/tmp/out.txt"})
    selection = await engine.select(ctx)
    # Should have a write rule for the target path
    assert len(selection.filesystem_policy.rules) >= 1
