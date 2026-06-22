"""Shared fixtures for all test packages."""

import os
import tempfile
from pathlib import Path

import pytest

from miqi.config.schema import Config


def pytest_configure(config):
    """Bootstrap a writable, repository-local pytest base temp directory.

    On some Windows/CI environments the system temp directory is read-only
    or contains an unowned ``pytest-of-*`` directory left by another process.
    Setting ``config.option.basetemp`` here forces pytest to create
    ``tmp_path`` under ``<repo>/.pytest-basetemp-*`` before any fixture runs,
    so ``isolated_process_environment`` never depends on a possibly-broken
    default system temp path.

    A per-process (or per-xdist-worker) suffix avoids conflicts between
    consecutive local runs, including cases where a previous subprocess test
    is still releasing handles when the next pytest session starts.
    """
    repo_root = Path(__file__).resolve().parent.parent
    worker = os.environ.get("PYTEST_XDIST_WORKER")
    suffix = worker if worker else f"pid{os.getpid()}"
    basetemp = repo_root / f".pytest-basetemp-{suffix}"
    basetemp.mkdir(parents=True, exist_ok=True)
    config.option.basetemp = str(basetemp)


class _FakeResponse:
    """Minimal fake LLM response with all attributes AgentLoop accesses."""
    def __init__(self, content="done", tool_calls=None, finish_reason="stop"):
        self.content = content
        self.tool_calls = tool_calls or []
        self._has_tool_calls = bool(tool_calls)
        self.reasoning_content = None
        self.usage: dict[str, int] = {}
        self.finish_reason = finish_reason

    @property
    def has_tool_calls(self):
        return self._has_tool_calls


@pytest.fixture
def fake_config():
    """Minimal Config with all fields needed by AgentLoop constructor."""
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        config = Config()
        config.agents.defaults.workspace = str(tmp)
        yield config


@pytest.fixture
def fake_provider():
    """Fake LLM provider that returns canned responses."""
    class FakeProvider:
        def __init__(self):
            self.chat_calls: list[dict] = []

        async def chat(self, **kwargs):
            self.chat_calls.append(kwargs)
            return _FakeResponse(content="done", tool_calls=[])

        async def stream_chat(self, **kwargs):
            """Phase 20: streaming fallback wrapping chat()."""
            from miqi.providers.base import LLMStreamEvent
            response = await self.chat(**kwargs)
            yield LLMStreamEvent(kind="completed", response=response)

    return FakeProvider()


@pytest.fixture(autouse=True)
def isolated_process_environment(monkeypatch, tmp_path, request):
    """Isolate every test from the real user home and system temp.

    Sets MIQI_HOME, HOME, USERPROFILE, TEMP, TMP, TMPDIR, and
    tempfile.tempdir below ``tmp_path`` so that no MiQi-owned write
    or third-party temp file can accidentally land in the real user
    profile.

    Tests decorated with ``@pytest.mark.self_managed_env`` opt out
    of automatic isolation — they MUST set all six environment
    variables themselves before any path access.
    """
    import tempfile

    if request.node.get_closest_marker("self_managed_env") is not None:
        return

    iso_dir = tmp_path / ".pytest-isolation"
    iso_dir.mkdir()
    home = iso_dir / "home"
    miqi_home = iso_dir / ".miqi"
    temp_dir = iso_dir / "tmp"
    home.mkdir()
    temp_dir.mkdir()

    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("TEMP", str(temp_dir))
    monkeypatch.setenv("TMP", str(temp_dir))
    monkeypatch.setenv("TMPDIR", str(temp_dir))
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))


# ── Platform capability detection ─────────────────────────────────────────────


def _has_subprocess() -> bool:
    """Check whether we can spawn a normal local subprocess."""
    import shutil
    import sys

    # On all platforms, look for a basic shell
    if sys.platform == "win32":
        return shutil.which("cmd.exe") is not None
    return shutil.which("sh") is not None


def _has_bwrap() -> bool:
    """Check whether bubblewrap is available."""
    import shutil
    import subprocess

    if shutil.which("bwrap") is None:
        return False
    try:
        subprocess.run(["bwrap", "--version"], capture_output=True, timeout=5, check=True)
        return True
    except Exception:
        return False


def _has_wsl() -> bool:
    """Check whether WSL has a usable distribution."""
    import shutil
    import subprocess
    import sys

    if sys.platform != "win32":
        return False
    if shutil.which("wsl.exe") is None:
        return False
    try:
        result = subprocess.run(
            ["wsl.exe", "--status"], capture_output=True, timeout=10,
        )
        return result.returncode == 0
    except Exception:
        return False


@pytest.fixture
def require_subprocess():
    """Skip the test if a normal subprocess cannot be launched."""
    if not _has_subprocess():
        pytest.skip("subprocess executable is not available")


@pytest.fixture
def require_bwrap():
    """Skip the test if bubblewrap is not available."""
    import sys

    if sys.platform == "win32":
        pytest.skip("bwrap is not available on Windows (requires WSL)")
    if not _has_bwrap():
        pytest.skip("bwrap executable is not available")


@pytest.fixture
def require_wsl():
    """Skip the test if WSL is not available."""
    if not _has_wsl():
        pytest.skip("wsl.exe is not available or has no usable distribution")
