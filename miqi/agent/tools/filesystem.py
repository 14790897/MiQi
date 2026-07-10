"""File system tools: read, write, edit — with sandbox path mapping support.

When a WSL-based sandbox is active, file operations are routed through
the sandbox's run_command() method, which executes inside WSL+bwrap.
Otherwise, local filesystem operations are used directly.
"""

import difflib
import hashlib as _hashlib
import json as _json
import logging
import threading
from pathlib import Path
from typing import Any

from miqi.agent.tools.base import Tool

_log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# File snapshot store — keeps original content before first write/edit
# so we can diff and revert without git.
# Snapshots are persisted to ~/.miqi/snapshots/<sha256>.json
# ---------------------------------------------------------------------------

_snapshots_lock = threading.Lock()


def _snapshots_dir() -> Path:
    from miqi.paths import get_miqi_home

    d = get_miqi_home() / "snapshots"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _snapshot_file_for_dir(snapshot_dir: Path, key: str) -> Path:
    h = _hashlib.sha256(key.encode()).hexdigest()
    return snapshot_dir / f"{h}.json"


def _snapshot_file(key: str) -> Path:
    return _snapshot_file_for_dir(_snapshots_dir(), key)


def _read_snapshot(key: str, snapshot_dir: Path | None = None) -> str | None:
    if snapshot_dir:
        p = _snapshot_file_for_dir(snapshot_dir, key)
        if p.exists():
            try:
                data = _json.loads(p.read_text(encoding="utf-8"))
                return data.get("content")
            except Exception:
                pass
    # Fall back to global dir
    p = _snapshot_file(key)
    try:
        if p.exists():
            data = _json.loads(p.read_text(encoding="utf-8"))
            return data.get("content")
    except Exception:
        pass
    return None


def _write_snapshot_to(snapshot_dir: Path, key: str, content: str) -> bool:
    """Write a snapshot file. Returns True on success, False on failure."""
    p = _snapshot_file_for_dir(snapshot_dir, key)
    try:
        snapshot_dir.mkdir(parents=True, exist_ok=True)
        p.write_text(
            _json.dumps({"path": key, "content": content}, ensure_ascii=False),
            encoding="utf-8",
        )
        return True
    except Exception:
        _log.warning("Failed to write snapshot for %s to %s", key, p, exc_info=True)
        return False


def _write_snapshot(key: str, content: str) -> None:
    _write_snapshot_to(_snapshots_dir(), key, content)


def _maybe_snapshot(resolved: Path, snapshot_dir: Path | None = None) -> bool:
    """Save a snapshot of *resolved* if not already snapshotted (disk-backed).

    Returns True if a snapshot was successfully written or already existed,
    False if the write failed.
    """
    key = str(resolved)
    effective_dir = snapshot_dir or _snapshots_dir()
    with _snapshots_lock:
        if _read_snapshot(key, snapshot_dir=snapshot_dir) is not None:
            return True
        if resolved.exists():
            try:
                content = resolved.read_text(encoding="utf-8", errors="replace")
            except Exception:
                content = ""
        else:
            content = ""
        return _write_snapshot_to(effective_dir, key, content)


def _restore_snapshot(resolved: Path, snapshot_dir: Path | None = None) -> bool:
    """Restore file from disk snapshot. Returns True if successful."""
    key = str(resolved)
    with _snapshots_lock:
        original = _read_snapshot(key, snapshot_dir=snapshot_dir)
    if original is None:
        return False
    try:
        if original == "":
            if resolved.exists():
                resolved.unlink()
        else:
            resolved.write_text(original, encoding="utf-8")
        return True
    except Exception:
        return False


def _delete_snapshot(key: str, snapshot_dir: Path | None = None) -> None:
    """Remove snapshot file from disk."""
    effective_dir = snapshot_dir or _snapshots_dir()
    p = _snapshot_file_for_dir(effective_dir, key)
    try:
        if p.exists():
            p.unlink()
    except Exception:
        pass


def _has_symlink_in_path(p: Path) -> bool:
    """Return True if any existing component of *p* is a symbolic link.

    Used as defense-in-depth when a directory restriction is active:
    symlinks inside the allowed directory that point outside it would
    otherwise pass the ``relative_to`` check after ``resolve()``.
    """
    accumulated = Path(p.anchor)
    for part in p.parts[1:]:  # Skip the root anchor ('/' or 'C:\\')
        accumulated = accumulated / part
        if accumulated.is_symlink():
            return True
        if not accumulated.exists():
            break  # Remaining components don't exist yet; no further symlinks.
    return False


