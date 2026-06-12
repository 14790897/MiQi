"""File artifact handlers for AppServer dispatch.

Phase 30: Migrates files.tree, files.read, files.write, files.delete,
files.diff, files.revert, and files.accept from bridge legacy handlers
to AppServer async handlers with client-scoped ownership enforcement.

Key semantics:
- All file operations (except files.tree without session_key) require
  client_id and verify session ownership via SessionManager.
- files.tree: workspace tree only when no session_key; session-scoped
  tree when session_key is provided and owned by client.
- files.read/write/delete: session ownership required for session-scoped
  paths; workspace-only paths are OK without ownership.
- files.diff/revert/accept: session ownership required; snapshots are
  resolved through the ownership-aware path resolver.
- Path resolution is centralized through _resolve_session_files_path()
  and _resolve_session_snapshot_dir() — no raw session_key concatenation
  in handler code.
- Bug fixes:
  1. _remove_tracked_file: was undefined — uses SessionManager.remove_tracked_file
  2. _reset_tracked_file_op: was bypassing ownership — now passes client_id
  3. files.write: tracked_files write was bypassing ownership — now passes client_id
"""

from __future__ import annotations

import difflib
from pathlib import Path
from typing import Any

from loguru import logger

from miqi.agent.tools.filesystem import (
    _delete_snapshot,
    _maybe_snapshot,
    _read_snapshot,
    _restore_snapshot,
    _snapshots_lock,
)
from miqi.runtime.app_server import AppServerError
from miqi.session.manager import OwnershipError
from miqi.utils.helpers import safe_filename


# ── workspace / SessionManager access ──────────────────────────────────────


