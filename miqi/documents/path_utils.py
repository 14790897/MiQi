"""Shared path-resolution helpers for office document tools (docx/pptx/xlsx/pdf).

All office write/read tools are registered with the per-session files
directory as both *workspace* and *allowed_dir* (see
``tool_registry_factory._write_workspace``).  Relative paths therefore
resolve against the **session files root**
(``<workspace>/sessions/<session_key>/files``).

The agent sometimes passes paths that were written relative to the
*workspace base* (the root containing ``sessions/<key>/files/...``), e.g.
``sessions/desktop_xxx/files/_ai_pest_run/step7_report/report.pdf``.
Naively joining that onto the session files root produces a nested
``files/sessions/desktop_xxx/files/...`` location (issue #806).
``resolve_output_path`` detects this prefix for the *current* session and
normalizes it away; prefixes that point at *another* session are rejected.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any


def raw_output_path(kwargs: dict[str, Any]) -> str:
    """Extract the raw output path from tool kwargs (filename / file_path / path)."""
    return str(
        kwargs.get("filename")
        or kwargs.get("file_path")
        or kwargs.get("path")
        or ""
    )


def ensure_suffix(path: Path, suffix: str) -> Path:
    """Append *suffix* (e.g. ``.pdf``) unless the path already ends with it."""
    if not path.name or path.name in {".", ".."}:
        raise ValueError("必须提供输出文件名")
    if path.suffix.lower() == suffix:
        return path
    return path.with_suffix(suffix)


def enforce_boundary(path: Path, allowed_dir: Path | None, workspace: Path | None) -> None:
    """Raise PermissionError if *path* resolves outside the effective boundary."""
    effective_dir = allowed_dir or workspace
    if effective_dir is None:
        return
    try:
        path.resolve().relative_to(effective_dir.resolve())
    except ValueError:
        raise PermissionError(
            f"Path '{path}' resolves outside allowed directory '{effective_dir}'"
        )


def _session_layout(workspace: Path) -> tuple[Path, str] | None:
    """If *workspace* is ``<base>/sessions/<key>/files``, return (base, key)."""
    try:
        if workspace.name == "files" and workspace.parent.parent.name == "sessions":
            return workspace.parent.parent.parent, workspace.parent.name
    except Exception:  # pragma: no cover - defensive
        pass
    return None


def _normalize_session_prefixed(rel: Path, workspace: Path) -> Path:
    """Resolve a workspace-base-relative path against the session files root.

    ``rel`` starts with ``sessions/<key>/files/...``:

    - ``key`` is the current session key: strip the prefix so the file lands
      in the session files root instead of being nested under it (#806).
    - ``key`` is another session: reject — sessions are isolated.
    - workspace is not session-structured: return None (caller falls back to
      plain ``workspace / rel`` joining).
    """
    layout = _session_layout(workspace)
    if layout is None:
        return None
    base, current_key = layout
    parts = list(rel.parts)
    if len(parts) < 3 or parts[0].lower() != "sessions" or parts[2].lower() != "files":
        return None
    other_key = parts[1]
    if other_key != current_key:
        raise PermissionError(
            f"Path '{rel}' 指向其他会话（{other_key}）的目录；"
            f"只能写入当前会话 files 目录（{workspace}）"
        )
    candidate = base.joinpath(*parts)
    # Defense-in-depth: the normalized candidate must stay inside the
    # session files root (guards against ".." escaping the prefix).
    try:
        candidate.resolve().relative_to(workspace.resolve())
    except ValueError:
        raise PermissionError(
            f"Path '{rel}' escapes the session files root '{workspace}'"
        )
    return candidate


def resolve_output_path(
    file_path: str,
    workspace: Path | None,
    allowed_dir: Path | None,
) -> Path:
    """Resolve an output path and enforce workspace/directory bounds.

    Path semantics (documented for agents):

    - Relative paths resolve against *workspace* — for session-scoped tools
      that is the **session files root**
      (``<workspace_base>/sessions/<key>/files``).
    - Paths starting with ``sessions/<key>/files/`` were written relative to
      the **workspace base**.  When ``<key>`` is the current session the
      prefix is stripped so the file lands in the session files root instead
      of being nested under it (#806).  Prefixes pointing at another session
      are rejected.
    - Absolute paths outside the effective boundary are rejected.

    Raises:
        PermissionError: if the resolved path is outside the effective
            boundary, or points into another session's directory.
    """
    # Normalize backslashes so `sessions\key\files\...` style paths (as
    # emitted by the agent on Windows) parse correctly on every platform.
    raw = file_path.replace("\\", "/")
    # Strip a single leading separator ONLY for backslash-rooted input:
    # `\sessions\key\files\...` (Windows rooted-relative) is equivalent to
    # `sessions/key/files/...`.  A forward-slash leading path (`/home/...`)
    # is a genuine POSIX absolute path and MUST be preserved; UNC
    # (`//server/share`) is preserved too.
    if file_path.startswith("\\") and raw.startswith("/"):
        raw = raw[1:]
    p = Path(raw).expanduser()
    if not p.is_absolute() and workspace is not None:
        normalized = _normalize_session_prefixed(p, workspace)
        p = normalized if normalized is not None else workspace / p
    resolved = p.resolve()

    effective_dir = allowed_dir
    if effective_dir is None and workspace is not None:
        effective_dir = workspace.resolve()

    if effective_dir is not None:
        try:
            resolved.relative_to(effective_dir.resolve())
        except ValueError:
            raise PermissionError(
                f"Path '{file_path}' resolves outside allowed directory "
                f"'{effective_dir}'（相对路径基准：会话 files 根目录，即 '{workspace}'）"
            )
    return resolved
