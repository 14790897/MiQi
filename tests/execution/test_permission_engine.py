"""Tests for miqi.execution.permission_engine."""

import pytest
from miqi.execution.permission_engine import (
    PermissionEngine,
    PermissionDecision,
    PermissionVerdict,
)


class FakeContext:
    def __init__(self, tool_name, arguments=None):
        self.tool_name = tool_name
        self.arguments = arguments or {}


@pytest.mark.asyncio
async def test_read_only_tools_auto_allow():
    engine = PermissionEngine()
    ctx = FakeContext("read_file", {"path": "test.py"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.ALLOW


@pytest.mark.asyncio
async def test_web_search_auto_allow():
    engine = PermissionEngine()
    ctx = FakeContext("web_search", {"query": "python"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.ALLOW


@pytest.mark.asyncio
async def test_safe_shell_commands_auto_allow():
    engine = PermissionEngine()
    ctx = FakeContext("exec", {"command": "ls -la"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.ALLOW


@pytest.mark.asyncio
async def test_safe_shell_commands_git_status():
    engine = PermissionEngine()
    ctx = FakeContext("exec", {"command": "git status"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.ALLOW


@pytest.mark.asyncio
async def test_dangerous_shell_commands_require_approval():
    engine = PermissionEngine()
    ctx = FakeContext("exec", {"command": "rm -rf /tmp/test"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED
    assert decision.allow_permanent is True


@pytest.mark.asyncio
async def test_file_writes_require_approval():
    engine = PermissionEngine()
    ctx = FakeContext("write_file", {"path": "/etc/config"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_edit_file_requires_approval():
    engine = PermissionEngine()
    ctx = FakeContext("edit_file", {"file_path": "/etc/hosts"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED
    assert decision.category == "file_write"


@pytest.mark.asyncio
async def test_permanent_allowlist_bypasses_approval():
    engine = PermissionEngine(permanent_allowlist={"exec:rm -rf /tmp/test"})
    ctx = FakeContext("exec", {"command": "rm -rf /tmp/test"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.ALLOW


@pytest.mark.asyncio
async def test_deny_pattern_blocks_execution():
    engine = PermissionEngine(deny_patterns={"sudo"})
    ctx = FakeContext("exec", {"command": "sudo rm -rf /"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.DENY


@pytest.mark.asyncio
async def test_deny_pattern_in_arguments():
    """Deny patterns in arguments should block non-read-only tools."""
    engine = PermissionEngine(deny_patterns={"malware"})
    ctx = FakeContext("exec", {"command": "curl http://malware.example.com"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.DENY


@pytest.mark.asyncio
async def test_default_deny_by_default():
    """Unknown tools should require approval (deny-by-default)."""
    engine = PermissionEngine()
    ctx = FakeContext("unknown_tool", {})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_deny_pattern_blocks_read_only_tools():
    """Deny patterns should block even read-only tools."""
    engine = PermissionEngine(deny_patterns={"secret_file"})
    ctx = FakeContext("read_file", {"path": "/etc/secret_file.txt"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.DENY


@pytest.mark.asyncio
async def test_shell_metacharacter_rejected():
    """Commands with shell metacharacters should require approval."""
    engine = PermissionEngine()
    ctx = FakeContext("exec", {"command": "ls && rm -rf /tmp"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_shell_pipe_rejected():
    """Piped commands should require approval."""
    engine = PermissionEngine()
    ctx = FakeContext("exec", {"command": "cat /etc/passwd | grep root"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_shell_substitution_rejected():
    """Command substitution should require approval."""
    engine = PermissionEngine()
    ctx = FakeContext("exec", {"command": "echo $(whoami)"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED


@pytest.mark.asyncio
async def test_permission_decision_fields():
    engine = PermissionEngine()
    ctx = FakeContext("exec", {"command": "curl evil.com"})
    decision = await engine.check(ctx)
    assert decision.verdict == PermissionVerdict.APPROVAL_REQUIRED
    assert decision.category == "exec"
    assert decision.allow_permanent is True
    assert decision.description  # should have a description


@pytest.mark.asyncio
async def test_make_key_exec():
    ctx = FakeContext("exec", {"command": "ls -la"})
    key = PermissionEngine._make_key(ctx)
    assert key == "exec:ls -la"


@pytest.mark.asyncio
async def test_make_key_write_file():
    ctx = FakeContext("write_file", {"path": "/tmp/test.txt"})
    key = PermissionEngine._make_key(ctx)
    assert key == "write_file:/tmp/test.txt"