def _get_workspace_path() -> Path:
    """Get the workspace path from bridge state config."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()
    return config.workspace_path.resolve()


def _get_session_manager() -> Any:
    """Get a SessionManager for the current workspace."""
    import miqi.bridge.server as bridge_module

    state = getattr(bridge_module, "_state", None)
    if state is None:
        raise AppServerError("Bridge state not available", code="INTERNAL")
    config = state.load_config()
    from miqi.session.manager import SessionManager
    return SessionManager(config.workspace_path)


# ── ownership verification ─────────────────────────────────────────────────


def _verify_session_ownership(client_id: str, session_key: str) -> None:
    """Verify that client_id owns session_key.

    Raises AppServerError with:
    - REQUIRES_CLAIM: session is unowned legacy
    - UNAUTHORIZED: session is owned by a different client
    """
    sm = _get_session_manager()
    try:
        sm._verify_ownership_for_mutation(session_key, client_id)
    except OwnershipError as exc:
        raise AppServerError(exc.args[0], code=exc.code) from exc


# ── path resolution ────────────────────────────────────────────────────────


def _resolve_session_files_path(client_id: str, session_key: str) -> Path:
    """Resolve the client-scoped session files directory.

    Verifies session ownership before returning the path.
    Uses the same session directory naming as SessionManager
    (safe_filename(session_key)), gated by ownership verification.
    """
    _verify_session_ownership(client_id, session_key)
    workspace = _get_workspace_path()
    safe_key = safe_filename(session_key.replace(":", "_"))
    files_dir = workspace / "sessions" / safe_key / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    return files_dir


def _resolve_session_snapshot_dir(client_id: str, session_key: str) -> Path:
    """Resolve the client-scoped session snapshot directory.

    Verifies session ownership before returning the path.
    """
    _verify_session_ownership(client_id, session_key)
    workspace = _get_workspace_path()
    safe_key = safe_filename(session_key.replace(":", "_"))
    snap_dir = workspace / "sessions" / safe_key / "snapshots"
    snap_dir.mkdir(parents=True, exist_ok=True)
    return snap_dir


def _validate_file_path(
    file_path: str,
    client_id: str,
    session_key: str | None = None,
) -> Path:
    """Resolve a relative file path with path-traversal protection.

    If session_key is provided:
      1. Verifies ownership via _verify_session_ownership
      2. Resolves against the session-scoped files directory
      3. Falls back to workspace root if the resolved path escapes

    If session_key is None:
      Resolves against workspace root only.

    Blocks absolute paths and path traversal (..).
    """
    workspace = _get_workspace_path()

    if not file_path or file_path.startswith("/") or file_path.startswith("\\"):
        raise AppServerError(
            "Only relative paths are allowed", code="INVALID_PARAMS",
        )

    # Session-scoped path resolution
    if session_key:
        try:
            session_files = _resolve_session_files_path(client_id, session_key)
        except AppServerError:
            # If ownership fails, still let the caller handle it explicitly
            raise
        resolved = (session_files / file_path).resolve()
        if str(resolved).startswith(str(workspace) + str(Path("/"))) or resolved == workspace:
            return resolved
        # If session files dir doesn't contain this path, fall through to workspace

    # Workspace-scoped path resolution
    resolved = (workspace / file_path).resolve()
    if not str(resolved).startswith(str(workspace) + str(Path("/"))) and resolved != workspace:
        raise AppServerError(
            f"Path escapes workspace: {file_path}", code="INVALID_PARAMS",
        )
    return resolved


# ── allowed file types ─────────────────────────────────────────────────────

_ALLOWED_SUFFIXES: set[str] = {
    ".md", ".txt", ".py", ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".js", ".ts", ".tsx", ".jsx", ".css", ".html", ".xml", ".svg",
    ".sh", ".bash", ".zsh", ".ps1", ".bat",
    ".env", ".gitignore", ".dockerignore", ".editorconfig",
    ".csv", ".log", ".lock", ".jsonl",
}

_ALLOWED_NAMES: set[str] = {
    ".gitignore", ".dockerignore", ".editorconfig", ".env",
}

_TREE_SKIP_SUFFIXES: set[str] = {
    ".sqlite", ".sqlite-shm", ".sqlite-wal", ".sqlite-journal",
    ".db", ".db-shm", ".db-wal",
    ".pyc", ".pyo", ".pyd",
    ".so", ".dll", ".dylib", ".exe",
    ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico", ".bmp",
    ".zip", ".tar", ".gz", ".bz2", ".xz", ".7z",
    ".bin", ".dat", ".pkl", ".npz", ".npy", ".h5", ".hdf5",
}

_TEXT_SAFE_SUFFIXES = _ALLOWED_SUFFIXES
_TEXT_SAFE_NAMES = _ALLOWED_NAMES


def _check_text_file_type(resolved: Path) -> None:
    """Raise AppServerError if the file is not a text-like type."""
    if resolved.suffix not in _TEXT_SAFE_SUFFIXES and resolved.name not in _TEXT_SAFE_NAMES:
        raise AppServerError(
            f"File type not supported: {resolved.suffix or resolved.name}",
            code="INVALID_PARAMS",
        )


# ── files.tree ─────────────────────────────────────────────────────────────


def _build_tree(path: Path, relative_to: Path, depth: int = 0, max_depth: int = 6) -> dict:
    """Build a FileNode tree for a directory."""
    node: dict[str, Any] = {
        "name": path.name or str(path),
        "path": str(path.relative_to(relative_to)).replace("\\", "/"),
        "is_dir": path.is_dir(),
    }
    if path.is_dir() and depth < max_depth:
        children = []
        try:
            for child in sorted(path.iterdir(), key=lambda p: (not p.is_dir(), p.name.lower())):
                if child.name.startswith(".") or child.name == "__pycache__":
                    continue
                if child.suffix.lower() in _TREE_SKIP_SUFFIXES:
                    continue
                children.append(_build_tree(child, relative_to, depth + 1, max_depth))
        except PermissionError:
            pass
        node["children"] = children
    return node


async def files_tree_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Build a file tree.

    Without session_key: returns the workspace tree (read-only, low risk).
    With session_key: returns session-scoped file tree after ownership verification.
    """
    workspace = _get_workspace_path()
    session_key = params.get("session_key")

    if session_key:
        # Session-scoped tree: verify ownership first
        _verify_session_ownership(client_id, session_key)
        session_files = _resolve_session_files_path(client_id, session_key)
        if not session_files.exists() or not any(session_files.iterdir()):
            root = {
                "name": session_key,
                "path": ".",
                "is_dir": True,
                "children": [],
            }
        else:
            root = _build_tree(session_files, session_files)
        return {
            "result": {
                "root": root,
                "workspace_path": str(workspace),
                "session_key": session_key,
            },
        }

    # Workspace tree only
    if not workspace.exists():
        return {
            "result": {
                "root": {"name": workspace.name, "path": ".", "is_dir": True, "children": []},
                "workspace_path": str(workspace),
            },
        }
    root = _build_tree(workspace, workspace)
    return {"result": {"root": root, "workspace_path": str(workspace)}}


