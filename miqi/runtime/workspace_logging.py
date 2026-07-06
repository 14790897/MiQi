from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from miqi.utils.helpers import ensure_dir

_REDACT_PATTERNS = [
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|authorization)\s*[:=]\s*([^\s,;]+)"), r"\1=[REDACTED]"),
    (re.compile(r"(?i)\b(api[_-]?key|token|secret|authorization)\b"), "[REDACTED]"),
]

# —— constants ——
_LOG_DIR_NAME = "logs"
_DEFAULT_RETAIN_DAYS = 7
_DEFAULT_MAX_TOTAL_BYTES = 50 * 1024 * 1024  # 50 MB total per log directory
_SINGLE_FILE_PRUNE_LINES = 10_000  # keep last 10k lines when a single file is too large


def _redact_message(message: str) -> str:
    redacted = message
    for pattern, replacement in _REDACT_PATTERNS:
        redacted = pattern.sub(replacement, redacted)
    return redacted


def _today_str() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def get_log_dir(workspace: Path) -> Path:
    """Return (and ensure) the ``workspace/logs/`` directory."""
    return ensure_dir(workspace / _LOG_DIR_NAME)


def get_log_path(workspace: Path, source: str) -> Path:
    """Return the date-based log file path: ``workspace/logs/{source}-{date}.log``."""
    return get_log_dir(workspace) / f"{source}-{_today_str()}.log"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def append_workspace_log(
    workspace: Path | str,
    message: str,
    *,
    level: str = "INFO",
    source: str = "bridge",
    session_key: str | None = None,
) -> Path:
    """Append a redacted log entry to a **date-based** workspace log file.

    Logs are written to ``workspace/logs/{source}-{YYYY-MM-DD}.log``.
    """
    workspace_path = Path(workspace).expanduser().resolve()
    log_path = get_log_path(workspace_path, source)

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    entry = f"[{timestamp}] [{level}] [{source}] {_redact_message(message)}\n"
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(entry)

    _prune_log_file(log_path)
    cleanup_old_logs(workspace_path, retain_days=_DEFAULT_RETAIN_DAYS)
    return log_path


def append_workspace_log_json(workspace: Path | str, payload: dict[str, Any]) -> Path:
    """Append a structured JSON log payload to a **date-based** workspace JSONL file.

    Logs are written to ``workspace/logs/{source}-{YYYY-MM-DD}.jsonl``.
    The *source* is read from ``payload["source"]`` (defaults to ``"bridge"``).
    """
    workspace_path = Path(workspace).expanduser().resolve()
    source = str(payload.get("source", "bridge"))
    log_path = get_log_dir(workspace_path) / f"{source}-{_today_str()}.jsonl"

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    record = {"timestamp": timestamp, **payload}
    record = {k: _redact_message(str(v)) if isinstance(v, str) else v for k, v in record.items()}
    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(record, ensure_ascii=False) + "\n")

    _prune_log_file(log_path)
    cleanup_old_logs(workspace_path, retain_days=_DEFAULT_RETAIN_DAYS)
    return log_path


def cleanup_old_logs(workspace: Path, *, retain_days: int = _DEFAULT_RETAIN_DAYS) -> None:
    """Remove log files older than *retain_days* and enforce total directory size limit.

    This is called automatically after every ``append_workspace_log`` /
    ``append_workspace_log_json`` call, so callers rarely need to invoke it directly.
    """
    log_dir = workspace / _LOG_DIR_NAME
    if not log_dir.exists():
        return

    cutoff_ts = datetime.now(timezone.utc).timestamp() - retain_days * 86400

    for pattern in ["*.log", "*.jsonl"]:
        for log_file in log_dir.glob(pattern):
            try:
                if log_file.stat().st_mtime < cutoff_ts:
                    log_file.unlink()
            except OSError:
                pass

    # After age-based cleanup, also enforce total directory size limit
    _enforce_size_limit(log_dir, max_total_bytes=_DEFAULT_MAX_TOTAL_BYTES)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _prune_log_file(
    log_path: Path,
    *,
    max_bytes: int = _DEFAULT_MAX_TOTAL_BYTES,
    keep_lines: int = _SINGLE_FILE_PRUNE_LINES,
) -> None:
    """Keep only the last *keep_lines* lines if a single log file exceeds *max_bytes*."""
    if not log_path.exists():
        return

    try:
        if log_path.stat().st_size <= max_bytes:
            return
    except OSError:
        return

    try:
        with log_path.open("r", encoding="utf-8") as handle:
            lines = handle.read().splitlines()
    except Exception:
        return

    if len(lines) <= keep_lines:
        return

    kept = lines[-keep_lines:]
    try:
        log_path.write_text("\n".join(kept) + "\n", encoding="utf-8")
    except OSError:
        pass


def _enforce_size_limit(log_dir: Path, *, max_total_bytes: int = _DEFAULT_MAX_TOTAL_BYTES) -> None:
    """If the total size of all log files exceeds *max_total_bytes*, delete the
    oldest files (by modification time) until the limit is satisfied.

    At least one file is always kept to avoid deleting today's active log.
    """
    all_files = sorted(
        [f for f in log_dir.glob("*") if f.is_file()],
        key=lambda f: f.stat().st_mtime if f.exists() else 0.0,
    )

    # Collect file sizes; ignore files that disappeared during iteration
    file_sizes: list[tuple[Path, int]] = []
    total_size = 0
    for f in all_files:
        try:
            sz = f.stat().st_size
        except OSError:
            continue
        file_sizes.append((f, sz))
        total_size += sz

    while total_size > max_total_bytes and len(file_sizes) > 1:
        oldest_path, oldest_size = file_sizes[0]
        try:
            oldest_path.unlink()
        except OSError:
            pass
        total_size -= oldest_size
        file_sizes.pop(0)
