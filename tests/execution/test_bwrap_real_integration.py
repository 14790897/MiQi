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
