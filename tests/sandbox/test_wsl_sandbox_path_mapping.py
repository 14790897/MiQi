"""Unit tests for WSL sandbox path mapping functions (#474).

Tests _resolve_sandbox_path, _canonicalize_wsl_mnt_path, and
_sandbox_to_host_path without requiring a real WSL environment.
"""
import tempfile
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from miqi.agent.tools.filesystem import (
    _canonicalize_wsl_mnt_path,
    _resolve_sandbox_path,
    _sandbox_to_host_path,
)


# ── Helpers ──────────────────────────────────────────────────────────────

def _make_wsl_sandbox():
    """Create a mock sandbox with _use_wsl=True."""
    sb = MagicMock()
    sb._use_wsl = True
    sb.workspace = Path("/tmp/mock_ws")
    return sb


def _make_native_sandbox():
    """Create a mock sandbox with _use_wsl=False."""
    sb = MagicMock()
    sb._use_wsl = False
    sb.workspace = Path("/tmp/mock_ws")
    return sb


# ── _canonicalize_wsl_mnt_path ───────────────────────────────────────────

class TestCanonicalizeWslMntPath:
    """Tests for _canonicalize_wsl_mnt_path workspace containment."""

    def test_normal_path_within_workspace(self):
        """Normal /mnt/ path within workspace passes through."""
        ws = Path("C:/Users/test/workspace")
        result = _canonicalize_wsl_mnt_path(
            "/mnt/c/Users/test/workspace/readme.md", ws
        )
        assert result == "/mnt/c/Users/test/workspace/readme.md"

    def test_path_traversal_rejected(self):
        """.. traversal escaping workspace raises PermissionError."""
        ws = Path("C:/Users/test/workspace")
        with pytest.raises(PermissionError, match="outside"):
            _canonicalize_wsl_mnt_path(
                "/mnt/c/Users/test/workspace/../../secret.txt", ws
            )

    def test_path_outside_workspace_rejected(self):
        """Path to a different directory raises PermissionError."""
        ws = Path("C:/Users/test/workspace")
        with pytest.raises(PermissionError, match="outside"):
            _canonicalize_wsl_mnt_path(
                "/mnt/c/Windows/System32/config/SAM", ws
            )

    def test_no_workspace_returns_unchanged(self):
        """None workspace passes path through unchanged."""
        result = _canonicalize_wsl_mnt_path(
            "/mnt/c/Users/test/../../secret.txt", None
        )
        assert result == "/mnt/c/Users/test/../../secret.txt"

    def test_non_mnt_path_returns_unchanged(self):
        """Non-/mnt/ paths pass through unchanged."""
        ws = Path("C:/Users/test/workspace")
        result = _canonicalize_wsl_mnt_path("/home/miqi/workspace/file.txt", ws)
        assert result == "/home/miqi/workspace/file.txt"

    def test_canonicalize_resolves_dots(self):
        """.. within workspace is resolved but stays inside."""
        ws = Path("C:/Users/test/workspace")
        result = _canonicalize_wsl_mnt_path(
            "/mnt/c/Users/test/workspace/subdir/../readme.md", ws
        )
        assert ".." not in result
        assert result == "/mnt/c/Users/test/workspace/readme.md"

    def test_workspace_root_itself(self):
        """The workspace root itself is allowed."""
        ws = Path("C:/Users/test/workspace")
        result = _canonicalize_wsl_mnt_path("/mnt/c/Users/test/workspace", ws)
        assert result == "/mnt/c/Users/test/workspace"


# ── _resolve_sandbox_path ────────────────────────────────────────────────

