"""Tests for exec environment description helpers and Git Bash exec.

The exec tool description and the per-turn session context used to
hard-code "exec 在沙箱中运行 / /home/miqi / /mnt/c" regardless of the
actual runtime state.  With the sandbox disabled, exec runs directly on
the host — and on Windows it now runs through Git Bash (bash.exe) when
available, so the AI's bash habits (; chains, ls/find/grep) keep working.
See the MOF-5 re-upload thrashing (bridge log 2026-08-24) for the
failure mode this prevents.
"""

import os

import pytest

from miqi.sandbox.manager import (
    describe_exec_environment,
    find_git_bash,
    sandbox_is_active,
    windows_path_to_msys,
)


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


@pytest.mark.parametrize(
    "win_path,expected",
    [
        (r"C:\Users\Intership003\.miqi\workspace", "/c/Users/Intership003/.miqi/workspace"),
        ("D:/data/out", "/d/data/out"),
        ("/already/posix", "/already/posix"),
    ],
)
def test_windows_path_to_msys(win_path, expected):
    assert windows_path_to_msys(win_path) == expected


def _reset_git_bash_cache(monkeypatch):
    monkeypatch.setattr("miqi.sandbox.manager._git_bash_checked", False)
    monkeypatch.setattr("miqi.sandbox.manager._git_bash_path", None)


def test_find_git_bash_from_path(monkeypatch):
    _reset_git_bash_cache(monkeypatch)
    monkeypatch.setattr("miqi.sandbox.manager.shutil.which", lambda name: r"C:\Program Files\Git\bin\bash.exe")
    assert find_git_bash() == r"C:\Program Files\Git\bin\bash.exe"


class _FakeOsPath:
    """Stand-in for os.path in find_git_bash detection tests."""

    def __init__(self, existing: tuple[str, ...] = (), expandvars_result: str | None = None):
        self._existing = set(existing)
        self._expandvars_result = expandvars_result

    def exists(self, path: str) -> bool:
        return path in self._existing

    def expandvars(self, path: str) -> str:
        return self._expandvars_result if self._expandvars_result is not None else path


class _FakeOs:
    """Stand-in for the os module inside miqi.sandbox.manager."""

    def __init__(self, existing: tuple[str, ...] = (), expandvars_result: str | None = None):
        self.name = "nt"
        self.path = _FakeOsPath(existing, expandvars_result)


def test_find_git_bash_from_common_location(monkeypatch, tmp_path):
    _reset_git_bash_cache(monkeypatch)
    monkeypatch.setattr("miqi.sandbox.manager.shutil.which", lambda name: None)
    fake = tmp_path / "Git" / "bin" / "bash.exe"
    monkeypatch.setattr(
        "miqi.sandbox.manager.os",
        _FakeOs(existing=(str(fake),), expandvars_result=str(fake)),
        raising=False,
    )
    assert find_git_bash() == str(fake)


def test_find_git_bash_not_installed(monkeypatch):
    _reset_git_bash_cache(monkeypatch)
    monkeypatch.setattr("miqi.sandbox.manager.shutil.which", lambda name: None)
    monkeypatch.setattr("miqi.sandbox.manager.os", _FakeOs(), raising=False)
    assert find_git_bash() is None


def test_describe_exec_environment_sandbox_active():
    manager = FakeSandboxManager(enabled=True, initialized=True)
    text = describe_exec_environment(manager)
    assert "WSL" in text
    assert "/home/miqi/workspace" in text


def test_describe_exec_environment_no_sandbox_windows_cmd_fallback(monkeypatch):
    monkeypatch.setattr("miqi.sandbox.manager.os.name", "nt")
    monkeypatch.setattr("miqi.sandbox.manager.find_git_bash", lambda: None)
    text = describe_exec_environment(None)
    assert "Windows" in text
    assert "cmd" in text
    assert "&&" in text
    assert "/mnt/c" not in text
    assert "/home/miqi" not in text


def test_describe_exec_environment_no_sandbox_windows_git_bash(monkeypatch):
    monkeypatch.setattr("miqi.sandbox.manager.os.name", "nt")
    monkeypatch.setattr(
        "miqi.sandbox.manager.find_git_bash",
        lambda: r"C:\Program Files\Git\bin\bash.exe",
    )
    text = describe_exec_environment(None, workspace=r"C:\Users\demo\ws")
    assert "Git Bash" in text
    assert "bash 语法" in text
    assert "/c/Users/demo/ws" in text
    assert "cmd" not in text
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
    monkeypatch.setattr("miqi.sandbox.manager.find_git_bash", lambda: None)
    tool_off = ExecTool(working_dir=".")
    assert "Windows" in tool_off.description
    assert "cmd" in tool_off.description
    assert "/mnt/c" not in tool_off.description
    assert "/home/miqi" not in tool_off.description


def test_exec_tool_description_git_bash(monkeypatch):
    from miqi.agent.tools.shell import ExecTool

    monkeypatch.setattr("miqi.sandbox.manager.os.name", "nt")
    monkeypatch.setattr(
        "miqi.sandbox.manager.find_git_bash",
        lambda: r"C:\Program Files\Git\bin\bash.exe",
    )
    tool = ExecTool(working_dir=r"C:\Users\demo\ws")
    assert "Git Bash" in tool.description
    assert "/c/Users/demo/ws" in tool.description


def test_session_context_reflects_sandbox_state(monkeypatch, tmp_path):
    from miqi.runtime.agent_control import build_session_context

    monkeypatch.setattr("miqi.sandbox.manager.os.name", "nt")
    monkeypatch.setattr("miqi.sandbox.manager.find_git_bash", lambda: None)
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


@pytest.mark.skipif(os.name != "nt", reason="Git Bash exec path is Windows-only")
def test_exec_direct_runs_through_git_bash_on_windows(tmp_path):
    """With Git Bash installed, ;-chained commands must actually execute
    (Windows cmd would echo the whole string verbatim instead)."""
    import asyncio

    from miqi.agent.tools.shell import ExecTool

    if find_git_bash() is None:
        pytest.skip("Git Bash not installed on this machine")

    tool = ExecTool(working_dir=str(tmp_path))

    async def _run() -> object:
        return await tool._execute_direct("echo A; echo B; echo C", str(tmp_path))

    result = asyncio.run(_run())
    assert result.exit_code == 0
    assert "A" in result.output and "B" in result.output and "C" in result.output
    # cmd would have echoed the command text verbatim; bash executed it
    assert "echo" not in result.output