# ---------------------------------------------------------------------------
# Sandbox-aware path resolution & file operations
# ---------------------------------------------------------------------------

def _get_active_sandbox(sandbox_manager):
    """Get the active sandbox from the manager, if any."""
    if sandbox_manager is None:
        return None
    sandbox = sandbox_manager.active_sandbox
    if sandbox and sandbox.is_running:
        return sandbox
    return None


def _sandbox_to_host_path(sandbox_path: str, workspace: Path | None, sandbox) -> str:
    """Map sandbox-internal path to host path for user-facing output."""
    if not sandbox_path or not workspace:
        return sandbox_path
    sb_ws = getattr(sandbox, "workspace_path", None) or "/home/miqi/workspace"
    sb_ws = sb_ws.rstrip("/")
    if sandbox_path.startswith(sb_ws):
        host_ws = str(workspace.resolve()).replace("\\", "/")
        rel = sandbox_path[len(sb_ws):].lstrip("/")
        return f"{host_ws}/{rel}"
    return sandbox_path


async def _ensure_sandbox(sandbox_manager, tool_name="file_tool", session_key=None):
    """Get or create a session-isolated sandbox.

    Industry standard: sandboxes MUST be per-session. session_key is not optional.
    Without session_key, returns None (caller must handle, no shared fallback).
    """
    if sandbox_manager is None:
        return None
    if not session_key:
        _log.warning("%s: no session_key provided, cannot ensure isolation", tool_name)
        return None
    sandbox = await sandbox_manager.get_or_create(session_key)
    if sandbox is None or not sandbox.is_running:
        _log.error("%s: failed to get_or_create sandbox for session=%s", tool_name, session_key)
        return None
    return sandbox


def _get_session_workspace(base_workspace: Path | None, sandbox) -> Path | None:
    """Compute the per-session workspace directory based on the sandbox session_key.

    When session_workspace_enabled is True, each session gets its own
    isolated directory under <base_workspace>/sessions/<safe_key>/files/.
    This is used by WriteFileTool/ReadFileTool/EditFileTool to ensure
    files created in one session are not visible to another.

    When no sandbox is available (sandbox_manager.active_sandbox is None),
    returns the base workspace unchanged.  In that case file tools operate
    on the host filesystem which has no sandbox isolation.
    """
    if base_workspace is None or sandbox is None:
        return base_workspace
    session_key = getattr(sandbox, "session_key", None) or ""
    key = session_key.split(":", 1)[-1] if ":" in session_key else session_key
    if not key:
        return base_workspace
    from miqi.utils.helpers import safe_filename
    safe_key = safe_filename(key.replace(":", "_"))
    session_ws = base_workspace / "sessions" / safe_key / "files"
    session_ws.mkdir(parents=True, exist_ok=True)
    _log.debug("Session workspace: %s → %s", session_key, session_ws)
    return session_ws


