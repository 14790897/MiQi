"""Unit tests for WSL sandbox path mapping functions (#474).

Tests _resolve_sandbox_path, _canonicalize_wsl_mnt_path, and
_sandbox_to_host_path. WSL-specific containment tests are Windows-only;
logic tests run everywhere.
"""
import os
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miqi.agent.tools.filesystem import (
    _canonicalize_wsl_mnt_path,
    _resolve_sandbox_path,
    _sandbox_to_host_path,
)

_IS_WINDOWS = sys.platform == "win32"


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_wsl_sandbox():
    sb = MagicMock()
    sb._use_wsl = True
    sb.workspace = Path("/tmp/mock_ws")
    return sb


def _make_native_sandbox():
    sb = MagicMock()
    sb._use_wsl = False
    sb.workspace = Path("/tmp/mock_ws")
    return sb


def _as_mnt_path(host_path: Path, *extra: str) -> str:
    """Convert a host Path to a /mnt/<drive>/... sandbox path on Windows,
    or /mnt/c<path> on Linux (for unit testing only)."""
    p = host_path.resolve()
    if _IS_WINDOWS:
        drive = p.drive[0].lower()
        rest = p.as_posix()[2:].lstrip("/")
    else:
        drive = "c"
        rest = p.as_posix().lstrip("/")
    parts = [f"/mnt/{drive}", rest] + list(extra)
    return "/".join(parts)


# ── _canonicalize_wsl_mnt_path ───────────────────────────────────────────

class TestCanonicalizeWslMntPath:

    def test_normal_path_within_workspace(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        result = _canonicalize_wsl_mnt_path(
            _as_mnt_path(ws, "readme.md"), ws
        )
        assert "readme.md" in result
        assert ".." not in result

    @pytest.mark.skipif(not _IS_WINDOWS, reason="WSL containment Windows-only")
    def test_path_traversal_rejected(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        mnt = _as_mnt_path(ws, "..", "secret.txt")
        with pytest.raises(PermissionError, match="outside"):
            _canonicalize_wsl_mnt_path(mnt, ws)

    @pytest.mark.skipif(not _IS_WINDOWS, reason="WSL containment Windows-only")
    def test_path_outside_workspace_rejected(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        with pytest.raises(PermissionError, match="outside"):
            _canonicalize_wsl_mnt_path(_as_mnt_path(other, "file.txt"), ws)

    def test_no_workspace_returns_unchanged(self):
        result = _canonicalize_wsl_mnt_path(
            "/mnt/c/some/../file.txt", None
        )
        assert result == "/mnt/c/some/../file.txt"

    def test_non_mnt_path_returns_unchanged(self, tmp_path):
        result = _canonicalize_wsl_mnt_path(
            "/home/miqi/workspace/file.txt", tmp_path
        )
        assert result == "/home/miqi/workspace/file.txt"

    def test_canonicalize_resolves_dots(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        result = _canonicalize_wsl_mnt_path(
            _as_mnt_path(ws, "nested", "..", "readme.md"), ws
        )
        assert ".." not in result
        assert result.endswith("/readme.md")

    def test_workspace_root_itself(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        result = _canonicalize_wsl_mnt_path(_as_mnt_path(ws), ws)
        assert result.endswith("/sub")


# ── _resolve_sandbox_path ────────────────────────────────────────────────

class TestResolveSandboxPathWSL:

    def test_wsl_windows_path_maps_to_mnt(self, tmp_path):
        """Under WSL sandbox on Windows, C:\\... maps to /mnt/..."""
        ws = tmp_path
        sb = _make_wsl_sandbox()
        if _IS_WINDOWS:
            win_path = str(ws.resolve() / "file.txt")
            result = _resolve_sandbox_path(win_path, ws, sb)
            assert result.startswith("/mnt/")
            assert result.endswith("/file.txt")
        else:
            # Linux: WSL sandbox not applicable, test fallback behavior
            result = _resolve_sandbox_path("readme.md", ws, sb)
            assert "readme.md" in result

    @pytest.mark.skipif(not _IS_WINDOWS, reason="WSL containment Windows-only")
    def test_windows_path_outside_workspace_rejected(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        sb = _make_wsl_sandbox()
        other = tmp_path / "other"
        other.mkdir()
        with pytest.raises(PermissionError, match="outside"):
            _resolve_sandbox_path(str(other.resolve() / "file.txt"), ws, sb)

    def test_relative_path_under_wsl(self, tmp_path):
        """Relative paths resolve against workspace under WSL."""
        ws = tmp_path / "proj"
        ws.mkdir()
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path("src/main.py", ws, sb)
        assert result.endswith("/src/main.py")

    @pytest.mark.skipif(not _IS_WINDOWS, reason="WSL containment Windows-only")
    def test_relative_path_traversal_rejected(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        sb = _make_wsl_sandbox()
        with pytest.raises(PermissionError, match="outside"):
            _resolve_sandbox_path("../../secret.txt", ws, sb)

    def test_linux_path_kept_as_is(self, tmp_path):
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path(
            "/home/miqi/workspace/file.txt", tmp_path, sb
        )
        assert result == "/home/miqi/workspace/file.txt"

    @pytest.mark.skipif(not _IS_WINDOWS, reason="WSL /mnt/ containment Windows-only")
    def test_mnt_path_within_workspace(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path(
            _as_mnt_path(ws, "file.txt"), ws, sb
        )
        assert "file.txt" in result

    @pytest.mark.skipif(not _IS_WINDOWS, reason="WSL containment Windows-only")
    def test_mnt_path_outside_workspace_rejected(self, tmp_path):
        ws = tmp_path / "sub"
        ws.mkdir()
        other = tmp_path / "other"
        other.mkdir()
        sb = _make_wsl_sandbox()
        with pytest.raises(PermissionError, match="outside"):
            _resolve_sandbox_path(_as_mnt_path(other, "file.txt"), ws, sb)

    def test_native_sandbox_uses_workspace_remap(self, tmp_path):
        """Non-WSL sandbox still uses the old workspace remap."""
        ws = tmp_path
        sb = _make_native_sandbox()
        result = _resolve_sandbox_path("readme.md", ws, sb)
        assert result.endswith("/readme.md")

    def test_wsl_session_subdir(self, tmp_path):
        session_ws = tmp_path / "sessions" / "abc123" / "files"
        session_ws.mkdir(parents=True)
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path("temp.txt", session_ws, sb)
        assert result.endswith("/sessions/abc123/files/temp.txt")


# ── _sandbox_to_host_path ────────────────────────────────────────────────

class TestSandboxToHostPath:

    def test_mnt_path_converts_to_host(self, tmp_path):
        ws = tmp_path
        sb = _make_wsl_sandbox()
        result = _sandbox_to_host_path(
            _as_mnt_path(ws, "file.txt"), ws, sb
        )
        assert "file.txt" in result

    def test_home_miqi_workspace_conversion(self, tmp_path):
        ws = tmp_path
        sb = _make_wsl_sandbox()
        result = _sandbox_to_host_path(
            "/home/miqi/workspace/file.txt", ws, sb
        )
        assert "file.txt" in result

    def test_none_workspace_returns_unchanged(self):
        sb = _make_wsl_sandbox()
        result = _sandbox_to_host_path("/mnt/c/some/file.txt", None, sb)
        assert result == "/mnt/c/some/file.txt"

    def test_empty_path_returns_empty(self, tmp_path):
        sb = _make_wsl_sandbox()
        assert _sandbox_to_host_path("", tmp_path, sb) == ""
        assert _sandbox_to_host_path(None, tmp_path, sb) is None