# ── files.read ─────────────────────────────────────────────────────────────


async def files_read_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Read a text file.

    For session-scoped paths (session_key provided): verifies session ownership.
    For workspace-only paths: no ownership check needed.
    """
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")

    logger.info(
        "[files:read] req={} path={} session_key={} client={}",
        request_id, file_path, session_key, client_id,
    )

    if not file_path:
        raise AppServerError("path is required", code="INVALID_PARAMS")

    try:
        resolved = _validate_file_path(file_path, client_id, session_key)
    except AppServerError:
        raise
    except ValueError as exc:
        raise AppServerError(str(exc), code="INVALID_PARAMS") from exc

    if not resolved.exists():
        raise AppServerError(f"File not found: {file_path}", code="NOT_FOUND")
    if resolved.is_dir():
        raise AppServerError(f"Path is a directory: {file_path}", code="INVALID_PARAMS")

    _check_text_file_type(resolved)

    try:
        content = resolved.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        raise AppServerError(
            "File is not valid UTF-8 text", code="INVALID_PARAMS",
        ) from None
    except Exception as exc:
        raise AppServerError(str(exc), code="INTERNAL") from exc

    logger.info("[files:read] ok path={} size={}", file_path, len(content))
    return {
        "result": {
            "path": file_path,
            "content": content,
            "size": len(content),
        },
    }


# ── files.write ────────────────────────────────────────────────────────────


async def files_write_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Write content to a text file.

    For session-scoped writes: verifies ownership, snapshots before first write,
    and updates tracked_files with client_id (fixing the bug where tracked_files
    write bypassed ownership verification).
    """
    file_path = params.get("path", "").strip()
    content = params.get("content", "")
    session_key = params.get("session_key")

    logger.info(
        "[files:write] req={} path={} size={} session_key={} client={}",
        request_id, file_path, len(content), session_key, client_id,
    )

    if not file_path:
        raise AppServerError("path is required", code="INVALID_PARAMS")

    try:
        resolved = _validate_file_path(file_path, client_id, session_key)
    except AppServerError:
        raise
    except ValueError as exc:
        raise AppServerError(str(exc), code="INVALID_PARAMS") from exc

    _check_text_file_type(resolved)

    # Snapshot original content before first write (enables diff/revert)
    snapshot_dir: Path | None = None
    if session_key:
        snapshot_dir = _resolve_session_snapshot_dir(client_id, session_key)
    _maybe_snapshot(resolved, snapshot_dir=snapshot_dir)

    resolved.parent.mkdir(parents=True, exist_ok=True)
    try:
        resolved.write_text(content, encoding="utf-8")
    except Exception as exc:
        raise AppServerError(str(exc), code="INTERNAL") from exc

    # Update tracked_files with client_id ownership check (BUG FIX A.3)
    if session_key:
        sm = _get_session_manager()
        try:
            sm.save_tracked_file(
                session_key, file_path, op="write", client_id=client_id,
            )
        except OwnershipError as exc:
            raise AppServerError(exc.args[0], code=exc.code) from exc

    logger.info("[files:write] ok path={}", file_path)
    return {"result": {"saved": True, "path": file_path}}


# ── files.delete ───────────────────────────────────────────────────────────