def _resolve_sandbox_path(path: str, workspace: Path | None, sandbox) -> str:
    """Resolve a path for use inside the sandbox.

    Returns a Linux-style absolute path inside the sandbox filesystem.
    Handles Windows paths (e.g. C:\\Users\\...) by mapping them to
    /home/miqi/workspace/... relative to the workspace root.
    """
    import re as _re

    original_path = path

    # ── Windows absolute path: C:\... → /home/miqi/workspace/... ──
    win_match = _re.match(r"^([A-Za-z]):[/\\](.+)$", path)
    if win_match:
        drive = win_match.group(1).lower()
        rest = win_match.group(2).replace("\\", "/")
        # If the workspace matches this drive, compute relative path
        if workspace:
            ws_str = str(workspace).replace("\\", "/")
            ws_match = _re.match(r"^([A-Za-z]):/(.+)$", ws_str)
            if ws_match and ws_match.group(1).lower() == drive:
                ws_rest = ws_match.group(2).rstrip("/")
                if rest.startswith(ws_rest + "/") or rest == ws_rest:
                    rel = rest[len(ws_rest):].lstrip("/")
                    result = f"/home/miqi/workspace/{rel}" if rel else "/home/miqi/workspace"
                    _log.debug("Sandbox path: %s → %s (Windows workspace remap)", original_path, result)
                    return result
        # Fallback: map full Windows path under /mnt/ in the sandbox
        result = f"/mnt/{drive}/{rest}"
        _log.debug("Sandbox path: %s → %s (Windows /mnt/ fallback)", original_path, result)
        return result

    # ── Relative path → resolve against sandbox workspace ──
    if not path.startswith("/"):
        # Compute the correct sandbox base path.
        # If the tool's workspace is a subdirectory of the sandbox's global
        # workspace (e.g. per-session dir), use the corresponding sandbox path
        # so that per-session files are isolated from other sessions.
        sandbox_base = "/home/miqi/workspace"
        if workspace:
            ws_str = str(workspace.resolve()).replace("\\", "/")
            sb_ws_str = str(sandbox.workspace).replace("\\", "/")
            if ws_str.startswith(sb_ws_str) and ws_str != sb_ws_str:
                rel_subdir = ws_str[len(sb_ws_str):].lstrip("/")
                sandbox_base = f"/home/miqi/workspace/{rel_subdir}"
        result = f"{sandbox_base}/{path}"
        _log.debug("Sandbox path: %s → %s (relative remap, base=%s)", original_path, result, sandbox_base)
        return result

    # ── Linux path that starts with workspace prefix → remap ──
    if workspace:
        ws_str = str(workspace)
        # Handle case where workspace is a Windows path but input is already /mnt/c/...
        if ws_str[1:2] == ":":
            drive = ws_str[0].lower()
            ws_rest = ws_str[2:].replace("\\", "/").lstrip("/")
            mnt_prefix = f"/mnt/{drive}/{ws_rest}"
            if path.startswith(mnt_prefix):
                rel = path[len(mnt_prefix):].lstrip("/")
                result = f"/home/miqi/workspace/{rel}" if rel else "/home/miqi/workspace"
                _log.debug("Sandbox path: %s → %s (/mnt/ remap)", original_path, result)
                return result

    _log.debug("Sandbox path: %s → %s (no remap needed)", original_path, path)
    return path


def _resolve_path(
    path: str,
    workspace: Path | None = None,
    allowed_dir: Path | None = None,
    sandbox_manager=None,
) -> Path:
    """Resolve path against workspace (if relative) and enforce directory restriction.

    When a sandbox_manager is provided and has an active sandbox, file
    operations are automatically redirected to the sandbox's workspace
    directory. This ensures each conversation's AI only accesses its
    own isolated filesystem.
    """
    p = Path(path).expanduser()
    if not p.is_absolute() and workspace:
        p = workspace / p

    # If sandbox is active, redirect path into sandbox workspace
    sandbox = _get_active_sandbox(sandbox_manager)
    if sandbox is not None:
        # Map the path into the sandbox's workspace on the host
        sandbox_ws = Path(sandbox.workspace_path)
        if workspace:
            try:
                # If the path is under the original workspace, remap
                resolved_orig = p.resolve()
                orig_ws = workspace.resolve()
                try:
                    rel = resolved_orig.relative_to(orig_ws)
                    p = sandbox_ws / rel
                except ValueError:
                    # Path is outside workspace — leave as-is
                    pass
            except Exception:
                pass
        elif not p.is_absolute():
            p = sandbox_ws / p

    # Defense-in-depth: reject symlink components before resolving (SEC-06).
    if allowed_dir and _has_symlink_in_path(p):
        raise PermissionError(
            f"Path '{path}' contains a symbolic link, which is not permitted "
            "in restricted mode."
        )
    resolved = p.resolve()
    if allowed_dir:
        try:
            resolved.relative_to(allowed_dir.resolve())
        except ValueError:
            raise PermissionError(f"Path {path} is outside allowed directory {allowed_dir}")
    return resolved


async def _sandbox_read_file(sandbox, sandbox_path: str) -> str:
    """Read a file inside the sandbox via run_command."""
    escaped = sandbox_path.replace("'", "'\\''")
    rc, stdout, stderr = await sandbox.run_command(f"cat '{escaped}'")
    if rc != 0:
        raise FileNotFoundError(f"Cannot read {sandbox_path}: {stderr}")
    return stdout


async def _sandbox_write_file(sandbox, sandbox_path: str, content: str) -> None:
    """Write content to a file inside the sandbox via run_command."""
    escaped_path = sandbox_path.replace("'", "'\\''")
    # Use base64 encoding to safely transfer content through shell
    import base64
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    rc, _, stderr = await sandbox.run_command(
        f"mkdir -p '$(dirname \"{escaped_path}\")' && "
        f"echo '{encoded}' | base64 -d > '{escaped_path}'"
    )
    if rc != 0:
        raise IOError(f"Cannot write {sandbox_path}: {stderr}")