class TestResolveSandboxPathWSL:
    """Tests for _resolve_sandbox_path WSL /mnt/ path mapping."""

    def test_windows_absolute_path_maps_to_mnt(self):
        """C:\\... paths map to /mnt/c/... under WSL sandbox."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path("C:\\Users\\test\\workspace\\file.txt", ws, sb)
        assert result == "/mnt/c/Users/test/workspace/file.txt"

    def test_windows_path_outside_workspace_rejected(self):
        """Windows path outside workspace raises PermissionError under WSL."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        with pytest.raises(PermissionError, match="outside"):
            _resolve_sandbox_path("C:\\Windows\\System32\\file.txt", ws, sb)

    def test_relative_path_maps_to_mnt_under_wsl(self):
        """Relative paths resolve to workspace via /mnt/ under WSL."""
        ws = Path("D:/projects/myapp")
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path("src/main.py", ws, sb)
        assert result == "/mnt/d/projects/myapp/src/main.py"

    def test_relative_path_traversal_rejected(self):
        """Relative path with .. escaping workspace raises PermissionError."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        with pytest.raises(PermissionError, match="outside"):
            _resolve_sandbox_path("../../secret.txt", ws, sb)

    def test_linux_path_kept_as_is_wsl(self):
        """Absolute Linux paths inside sandbox pass through."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path("/home/miqi/workspace/file.txt", ws, sb)
        assert result == "/home/miqi/workspace/file.txt"

    def test_mnt_path_kept_with_containment_wsl(self):
        """Existing /mnt/ paths kept with containment check under WSL."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path(
            "/mnt/c/Users/test/workspace/file.txt", ws, sb
        )
        assert result == "/mnt/c/Users/test/workspace/file.txt"

    def test_mnt_path_outside_workspace_rejected(self):
        """Existing /mnt/ path outside workspace rejected under WSL."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        with pytest.raises(PermissionError, match="outside"):
            _resolve_sandbox_path("/mnt/c/Windows/file.txt", ws, sb)

    def test_native_sandbox_still_uses_workspace_remap(self):
        """Non-WSL sandbox keeps the old workspace remap behavior."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_native_sandbox()
        result = _resolve_sandbox_path("C:\\Users\\test\\workspace\\file.txt", ws, sb)
        assert result == "/home/miqi/workspace/file.txt"

    def test_wsl_with_drive_d_mapping(self):
        """D: drive paths map to /mnt/d/... under WSL."""
        ws = Path("D:/data")
        sb = _make_wsl_sandbox()
        result = _resolve_sandbox_path("D:\\data\\report.csv", ws, sb)
        assert result == "/mnt/d/data/report.csv"

    def test_wsl_workspace_with_session_subdir(self, tmp_path):
        """WSL paths under a per-session workspace subdirectory work."""
        session_ws = tmp_path / "sessions" / "abc123" / "files"
        session_ws.mkdir(parents=True, exist_ok=True)
        sb = _make_wsl_sandbox()
        # A relative path resolves against the session workspace
        result = _resolve_sandbox_path("temp.txt", session_ws, sb)
        ws_str = str(session_ws.resolve()).replace("\\", "/")
        assert result.startswith("/mnt/")
        assert result.endswith("/sessions/abc123/files/temp.txt")


# ── _sandbox_to_host_path ────────────────────────────────────────────────

class TestSandboxToHostPath:
    """Tests for _sandbox_to_host_path /mnt/ conversion."""

    def test_mnt_path_converts_to_windows(self):
        """/mnt/c/... converts to C:/..."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        result = _sandbox_to_host_path(
            "/mnt/c/Users/test/workspace/file.txt", ws, sb
        )
        assert result == "C:/Users/test/workspace/file.txt"

    def test_mnt_d_drive_converts(self):
        """/mnt/d/... converts to D:/..."""
        ws = Path("D:/data")
        sb = _make_wsl_sandbox()
        result = _sandbox_to_host_path("/mnt/d/data/report.csv", ws, sb)
        assert result == "D:/data/report.csv"

    def test_home_miqi_workspace_path_still_works(self):
        """Original /home/miqi/workspace paths still convert correctly."""
        ws = Path("C:/Users/test/workspace")
        sb = _make_wsl_sandbox()
        result = _sandbox_to_host_path(
            "/home/miqi/workspace/file.txt", ws, sb
        )
        assert result == "C:/Users/test/workspace/file.txt"

    def test_none_workspace_returns_unchanged(self):
        """None workspace returns path unchanged."""
        sb = _make_wsl_sandbox()
        result = _sandbox_to_host_path("/mnt/c/some/file.txt", None, sb)
        assert result == "/mnt/c/some/file.txt"

    def test_empty_path_returns_empty(self):
        """Empty or None path returns unchanged."""
        sb = _make_wsl_sandbox()
        assert _sandbox_to_host_path("", Path("C:/ws"), sb) == ""
        assert _sandbox_to_host_path(None, Path("C:/ws"), sb) is None