async def files_delete_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Delete a workspace file or empty directory.

    For session-scoped deletes: verifies session ownership.
    """
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")

    logger.info(
        "[files:delete] req={} path={} session_key={} client={}",
        request_id, file_path, session_key, client_id,
    )

    if not file_path:
        raise AppServerError("path is required", code="INVALID_PARAMS")

    try:
        resolved = _validate_file_path(file_path, client_id, session_key)
    except AppServerError:
        raise
    except ValueError as exc:
        raise AppServerError(str(exc), code="INVALID_PARAMS") from exc

    if not resolved.exists():
        raise AppServerError(f"Not found: {file_path}", code="NOT_FOUND")

    workspace = _get_workspace_path()
    if resolved == workspace:
        raise AppServerError("Cannot delete workspace root", code="INVALID_PARAMS")

    if resolved.is_dir():
        if any(resolved.iterdir()):
            raise AppServerError("Directory is not empty", code="INVALID_PARAMS")
        resolved.rmdir()
    else:
        resolved.unlink()

    logger.info("[files:delete] ok path={}", file_path)
    return {"result": {"deleted": True, "path": file_path}}


# ── files.diff ─────────────────────────────────────────────────────────────


async def files_diff_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Diff a file against its pre-session snapshot (no git required).

    Verifies session ownership before accessing snapshots.
    """
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")

    logger.info(
        "[files:diff] req={} path={} session_key={} client={}",
        request_id, file_path, session_key, client_id,
    )

    if not file_path:
        raise AppServerError("path is required", code="INVALID_PARAMS")

    try:
        resolved = _validate_file_path(file_path, client_id, session_key)
    except AppServerError:
        raise
    except ValueError as exc:
        raise AppServerError(str(exc), code="INVALID_PARAMS") from exc

    snapshot_key = str(resolved)

    # Resolve snapshot dir with ownership verification
    snapshot_dir: Path | None = None
    if session_key:
        snapshot_dir = _resolve_session_snapshot_dir(client_id, session_key)

    with _snapshots_lock:
        original_content: str | None = _read_snapshot(snapshot_key, snapshot_dir=snapshot_dir)

    # Fall back to global snapshots dir
    if original_content is None:
        original_content = _read_snapshot(snapshot_key)

    # Read current content
    current_content: str | None = None
    file_exists = resolved.exists()
    if file_exists:
        try:
            current_content = resolved.read_text(encoding="utf-8", errors="replace")
        except Exception as exc:
            logger.info("[files:diff] read current failed: {}", exc)

    # If no snapshot exists, generate a diff showing all content as additions
    if original_content is None:
        if file_exists and current_content is not None and current_content != "":
            logger.info("[files:diff] new file detected for {}", snapshot_key)
            current_lines = current_content.splitlines(keepends=True)
            diff_lines = [
                "--- /dev/null",
                f"+++ b/{file_path}",
            ]
            line_count = len(current_lines)
            diff_lines.append(f"@@ -0,0 +1,{line_count} @@")
            diff_lines.extend("+" + line for line in current_lines)
            diff_text = "\n".join(diff_lines)
            return {
                "result": {
                    "path": file_path,
                    "diff": diff_text,
                    "has_diff": True,
                    "original_content": None,
                    "current_content": current_content,
                    "is_new_file": True,
                },
            }
        logger.info("[files:diff] no snapshot for {}", snapshot_key)
        return {
            "result": {
                "path": file_path,
                "diff": None,
                "has_diff": False,
                "original_content": None,
                "current_content": current_content,
                "error": "No snapshot found — file was not modified in this session",
            },
        }

    # Generate unified diff for modified files
    original_lines = original_content.splitlines(keepends=True)
    current_lines = (current_content or "").splitlines(keepends=True)
    diff_lines = list(difflib.unified_diff(
        original_lines,
        current_lines,
        fromfile=f"a/{file_path}",
        tofile=f"b/{file_path}",
        lineterm="",
    ))
    diff_text = "\n".join(diff_lines) if diff_lines else None
    has_diff = bool(diff_text)
    logger.info("[files:diff] ok has_diff={} lines={} path={}", has_diff, len(diff_lines), file_path)

    return {
        "result": {
            "path": file_path,
            "diff": diff_text,
            "has_diff": has_diff,
            "original_content": original_content,
            "current_content": current_content,
        },
    }


# ── files.revert ───────────────────────────────────────────────────────────