async def _sandbox_file_exists(sandbox, sandbox_path: str) -> bool:
    """Check if a file exists inside the sandbox."""
    escaped = sandbox_path.replace("'", "'\\''")
    rc, _, _ = await sandbox.run_command(f"test -f '{escaped}'")
    return rc == 0


async def _sandbox_dir_exists(sandbox, sandbox_path: str) -> bool:
    """Check if a directory exists inside the sandbox."""
    escaped = sandbox_path.replace("'", "'\\''")
    rc, _, _ = await sandbox.run_command(f"test -d '{escaped}'")
    return rc == 0


async def _sandbox_list_dir(sandbox, sandbox_path: str) -> str:
    """List directory contents inside the sandbox."""
    escaped = sandbox_path.replace("'", "'\\''")
    # Simple approach: use ls -1p (appends '/' to directory names),
    # then format in Python rather than in bash to avoid f-string
    # escaping issues with bash variables like ${line: -1}.
    rc, stdout, stderr = await sandbox.run_command(
        f"ls -1p '{escaped}' 2>&1"
    )
    if rc != 0:
        raise IOError(f"Cannot list {sandbox_path}: {stderr}")
    # Format: directories get 'dir ' prefix, files get 5-space indent
    lines = []
    for entry in stdout.strip().splitlines():
        if entry.endswith("/"):
            lines.append(f"dir {entry.rstrip('/')}")
        else:
            lines.append(f"     {entry}")
    return "\n".join(lines)


class ReadFileTool(Tool):
    """Tool to read file contents — works with local or sandbox filesystems."""

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        sandbox_manager=None,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._sandbox_manager = sandbox_manager

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return "Read the contents of a file at the given path."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to read"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        _sess_key = kwargs.pop("_session_key", None)
        sandbox = await _ensure_sandbox(self._sandbox_manager, session_key=_sess_key)
        session_ws = _get_session_workspace(self._workspace, sandbox)
        if sandbox is not None and getattr(sandbox, "_use_wsl", False):
            # WSL sandbox — route file operations through the sandbox
            sandbox_path = _resolve_sandbox_path(path, session_ws, sandbox)
            _log.info("read_file [sandbox]: %s → %s", path, sandbox_path)
            try:
                exists = await _sandbox_file_exists(sandbox, sandbox_path)
            except Exception as e:
                return f"Error: Failed to check file existence in sandbox (path={sandbox_path}): {e}"
            if not exists:
                return f"Error: File not found: {path} (sandbox path: {sandbox_path})"
            try:
                content = await _sandbox_read_file(sandbox, sandbox_path)
                return content
            except FileNotFoundError as e:
                return f"Error: File not found in sandbox: {sandbox_path}: {e}"
            except Exception as e:
                return f"Error: Failed to read file in sandbox (path={sandbox_path}): {type(e).__name__}: {e}"
        else:
            # Native sandbox or no sandbox — use local filesystem
            try:
                file_path = _resolve_path(
                    path, self._workspace, self._allowed_dir, self._sandbox_manager
                )
                if not file_path.exists():
                    return f"Error: File not found: {path}"
                if not file_path.is_file():
                    return f"Error: Not a file: {path}"

                content = file_path.read_text(encoding="utf-8")
                return content
            except PermissionError as e:
                return f"Error: Permission denied: {e}"
            except Exception as e:
                return f"Error reading file: {type(e).__name__}: {e}"


