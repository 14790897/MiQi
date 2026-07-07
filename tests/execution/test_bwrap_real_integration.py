"""Real bubblewrap integration tests.

These tests only run when bwrap (or WSL with bwrap) is actually available.
They validate the full BwrapSandbox stack rather than mocked handles.
"""

import sys

import pytest


@pytest.mark.sandbox
@pytest.mark.bwrap
@pytest.mark.subprocess
@pytest.mark.asyncio
async def test_bwrap_sandbox_runs_echo_command(
    require_bwrap, require_subprocess, tmp_path,
):
    """A real bwrap sandbox must successfully run a command and return output.

    The sandbox is destroyed in ``finally`` so the host never leaks a bwrap
    container, regardless of assertion failures.
    """
    from miqi.sandbox.manager import SandboxManager

    manager = SandboxManager(workspace=tmp_path, enabled=True)
    cleanup_failed = False
    try:
        initialized = await manager.initialize()
        assert initialized, "bwrap should be available on this host"

        sandbox = await manager.get_or_create("integration-test:echo")
        assert sandbox is not None, "sandbox must be created when bwrap is available"

        exit_code, stdout, stderr = await sandbox.run_command("echo hello-from-bwrap")
        assert exit_code == 0, f"bwrap command failed: {stderr}"
        assert "hello-from-bwrap" in stdout
    finally:
        try:
            destroyed = await manager.destroy("integration-test:echo")
            if not destroyed:
                cleanup_failed = True
        except Exception:
            cleanup_failed = True

        if cleanup_failed and sys.exc_info()[0] is None:
            pytest.fail("failed to clean up real bwrap sandbox")


@pytest.mark.sandbox
@pytest.mark.bwrap
@pytest.mark.subprocess
@pytest.mark.asyncio
async def test_bwrap_sandbox_uses_workspace_and_writes_back(
    require_bwrap, require_subprocess, tmp_path,
):
    """A real bwrap sandbox must run from the sandbox workspace and write back.

    This is the visible acceptance proof for #142: a command sees
    ``/home/miqi/workspace`` inside the sandbox, and files created there are
    transparently visible in the host workspace because the workspace is
    bind-mounted.
    """
    from miqi.sandbox.manager import SandboxManager

    manager = SandboxManager(workspace=tmp_path, enabled=True)
    cleanup_failed = False
    try:
        initialized = await manager.initialize()
        assert initialized, "bwrap should be available on this host"

        sandbox = await manager.activate("integration-test:writeback")
        assert sandbox is not None, "sandbox must be created when bwrap is available"

        exit_code, stdout, stderr = await sandbox.run_command(
            "pwd && printf sandbox-proof > sandbox-proof.txt",
        )
        assert exit_code == 0, f"bwrap command failed: {stderr}"
        assert "/home/miqi/workspace" in stdout
        assert (tmp_path / "sandbox-proof.txt").read_text() == "sandbox-proof"
    finally:
        try:
            destroyed = await manager.destroy("integration-test:writeback")
            if not destroyed:
                cleanup_failed = True
        except Exception:
            cleanup_failed = True

        if cleanup_failed and sys.exc_info()[0] is None:
            pytest.fail("failed to clean up real bwrap sandbox")