async def files_revert_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Revert a file to its pre-session snapshot (no git required).

    Verifies session ownership before accessing snapshots.
    BUG FIX: Uses SessionManager.remove_tracked_file with client_id instead
    of calling the undefined _remove_tracked_file.
    """
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")

    logger.info(
        "[files:revert] req={} path={} session_key={} client={}",
        request_id, file_path, session_key, client_id,
    )

    if not file_path:
        raise AppServerError("path is required", code="INVALID_PARAMS")

    try:
        resolved = _validate_file_path(file_path, client_id, session_key)
    except AppServerError:
        raise
    except ValueError as exc:
        raise AppServerError(str(exc), code="INVALID_PARAMS") from exc

    snapshot_key = str(resolved)

    # Resolve snapshot dir with ownership verification
    snapshot_dir: Path | None = None
    if session_key:
        snapshot_dir = _resolve_session_snapshot_dir(client_id, session_key)

    with _snapshots_lock:
        has_snapshot = _read_snapshot(snapshot_key, snapshot_dir=snapshot_dir) is not None

    if not has_snapshot:
        # Also check global snapshots dir
        has_snapshot = _read_snapshot(snapshot_key) is not None
        if has_snapshot:
            snapshot_dir = None  # use global dir for restore/delete
            logger.info("[files:revert] found snapshot in global dir for {}", snapshot_key)

    if not has_snapshot:
        raise AppServerError(
            "No snapshot found — cannot revert (file was not modified in this session)",
            code="NOT_FOUND",
        )

    ok = _restore_snapshot(resolved, snapshot_dir=snapshot_dir)
    if not ok:
        raise AppServerError(
            "Revert failed — could not write original content",
            code="INTERNAL",
        )

    # Delete snapshot so the file is treated as clean again
    with _snapshots_lock:
        _delete_snapshot(snapshot_key, snapshot_dir=snapshot_dir)

    # Remove tracked file entry with ownership check (BUG FIX A.1)
    if session_key:
        sm = _get_session_manager()
        try:
            sm.remove_tracked_file(session_key, file_path, client_id=client_id)
        except OwnershipError as exc:
            raise AppServerError(exc.args[0], code=exc.code) from exc

    logger.info("[files:revert] ok path={}", file_path)
    return {"result": {"reverted": True, "path": file_path}}


# ── files.accept ───────────────────────────────────────────────────────────


async def files_accept_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Accept all changes for a file — keep current content, delete snapshot.

    Verifies session ownership before accessing snapshots and tracked_files.
    BUG FIX: Passes client_id to SessionManager.reset_tracked_file_op
    instead of bypassing ownership verification.
    """
    file_path = params.get("path", "").strip()
    session_key = params.get("session_key")

    logger.info(
        "[files:accept] req={} path={} session_key={} client={}",
        request_id, file_path, session_key, client_id,
    )

    if not file_path:
        raise AppServerError("path is required", code="INVALID_PARAMS")

    # Reset tracked file entry with ownership check (BUG FIX A.2)
    if session_key:
        sm = _get_session_manager()
        try:
            sm.reset_tracked_file_op(
                session_key, file_path, op="read", client_id=client_id,
            )
        except OwnershipError as exc:
            raise AppServerError(exc.args[0], code=exc.code) from exc

    try:
        resolved = _validate_file_path(file_path, client_id, session_key)
    except AppServerError:
        # Path validation failed — still report accepted for tracked_files reset
        return {"result": {"accepted": True, "path": file_path}}
    except ValueError:
        return {"result": {"accepted": True, "path": file_path}}

    snapshot_key = str(resolved)

    # Resolve snapshot dir with ownership verification
    snapshot_dir: Path | None = None
    if session_key:
        try:
            snapshot_dir = _resolve_session_snapshot_dir(client_id, session_key)
        except AppServerError:
            snapshot_dir = None

    # Delete snapshot from session dir
    with _snapshots_lock:
        _delete_snapshot(snapshot_key, snapshot_dir=snapshot_dir)

    # Also clean global dir if snapshot landed there
    with _snapshots_lock:
        _delete_snapshot(snapshot_key)

    logger.info("[files:accept] ok path={}", file_path)
    return {"result": {"accepted": True, "path": file_path}}