class WriteFileTool(Tool):
    """Tool to write content to a file — works with local or sandbox filesystems."""

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        snapshot_dir: Path | None = None,
        sandbox_manager=None,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._snapshot_dir = snapshot_dir
        self._sandbox_manager = sandbox_manager

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return "Write content to a file at the given path. Creates parent directories if needed."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to write to"
                },
                "content": {
                    "type": "string",
                    "description": "The content to write"
                }
            },
            "required": ["path", "content"]
        }

    async def execute(self, path: str, content: str, **kwargs: Any) -> str:
        office_suffixes = {".docx", ".xlsx", ".pptx"}
        if Path(path).suffix.lower() in office_suffixes:
            return (
                "Error: write_file cannot create Office binary files. "
                "Use create_docx, create_xlsx, or create_pptx instead."
            )

        _sess_key = kwargs.pop("_session_key", None)
        sandbox = await _ensure_sandbox(self._sandbox_manager, session_key=_sess_key)
        session_ws = _get_session_workspace(self._workspace, sandbox)
        if sandbox is not None and getattr(sandbox, "_use_wsl", False):
            # WSL sandbox — route file operations through the sandbox
            sandbox_path = _resolve_sandbox_path(path, session_ws, sandbox)
            _log.info("write_file [sandbox]: %s → %s", path, sandbox_path)
            try:
                await _sandbox_write_file(sandbox, sandbox_path, content)
                host_path = _sandbox_to_host_path(sandbox_path, self._workspace, sandbox)
                return f"Successfully wrote {len(content)} bytes to {host_path}"
            except IOError as e:
                return f"Error: Failed to write file in sandbox (path={sandbox_path}): {e}"
            except Exception as e:
                return f"Error: Failed to write file in sandbox (path={sandbox_path}): {type(e).__name__}: {e}"
        else:
            # Native sandbox or no sandbox — use local filesystem
            try:
                file_path = _resolve_path(
                    path, self._workspace, self._allowed_dir, self._sandbox_manager
                )
                # Snapshot original content before first write (enables non-git diff/revert)
                snap_ok = _maybe_snapshot(file_path, snapshot_dir=self._snapshot_dir)
                file_path.parent.mkdir(parents=True, exist_ok=True)
                file_path.write_text(content, encoding="utf-8")
                result = f"Successfully wrote {len(content)} bytes to {file_path}"
                if not snap_ok:
                    _log.warning("Snapshot failed for %s — revert will not be available", file_path)
                return result
            except PermissionError as e:
                return f"Error: Permission denied: {e}"
            except Exception as e:
                return f"Error writing file: {type(e).__name__}: {e}"


class EditFileTool(Tool):
    """Tool to edit a file by replacing text — works with local or sandbox filesystems."""

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        snapshot_dir: Path | None = None,
        sandbox_manager=None,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._snapshot_dir = snapshot_dir
        self._sandbox_manager = sandbox_manager

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return "Edit a file by replacing old_text with new_text. The old_text must exist exactly in the file."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The file path to edit"
                },
                "old_text": {
                    "type": "string",
                    "description": "The exact text to find and replace"
                },
                "new_text": {
                    "type": "string",
                    "description": "The text to replace with"
                }
            },
            "required": ["path", "old_text", "new_text"]
        }

    async def execute(self, path: str, old_text: str, new_text: str, **kwargs: Any) -> str:
        _sess_key = kwargs.pop("_session_key", None)
        sandbox = await _ensure_sandbox(self._sandbox_manager, session_key=_sess_key)
        session_ws = _get_session_workspace(self._workspace, sandbox)
        if sandbox is not None and getattr(sandbox, "_use_wsl", False):
            # WSL sandbox — route file operations through the sandbox
            sandbox_path = _resolve_sandbox_path(path, session_ws, sandbox)
            _log.info("edit_file [sandbox]: %s → %s", path, sandbox_path)
            try:
                exists = await _sandbox_file_exists(sandbox, sandbox_path)
            except Exception as e:
                return f"Error: Failed to check file existence in sandbox (path={sandbox_path}): {e}"
            if not exists:
                return f"Error: File not found: {path} (sandbox path: {sandbox_path})"

            try:
                content = await _sandbox_read_file(sandbox, sandbox_path)
            except Exception as e:
                return f"Error: Failed to read file in sandbox for editing (path={sandbox_path}): {type(e).__name__}: {e}"

            if old_text not in content:
                return self._not_found_message(old_text, content, path)

            # Count occurrences
            count = content.count(old_text)
            if count > 1:
                return f"Warning: old_text appears {count} times. Please provide more context to make it unique."

            new_content = content.replace(old_text, new_text, 1)
            try:
                await _sandbox_write_file(sandbox, sandbox_path, new_content)
            except Exception as e:
                return f"Error: Failed to write edited file in sandbox (path={sandbox_path}): {type(e).__name__}: {e}"

            return f"Successfully edited {_sandbox_to_host_path(sandbox_path, self._workspace, sandbox)}"
        else:
            # Native sandbox or no sandbox — use local filesystem
            try:
                file_path = _resolve_path(
                    path, self._workspace, self._allowed_dir, self._sandbox_manager
                )
                if not file_path.exists():
                    return f"Error: File not found: {path}"

                # Snapshot original content before first edit (enables non-git diff/revert)
                snap_ok = _maybe_snapshot(file_path, snapshot_dir=self._snapshot_dir)

                content = file_path.read_text(encoding="utf-8")

                if old_text not in content:
                    return self._not_found_message(old_text, content, path)

                # Count occurrences
                count = content.count(old_text)
                if count > 1:
                    return f"Warning: old_text appears {count} times. Please provide more context to make it unique."

                new_content = content.replace(old_text, new_text, 1)
                file_path.write_text(new_content, encoding="utf-8")

                return f"Successfully edited {file_path}"
            except PermissionError as e:
                return f"Error: Permission denied: {e}"
            except Exception as e:
                return f"Error editing file: {type(e).__name__}: {e}"

    @staticmethod
    def _not_found_message(old_text: str, content: str, path: str) -> str:
        """Build a helpful error when old_text is not found."""
        lines = content.splitlines(keepends=True)
        old_lines = old_text.splitlines(keepends=True)
        window = len(old_lines)

        best_ratio, best_start = 0.0, 0
        for i in range(max(1, len(lines) - window + 1)):
            ratio = difflib.SequenceMatcher(None, old_lines, lines[i : i + window]).ratio()
            if ratio > best_ratio:
                best_ratio, best_start = ratio, i

        if best_ratio > 0.5:
            diff = "\n".join(difflib.SequenceMatcher(
                None, old_lines, lines[best_start : best_start + window]
            ).get_opcodes() if False else difflib.unified_diff(
                old_lines, lines[best_start : best_start + window],
                fromfile="old_text (provided)", tofile=f"{path} (actual, line {best_start + 1})",
                lineterm="",
            ))
            return f"Error: old_text not found in {path}.\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
        return f"Error: old_text not found in {path}. No similar text found. Verify the file content."


