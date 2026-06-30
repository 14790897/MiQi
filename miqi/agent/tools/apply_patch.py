"""Unified-diff patch parser and application tool.

Implements a Codex-style ``apply_patch`` tool that applies a multi-file,
multi-hunk unified diff in one call.
"""

from __future__ import annotations

import re as _re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from miqi.agent.tools.base import Tool
from miqi.agent.tools.filesystem import (
    _get_active_sandbox,
    _maybe_snapshot,
    _resolve_path,
    _resolve_sandbox_path,
    _sandbox_file_exists,
    _sandbox_read_file,
    _sandbox_write_file,
)


class PatchParseError(Exception):
    """Raised when a unified diff cannot be parsed."""


class PatchApplyError(Exception):
    """Raised when a patch cannot be applied to file content."""


@dataclass
class Hunk:
    """One hunk from a unified diff."""

    old_start: int
    old_count: int
    new_start: int
    new_count: int
    lines: list[str]  # each prefixed ' ', '-', or '+'


@dataclass
class FilePatch:
    """A patch for a single file, composed of one or more hunks."""

    path: str
    hunks: list[Hunk]


_HUNK_RE = _re.compile(
    r"^@@\s+-(?P<old_start>\d+)(?:,(?P<old_count>\d+))?"
    r"\s+\+(?P<new_start>\d+)(?:,(?P<new_count>\d+))?"
    r"\s+@@(?P<comment>.*)$"
)


def _strip_prefix(path: str) -> str:
    """Strip 'a/' or 'b/' prefix used by unified diff file headers."""
    if path.startswith("a/") or path.startswith("b/"):
        return path[2:]
    return path


def parse_patch(text: str) -> list[FilePatch]:
    """Parse a unified diff into per-file hunk sets.

    Raises ``PatchParseError`` on malformed input.
    """
    files: list[FilePatch] = []
    lines = text.splitlines()
    i = 0
    n = len(lines)

    while i < n:
        # Skip blank lines between file sections
        if lines[i].strip() == "":
            i += 1
            continue

        if not lines[i].startswith("--- "):
            raise PatchParseError(f"Expected '--- ' file header at line {i + 1}")

        old_path = lines[i][4:].strip()
        i += 1

        if i >= n or not lines[i].startswith("+++ "):
            raise PatchParseError(f"Expected '+++ ' file header after line {i}")

        new_path = lines[i][4:].strip()
        i += 1

        # Prefer the new path; strip a/ or b/ prefix
        path = _strip_prefix(new_path) or _strip_prefix(old_path)

        hunks: list[Hunk] = []

        while i < n:
            line = lines[i]
            # A hunk header starts a new hunk; a file header ends this file
            if line.startswith("--- "):
                break
            if line.startswith("+++ "):
                # Should not appear except right after ---; treat as file header
                break

            if not line.startswith("@@"):
                raise PatchParseError(
                    f"Expected hunk header at line {i + 1}, got: {line!r}"
                )

            m = _HUNK_RE.match(line)
            if not m:
                raise PatchParseError(f"Malformed hunk header at line {i + 1}: {line!r}")

            old_start = int(m.group("old_start"))
            old_count = int(m.group("old_count") or "1")
            new_start = int(m.group("new_start"))
            new_count = int(m.group("new_count") or "1")

            i += 1
            hunk_lines: list[str] = []

            while i < n:
                inner = lines[i]
                if inner.startswith("@@") or inner.startswith("--- "):
                    break
                # Unified diff lines begin with ' ', '-', '+', or are empty context
                if inner == "":
                    # Treat bare empty line as context line (single space)
                    hunk_lines.append(" ")
                elif inner[0] in " -+":
                    hunk_lines.append(inner)
                elif inner.startswith("\\"):
                    # "\ No newline at end of file" marker — ignore
                    pass
                else:
                    raise PatchParseError(
                        f"Unexpected line in hunk at line {i + 1}: {inner!r}"
                    )
                i += 1

            hunks.append(
                Hunk(
                    old_start=old_start,
                    old_count=old_count,
                    new_start=new_start,
                    new_count=new_count,
                    lines=hunk_lines,
                )
            )

        if not hunks:
            raise PatchParseError(f"No hunks found for file {path!r}")

        files.append(FilePatch(path=path, hunks=hunks))

    if not files:
        raise PatchParseError("No file headers found in patch")

    return files


def _split_lines_keepends(text: str) -> list[str]:
    """Split text into lines while preserving line endings and final no-newline."""
    if text == "":
        return []
    lines = text.splitlines(keepends=True)
    if not text.endswith("\n"):
        # Last element from splitlines(keepends=True) has no newline; keep it.
        return lines
    return lines


def _find_hunk_position(
    lines: list[str], hunk: Hunk, offset: int
) -> tuple[int, list[str]]:
    """Find where to apply a hunk, allowing small offset fuzz if needed.

    Returns (position, reconstructed old_lines_for_context) or raises PatchApplyError.
    """
    context: list[str] = []
    for raw in hunk.lines:
        prefix = raw[0] if raw else " "
        body = raw[1:]
        if prefix == "+":
            continue
        if prefix in (" ", "-"):
            context.append(body)

    target_index = hunk.old_start - 1 + offset

    # Exact match attempt
    if _match_at(lines, context, target_index):
        return target_index, context

    # Small fuzz search around target index
    for delta in range(1, 6):
        for candidate in (target_index - delta, target_index + delta):
            if candidate < 0 or candidate > len(lines) - len(context):
                continue
            if _match_at(lines, context, candidate):
                return candidate, context

    raise PatchApplyError(
        f"Could not apply hunk at line {hunk.old_start} for {context!r}"
    )


