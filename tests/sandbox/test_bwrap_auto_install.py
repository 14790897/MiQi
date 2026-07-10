"""Tests for WSL sandbox auto-install (bwrap.py).

Verifies that _find_any_wsl_distro, _ensure_wsl_deps, and the auto-install
integration in is_available() work correctly by mocking asyncio subprocess.
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from miqi.sandbox.bwrap import BwrapSandbox


# ── mock helpers ─────────────────────────────────────────────────────────

def _mock_process(returncode=0, stdout=b"", stderr=b""):
    """Create a mock asyncio Process."""
    proc = MagicMock()
    proc.returncode = returncode

    async def _communicate():
        return (stdout, stderr)

    proc.communicate = _communicate
    return proc


class MockSubprocessFactory:
    """Factory that returns different mock processes based on command args.

    Each scenario is a tuple of (arg_matchers, mock_process).
    arg_matchers is a list of strings — all must appear (substring) in the
    flattened rgs for the scenario to match.
    """

    def __init__(self, scenarios: list):
        self._scenarios = scenarios  # [(matchers, process), ...]

    async def __call__(self, *args, **kwargs):
        # Flatten to a single string for easy matching
        flat = " ".join(str(a) for a in args if isinstance(a, str))
        for matchers, proc in self._scenarios:
            if all(m in flat for m in matchers):
                return proc
        # default: failure
        return _mock_process(returncode=1, stderr=b"mock: no scenario matched")


# ── _find_any_wsl_distro ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_find_any_wsl_distro_preferred_found(monkeypatch):
    """Preferred distro is running → returns it immediately."""
    factory = MockSubprocessFactory([
        (["wsl.exe", "-d", "Ubuntu", "--", "echo ok"], _mock_process(returncode=0)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    # Also patch _is_windows
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox._find_any_wsl_distro("Ubuntu")
    assert result == "Ubuntu"


@pytest.mark.asyncio
async def test_find_any_wsl_distro_preferred_not_found_scan(monkeypatch):
    """Preferred distro not running → scans list → returns first available."""
    factory = MockSubprocessFactory([
        # Preferred fails (returncode 1)
        (["wsl.exe", "-d", "AIShadowSandbox", "--", "echo ok"],
         _mock_process(returncode=1)),
        # wsl -l -q returns distro list (UTF-16-LE encoded)
        (["wsl.exe", "-l", "-q"],
         _mock_process(returncode=0, stdout="Ubuntu\n".encode("utf-16-le"))),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox._find_any_wsl_distro("AIShadowSandbox")
    assert result == "Ubuntu"


@pytest.mark.asyncio
async def test_find_any_wsl_distro_no_wsl(monkeypatch):
    """No WSL available → returns None."""
    factory = MockSubprocessFactory([
        (["wsl.exe", "-l", "-q"], _mock_process(returncode=1)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox._find_any_wsl_distro()
    assert result is None


@pytest.mark.asyncio
async def test_find_any_wsl_distro_not_windows(monkeypatch):
    """On non-Windows → always returns None."""
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: False)

    result = await BwrapSandbox._find_any_wsl_distro("Ubuntu")
    assert result is None


# ── _ensure_wsl_deps ─────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_ensure_wsl_deps_success_with_sudo(monkeypatch):
    """sudo is available → uses sudo apt-get → install succeeds → bwrap found."""
    factory = MockSubprocessFactory([
        # has sudo
        (["command -v sudo"], _mock_process(returncode=0)),
        # apt install succeeds
        (["sudo", "apt-get"], _mock_process(returncode=0)),
        # which bwrap → found
        (["which bwrap"], _mock_process(returncode=0)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)

    result = await BwrapSandbox._ensure_wsl_deps("Ubuntu")
    assert result is True


@pytest.mark.asyncio
async def test_ensure_wsl_deps_success_without_sudo(monkeypatch):
    """No sudo → runs apt-get directly → install succeeds."""
    factory = MockSubprocessFactory([
        # no sudo
        (["command -v sudo"], _mock_process(returncode=1)),
        # apt-get succeeds (no sudo prefix)
        (["apt-get"], _mock_process(returncode=0)),
        # which bwrap → found
        (["which bwrap"], _mock_process(returncode=0)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)

    result = await BwrapSandbox._ensure_wsl_deps("Ubuntu")
    assert result is True


@pytest.mark.asyncio
async def test_ensure_wsl_deps_install_fails(monkeypatch):
    """apt-get install fails → returns False."""
    factory = MockSubprocessFactory([
        # has sudo
        (["command -v sudo"], _mock_process(returncode=0)),
        # apt install fails
        (["sudo", "apt-get"], _mock_process(
            returncode=100,
            stderr=b"E: Unable to locate package",
        )),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)

    result = await BwrapSandbox._ensure_wsl_deps("Ubuntu")
    assert result is False


@pytest.mark.asyncio
async def test_ensure_wsl_deps_install_ok_but_bwrap_missing(monkeypatch):
    """apt-get succeeds but bwrap still missing after install → False."""
    factory = MockSubprocessFactory([
        (["command -v sudo"], _mock_process(returncode=1)),
        (["apt-get"], _mock_process(returncode=0)),
        # which bwrap → still NOT found
        (["which bwrap"], _mock_process(returncode=1)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)

    result = await BwrapSandbox._ensure_wsl_deps("Ubuntu")
    assert result is False


# ── is_available with auto_install_deps ──────────────────────────────────

@pytest.mark.asyncio
async def test_is_available_bwrap_already_installed(monkeypatch):
    """bwrap already in WSL distro → returns True immediately, no install."""
    factory = MockSubprocessFactory([
        # _detect_wsl_distro: bwrap found in preferred distro
        (["wsl.exe", "-d", "Ubuntu", "--", "which bwrap"],
         _mock_process(returncode=0)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox.is_available(
        wsl_distro="Ubuntu", auto_install_deps=True,
    )
    assert result is True


@pytest.mark.asyncio
async def test_is_available_auto_install_success(monkeypatch):
    """No bwrap → auto-install → bwrap found → returns True.

    Simulates the full flow:
    1. _detect_wsl_distro fails (no bwrap anywhere)
    2. _find_any_wsl_distro finds Ubuntu
    3. _ensure_wsl_deps installs packages
    4. Retry _detect_wsl_distro → bwrap now found
    5. is_available() returns True
    """
    call_count = {"which_bwrap": 0}

    async def dynamic_factory(*args, **kwargs):
        flat = " ".join(str(a) for a in args if isinstance(a, str))
        # _detect_wsl_distro: "which bwrap" check
        if "which bwrap" in flat:
            call_count["which_bwrap"] += 1
            if call_count["which_bwrap"] <= 2:
                # First two (preferred + scan distros) → fail
                return _mock_process(returncode=1)
            # After install → succeed
            return _mock_process(returncode=0)
        # _find_any_wsl_distro: "echo ok" → distro is running
        if "echo ok" in flat:
            return _mock_process(returncode=0)
        # _ensure_wsl_deps: has sudo
        if "command -v sudo" in flat:
            return _mock_process(returncode=0)
        # _ensure_wsl_deps: apt install
        if "apt-get" in flat:
            return _mock_process(returncode=0)
        # wsl -l -q → list distros
        if "-l" in flat and "-q" in flat:
            return _mock_process(
                returncode=0,
                stdout="Ubuntu\n".encode("utf-16-le"),
            )
        return _mock_process(returncode=1)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", dynamic_factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox.is_available(
        wsl_distro="Ubuntu", auto_install_deps=True,
    )
    assert result is True


@pytest.mark.asyncio
async def test_is_available_auto_install_failure(monkeypatch):
    """No bwrap → auto-install fails → returns False."""
    factory = MockSubprocessFactory([
        # _detect_wsl_distro: no bwrap
        (["wsl.exe", "-d", "Ubuntu", "--", "which bwrap"],
         _mock_process(returncode=1)),
        (["wsl.exe", "-l", "-q"],
         _mock_process(returncode=0, stdout="Ubuntu\n".encode("utf-16-le"))),
        # _find_any_wsl_distro: "echo ok"
        (["wsl.exe", "-d", "Ubuntu", "--", "echo ok"],
         _mock_process(returncode=0)),
        # _ensure_wsl_deps: install fails
        (["command -v sudo"], _mock_process(returncode=0)),
        (["sudo", "apt-get"], _mock_process(
            returncode=100,
            stderr=b"Network unreachable",
        )),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox.is_available(
        wsl_distro="Ubuntu", auto_install_deps=True,
    )
    assert result is False


@pytest.mark.asyncio
async def test_is_available_auto_install_disabled(monkeypatch):
    """auto_install_deps=False → does NOT attempt install → returns False."""
    factory = MockSubprocessFactory([
        # _detect_wsl_distro: no bwrap
        (["wsl.exe", "-d", "Ubuntu", "--", "which bwrap"],
         _mock_process(returncode=1)),
        (["wsl.exe", "-l", "-q"],
         _mock_process(returncode=1)),  # no distros found at all
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox.is_available(
        wsl_distro="Ubuntu", auto_install_deps=False,
    )
    assert result is False


@pytest.mark.asyncio
async def test_is_available_no_wsl_installed(monkeypatch):
    """No WSL at all → returns False, no install attempt."""
    factory = MockSubprocessFactory([
        # All wsl.exe calls fail
        (["wsl.exe", "-l", "-q"], _mock_process(returncode=1)),
        (["wsl.exe", "-d", "Ubuntu", "--"], _mock_process(returncode=1)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    result = await BwrapSandbox.is_available(
        wsl_distro="Ubuntu", auto_install_deps=True,
    )
    assert result is False


@pytest.mark.asyncio
async def test_is_available_not_windows_native_check(monkeypatch):
    """On Linux (non-Windows) → delegates to native bwrap detection."""
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: False)
    # Mock native bwrap detection to succeed
    async def mock_find_native():
        return "/usr/bin/bwrap"

    monkeypatch.setattr(
        "miqi.sandbox.bwrap.BwrapSandbox._find_bwrap_native",
        mock_find_native,
    )

    result = await BwrapSandbox.is_available(
        wsl_distro="", auto_install_deps=True,
    )
    assert result is True


@pytest.mark.asyncio
async def test_is_available_default_params(monkeypatch):
    """Default auto_install_deps=True (backward compat)."""
    factory = MockSubprocessFactory([
        (["wsl.exe", "-d", "Ubuntu", "--", "which bwrap"],
         _mock_process(returncode=0)),
    ])
    monkeypatch.setattr(asyncio, "create_subprocess_exec", factory)
    monkeypatch.setattr("miqi.sandbox.bwrap._is_windows", lambda: True)

    # Default auto_install_deps=True should still work
    result = await BwrapSandbox.is_available(wsl_distro="Ubuntu")
    assert result is True