class ListDirTool(Tool):
    """Tool to list directory contents — works with local or sandbox filesystems."""

    def __init__(
        self,
        workspace: Path | None = None,
        allowed_dir: Path | None = None,
        sandbox_manager=None,
    ):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._sandbox_manager = sandbox_manager

    @property
    def name(self) -> str:
        return "list_dir"

    @property
    def description(self) -> str:
        return "List the contents of a directory."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "The directory path to list"
                }
            },
            "required": ["path"]
        }

    async def execute(self, path: str, **kwargs: Any) -> str:
        _sess_key = kwargs.pop("_session_key", None)
        sandbox = await _ensure_sandbox(self._sandbox_manager, session_key=_sess_key)
        session_ws = _get_session_workspace(self._workspace, sandbox)
        if sandbox is not None and getattr(sandbox, "_use_wsl", False):
            # WSL sandbox — route file operations through the sandbox
            sandbox_path = _resolve_sandbox_path(path, session_ws, sandbox)
            _log.info("list_dir [sandbox]: %s → %s", path, sandbox_path)
            try:
                exists = await _sandbox_dir_exists(sandbox, sandbox_path)
            except Exception as e:
                return f"Error: Failed to check directory existence in sandbox (path={sandbox_path}): {e}"
            if not exists:
                return f"Error: Directory not found: {path} (sandbox path: {sandbox_path})"
            try:
                content = await _sandbox_list_dir(sandbox, sandbox_path)
            except IOError as e:
                return f"Error: Failed to list directory in sandbox (path={sandbox_path}): {e}"
            except Exception as e:
                return f"Error: Failed to list directory in sandbox (path={sandbox_path}): {type(e).__name__}: {e}"
            if not content.strip():
                return f"Directory {path} is empty"
            return content
        else:
            # Native sandbox or no sandbox — use local filesystem
            try:
                dir_path = _resolve_path(
                    path, self._workspace, self._allowed_dir, self._sandbox_manager
                )
                if not dir_path.exists():
                    return f"Error: Directory not found: {path}"
                if not dir_path.is_dir():
                    return f"Error: Not a directory: {path}"

                items = []
                for item in sorted(dir_path.iterdir()):
                    prefix = "dir " if item.is_dir() else "     "
                    items.append(f"{prefix}{item.name}")

                if not items:
                    return f"Directory {path} is empty"

                return "\n".join(items)
            except PermissionError as e:
                return f"Error: Permission denied: {e}"
            except Exception as e:
                return f"Error listing directory: {type(e).__name__}: {e}"
