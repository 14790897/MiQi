"""Tests for exec environment description helpers.

The exec tool description and the per-turn session context used to
hard-code "exec 在沙箱中运行 / /home/miqi / /mnt/c" regardless of the
actual runtime state.  With the sandbox disabled, exec runs directly on
the host (Windows cmd on Windows), so the AI was told a false story and
kept issuing WSL paths / bash syntax that failed — see the MOF-5
re-upload thrashing (bridge log 2026-08-24: /mnt/c paths and
--break-system-packages run through Windows cmd, sandbox=none).
"""

import pytest

from miqi.sandbox.manager import describe_exec_environment, sandbox_is_active


class FakeSandboxManager:
    def __init__(self, enabled: bool = False, initialized: bool = False):
        self.enabled = enabled
        self._initialized = initialized


@pytest.mark.parametrize(
    "manager,expected",
    [
        (None, False),
        ("disabled", False),
        (FakeSandboxManager(enabled=False, initialized=True), False),
        (FakeSandboxManager(enabled=True, initialized=False), False),
        (FakeSandboxManager(enabled=True, initialized=True), True),
    ],
)
def test_sandbox_is_active(manager, expected):
    assert sandbox_is_active(manager) is expected


def test_describe_exec_environment_sandbox_active():
    manager = FakeSandboxManager(enabled=True, initialized=True)
    text = describe_exec_environment(manager)
    assert "WSL" in text
    assert "/home/miqi/workspace" in text


def test_describe_exec_environment_no_sandbox_windows(monkeypatch):
    monkeypatch.setattr("miqi.sandbox.manager.os.name", "nt")
    text = describe_exec_environment(None)
    assert "Windows" in text
    assert "cmd" in text
    assert "&&" in text
    assert "/mnt/c" not in text
    assert "/home/miqi" not in text


def test_describe_exec_environment_no_sandbox_posix(monkeypatch):
    monkeypatch.setattr("miqi.sandbox.manager.os.name", "posix")
    text = describe_exec_environment(None)
    assert "bash" in text
    assert "/mnt/c" not in text
    assert "/home/miqi" not in text


def test_exec_tool_description_reflects_sandbox_state(monkeypatch):
    from miqi.agent.tools.shell import ExecTool

    tool_active = ExecTool(
        working_dir=".",
        sandbox_manager=FakeSandboxManager(enabled=True, initialized=True),
    )
    assert "WSL" in tool_active.description
    assert "/home/miqi/workspace" in tool_active.description

    monkeypatch.setattr("miqi.sandbox.manager.os.name", "nt")
    tool_off = ExecTool(working_dir=".")
    assert "Windows" in tool_off.description
    assert "cmd" in tool_off.description
    assert "/mnt/c" not in tool_off.description
    assert "/home/miqi" not in tool_off.description


def test_session_context_reflects_sandbox_state(monkeypatch, tmp_path):
    from miqi.runtime.agent_control import build_session_context

    monkeypatch.setattr("miqi.sandbox.manager.os.name", "nt")
    ctx = build_session_context(
        workspace=tmp_path,
        session_id="miqi-desktop:desktop:test",
        sandbox_manager=None,
    )
    assert "Windows" in ctx
    assert "cmd" in ctx
    assert str(tmp_path) in ctx
    assert "/mnt/c" not in ctx
    # the legacy "不要说 /home/miqi/workspace" disclaimer may remain,
    # but the WSL sandbox environment story must not be injected
    assert "WSL" not in ctx

    ctx_active = build_session_context(
        workspace=tmp_path,
        session_id="miqi-desktop:desktop:test",
        sandbox_manager=FakeSandboxManager(enabled=True, initialized=True),
    )
    assert "/home/miqi/workspace" in ctx_active
    assert "WSL" in ctx_active
