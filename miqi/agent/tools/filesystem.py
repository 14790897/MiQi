"""File system tools: read, write, edit."""

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
    d = Path.home() / ".miqi" / "snapshots"
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


def _resolve_path(path: str, workspace: Path | None = None, allowed_dir: Path | None = None) -> Path:
    """Resolve path against workspace (if relative) and enforce directory restriction."""
    p = Path(path).expanduser()
    if not p.is_absolute() and workspace:
        p = workspace / p
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


class ReadFileTool(Tool):
    """Tool to read file contents."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

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
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
            if not file_path.exists():
                return f"Error: File not found: {path}"
            if not file_path.is_file():
                return f"Error: Not a file: {path}"

            content = file_path.read_text(encoding="utf-8")
            return content
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error reading file: {str(e)}"


class WriteFileTool(Tool):
    """Tool to write content to a file."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None, snapshot_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._snapshot_dir = snapshot_dir

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
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
            # Snapshot original content before first write (enables non-git diff/revert)
            snap_ok = _maybe_snapshot(file_path, snapshot_dir=self._snapshot_dir)
            file_path.parent.mkdir(parents=True, exist_ok=True)
            file_path.write_text(content, encoding="utf-8")
            result = f"Successfully wrote {len(content)} bytes to {file_path}"
            if not snap_ok:
                _log.warning("Snapshot failed for %s — revert will not be available", file_path)
            return result
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error writing file: {str(e)}"


class EditFileTool(Tool):
    """Tool to edit a file by replacing text."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None, snapshot_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir
        self._snapshot_dir = snapshot_dir

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
        try:
            file_path = _resolve_path(path, self._workspace, self._allowed_dir)
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
            return f"Error: {e}"
        except Exception as e:
            return f"Error editing file: {str(e)}"

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
            diff = "\n".join(difflib.unified_diff(
                old_lines, lines[best_start : best_start + window],
                fromfile="old_text (provided)", tofile=f"{path} (actual, line {best_start + 1})",
                lineterm="",
            ))
            return f"Error: old_text not found in {path}.\nBest match ({best_ratio:.0%} similar) at line {best_start + 1}:\n{diff}"
        return f"Error: old_text not found in {path}. No similar text found. Verify the file content."


class ListDirTool(Tool):
    """Tool to list directory contents."""

    def __init__(self, workspace: Path | None = None, allowed_dir: Path | None = None):
        self._workspace = workspace
        self._allowed_dir = allowed_dir

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
        try:
            dir_path = _resolve_path(path, self._workspace, self._allowed_dir)
            if not dir_path.exists():
                return f"Error: Directory not found: {path}"
            if not dir_path.is_dir():
                return f"Error: Not a directory: {path}"

            items = []
            for item in sorted(dir_path.iterdir()):
                prefix = "📁 " if item.is_dir() else "📄 "
                items.append(f"{prefix}{item.name}")

            if not items:
                return f"Directory {path} is empty"

            return "\n".join(items)
        except PermissionError as e:
            return f"Error: {e}"
        except Exception as e:
            return f"Error listing directory: {str(e)}"