def _match_at(lines: list[str], context: list[str], start: int) -> bool:
    """Check whether context matches lines starting at start (0-based)."""
    if start < 0 or start + len(context) > len(lines):
        return False
    for idx, expected in enumerate(context):
        actual = lines[start + idx]
        # Compare without trailing newline
        if actual.rstrip("\n") != expected:
            return False
    return True


def apply_file_patch(original: str, file_patch: FilePatch) -> str:
    """Apply a parsed file patch to original content.

    Raises ``PatchApplyError`` if context does not match.
    Preserves trailing newline behavior of the original content.
    """
    lines = _split_lines_keepends(original)
    had_trailing_newline = original.endswith("\n")

    # Strip line endings for easier manipulation; re-apply at the end.
    bare = [ln.rstrip("\n") for ln in lines]

    offset = 0
    for hunk in file_patch.hunks:
        position, context = _find_hunk_position(bare, hunk, offset)

        # Build replacement lines for this hunk
        replacement: list[str] = []
        for raw in hunk.lines:
            prefix = raw[0] if raw else " "
            body = raw[1:]
            if prefix == " ":
                replacement.append(body)
            elif prefix == "+":
                replacement.append(body)
            elif prefix == "-":
                continue

        # Remove old context lines from bare
        del bare[position : position + len(context)]
        # Insert replacement
        for idx, rep_line in enumerate(replacement):
            bare.insert(position + idx, rep_line)

        offset = (position + len(replacement)) - (hunk.new_start - 1)

    # Reconstruct text
    if not bare and not had_trailing_newline:
        return ""
    if had_trailing_newline:
        return "\n".join(bare) + "\n"
    return "\n".join(bare)


class ApplyPatchTool(Tool):
    """Tool to apply a unified-diff patch to one or more files."""

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
        return "apply_patch"

    @property
    def description(self) -> str:
        return (
            "Apply a unified-diff patch (one or more files, multiple hunks). "
            "Use for multi-line or multi-file edits; use edit_file for a single replacement."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "patch": {
                    "type": "string",
                    "description": "The unified diff body to apply",
                }
            },
            "required": ["patch"],
        }

    async def execute(self, **kwargs: Any) -> str:  # type: ignore[override]
        patch = kwargs.get("patch", "")
        if not isinstance(patch, str) or not patch:
            return "Error: Missing required parameter 'patch'"
        try:
            file_patches = parse_patch(patch)
        except PatchParseError as e:
            return f"Error: Invalid patch: {e}"

        changed: list[str] = []
        sandbox = _get_active_sandbox(self._sandbox_manager)

        for fp in file_patches:
            try:
                result = await self._apply_one_file(fp, sandbox)
            except PatchApplyError as e:
                return f"Error applying patch to {fp.path}: {e}"
            except PermissionError as e:
                return f"Error: Permission denied: {e}"
            except Exception as e:
                return f"Error applying patch to {fp.path}: {type(e).__name__}: {e}"
            if result is not None:
                changed.append(fp.path)

        if not changed:
            return "No files changed"
        return f"Applied patch to: {', '.join(changed)}"

    async def _apply_one_file(self, file_patch: FilePatch, sandbox):
        path = file_patch.path

        if sandbox is not None and getattr(sandbox, "_use_wsl", False):
            sandbox_path = _resolve_sandbox_path(path, self._workspace, sandbox)
            _log.info("apply_patch [sandbox]: %s → %s", path, sandbox_path)

            try:
                exists = await _sandbox_file_exists(sandbox, sandbox_path)
            except Exception as e:
                raise IOError(f"Cannot check file existence in sandbox: {e}") from e

            if not exists:
                # Treat missing file as empty
                original = ""
            else:
                try:
                    original = await _sandbox_read_file(sandbox, sandbox_path)
                except Exception as e:
                    raise IOError(f"Cannot read file in sandbox: {e}") from e

            new_content = apply_file_patch(original, file_patch)

            try:
                await _sandbox_write_file(sandbox, sandbox_path, new_content)
            except Exception as e:
                raise IOError(f"Cannot write file in sandbox: {e}") from e

            return sandbox_path

        # Native / no sandbox
        file_path = _resolve_path(
            path, self._workspace, self._allowed_dir, self._sandbox_manager
        )
        snap_ok = _maybe_snapshot(file_path, snapshot_dir=self._snapshot_dir)

        if file_path.exists():
            original = file_path.read_text(encoding="utf-8")
        else:
            original = ""

        new_content = apply_file_patch(original, file_patch)

        file_path.parent.mkdir(parents=True, exist_ok=True)
        file_path.write_text(new_content, encoding="utf-8")

        if not snap_ok:
            _log.warning(
                "Snapshot failed for %s — revert will not be available", file_path
            )
        return str(file_path)


# Deferred logger to avoid circular import concerns
import logging as _logging  # noqa: E402

_log = _logging.getLogger(__name__)
