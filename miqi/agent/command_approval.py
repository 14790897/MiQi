"""Dangerous command approval system, ported from Hermes Agent's tools/approval.py.

This module is the single source of truth for dangerous command detection in MiQi:
  - Pattern detection (DANGEROUS_PATTERNS, detect_dangerous_command)
  - Per-session approval state (thread-safe)
  - Approval prompting (CLI interactive: once/session/always/deny)
  - Permanent allowlist persistence via config

Key differences from Hermes:
  - No Gateway blocking queue (MiQi has no gateway mode)
  - No Smart Approval (no auxiliary LLM client)
  - No Tirith security scanner integration
  - Simpler session-key scheme (uses MiQi session keys directly)
"""
from __future__ import annotations

import logging
import os
import re
import sys
import threading
import unicodedata
from typing import Optional

logger = logging.getLogger(__name__)

# ── Sensitive write target patterns ───────────────────────────────────────
_SSH_SENSITIVE_PATH = r'(?:~|\$home|\$\{home\})/\.ssh(?:/|$)'
_SENSITIVE_WRITE_TARGET = rf'(?:/etc/|/dev/sd|{_SSH_SENSITIVE_PATH})'

# ── Dangerous command patterns (39 patterns, ported from Hermes approval.py) ──
DANGEROUS_PATTERNS: list[tuple[str, str]] = [
    (r'\brm\s+(-[^\s]*\s+)*/', "delete in root path"),
    (r'\brm\s+-[^\s]*r', "recursive delete"),
    (r'\brm\s+--recursive\b', "recursive delete (long flag)"),
    (r'\bchmod\s+(-[^\s]*\s+)*(777|666|o\+[rwx]*w|a\+[rwx]*w)\b', "world/other-writable permissions"),
    (r'\bchmod\s+--recursive\b.*(777|666|o\+[rwx]*w|a\+[rwx]*w)', "recursive world/other-writable (long flag)"),
    (r'\bchown\s+(-[^\s]*)?R\s+root', "recursive chown to root"),
    (r'\bchown\s+--recursive\b.*root', "recursive chown to root (long flag)"),
    (r'\bmkfs\b', "format filesystem"),
    (r'\bdd\s+.*if=', "disk copy"),
    (r'>\s*/dev/sd', "write to block device"),
    (r'\bDROP\s+(TABLE|DATABASE)\b', "SQL DROP"),
    (r'\bDELETE\s+FROM\b(?!.*\bWHERE\b)', "SQL DELETE without WHERE"),
    (r'\bTRUNCATE\s+(TABLE)?\s*\w', "SQL TRUNCATE"),
    (r'>\s*/etc/', "overwrite system config"),
    (r'\bsystemctl\s+(stop|disable|mask)\b', "stop/disable system service"),
    (r'\bkill\s+-9\s+-1\b', "kill all processes"),
    (r'\bpkill\s+-9\b', "force kill processes"),
    (r':\(\)\s*\{\s*:\s*\|\s*:\s*&\s*\}\s*;\s*:', "fork bomb"),
    (r'\b(bash|sh|zsh|ksh)\s+-[^\s]*c(\s+|$)', "shell command via -c/-lc flag"),
    (r'\b(python[23]?|perl|ruby|node)\s+-[ec]\s+', "script execution via -e/-c flag"),
    (r'\b(curl|wget)\b.*\|\s*(ba)?sh\b', "pipe remote content to shell"),
    (r'\b(bash|sh|zsh|ksh)\s+<\s*<?\s*\(\s*(curl|wget)\b', "execute remote script via process substitution"),
    (rf'\btee\b.*["\']?{_SENSITIVE_WRITE_TARGET}', "overwrite system file via tee"),
    (rf'>>?\s*["\']?{_SENSITIVE_WRITE_TARGET}', "overwrite system file via redirection"),
    (r'\bxargs\s+.*\brm\b', "xargs with rm"),
    (r'\bfind\b.*-exec\s+(/\S*/)?rm\b', "find -exec rm"),
    (r'\bfind\b.*-delete\b', "find -delete"),
    (r'\b(cp|mv|install)\b.*\s/etc/', "copy/move file into /etc/"),
    (r'\bsed\s+-[^\s]*i.*\s/etc/', "in-place edit of system config"),
    (r'\bsed\s+--in-place\b.*\s/etc/', "in-place edit of system config (long flag)"),
    (r'\b(python[23]?|perl|ruby|node)\s+<<', "script execution via heredoc"),
    (r'\bgit\s+reset\s+--hard\b', "git reset --hard (destroys uncommitted changes)"),
    (r'\bgit\s+push\b.*--force\b', "git force push (rewrites remote history)"),
    (r'\bgit\s+push\b.*-f\b', "git force push short flag (rewrites remote history)"),
    (r'\bgit\s+clean\s+-[^\s]*f', "git clean with force (deletes untracked files)"),
    (r'\bgit\s+branch\s+-D\b', "git branch force delete"),
    (r'\bchmod\s+\+x\b.*[;&|]+\s*\./', "chmod +x followed by immediate execution"),
    (r'\bkill\b.*\$\(\s*pgrep\b', "kill process via pgrep expansion"),
    (r'\bkill\b.*`\s*pgrep\b', "kill process via backtick pgrep expansion"),
]

# ── Per-session state (thread-safe) ───────────────────────────────────────
_lock = threading.Lock()
_session_approved: dict[str, set[str]] = {}   # session_key → set of approved pattern descriptions
_permanent_approved: set[str] = set()


def _normalize_command(command: str) -> str:
    """Normalize command string to prevent Unicode obfuscation bypass."""
    command = re.sub(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])', '', command)  # strip ANSI
    command = command.replace('\x00', '')
    command = unicodedata.normalize('NFKC', command)
    return command


def detect_dangerous_command(command: str) -> tuple[bool, Optional[str], Optional[str]]:
    """Check if a command matches any dangerous pattern.

    Returns:
        (is_dangerous, pattern_description, description) or (False, None, None)
    """
    normalized = _normalize_command(command).lower()
    for pattern, description in DANGEROUS_PATTERNS:
        if re.search(pattern, normalized, re.IGNORECASE | re.DOTALL):
            return (True, description, description)
    return (False, None, None)


def is_approved(session_key: str, pattern_key: str) -> bool:
    """Check if a pattern is approved for this session or permanently."""
    with _lock:
        if pattern_key in _permanent_approved:
            return True
        return pattern_key in _session_approved.get(session_key, set())


def approve_session(session_key: str, pattern_key: str) -> None:
    """Approve a pattern for this session only."""
    with _lock:
        _session_approved.setdefault(session_key, set()).add(pattern_key)


def approve_permanent(pattern_key: str) -> None:
    """Add a pattern to the permanent allowlist."""
    with _lock:
        _permanent_approved.add(pattern_key)


def clear_session(session_key: str) -> None:
    """Clear all approvals for a session (on /new or session end)."""
    with _lock:
        _session_approved.pop(session_key, None)


def load_permanent_allowlist(patterns: set[str]) -> None:
    """Bulk-load permanent allowlist (called from config loader)."""
    with _lock:
        _permanent_approved.update(patterns)


def get_permanent_allowlist() -> set[str]:
    """Return current permanent allowlist (for config persistence)."""
    with _lock:
        return set(_permanent_approved)


def check_dangerous_command(
    command: str,
    session_key: str = "",
    approval_callback=None,
) -> dict:
    """Main entry point: check if command is dangerous and handle approval.

    Args:
        command: The shell command to check.
        session_key: Session identifier for per-session approvals.
        approval_callback: Optional callback for custom approval UI.
            Signature: (command, description, *, allow_permanent=True) -> str
            Returns: 'once' | 'session' | 'always' | 'deny'

    Returns:
        {"approved": bool, "message": str | None, ...}
    """
    is_dangerous, pattern_key, description = detect_dangerous_command(command)
    if not is_dangerous:
        return {"approved": True, "message": None}

    if is_approved(session_key, pattern_key):
        return {"approved": True, "message": None}

    # Non-interactive mode: approve (matches Hermes behaviour for non-CLI/gateway)
    is_cli = os.getenv("MIQI_INTERACTIVE")
    if not is_cli:
        return {"approved": True, "message": None}

    # CLI interactive approval
    choice = prompt_dangerous_approval(
        command, description,
        approval_callback=approval_callback,
    )

    if choice == "deny":
        return {
            "approved": False,
            "message": (
                f"BLOCKED: User denied this potentially dangerous command "
                f"(matched '{description}' pattern). Do NOT retry this command."
            ),
            "pattern_key": pattern_key,
            "description": description,
        }

    if choice == "session":
        approve_session(session_key, pattern_key)
    elif choice == "always":
        approve_session(session_key, pattern_key)
        approve_permanent(pattern_key)
        _save_permanent_allowlist()

    return {"approved": True, "message": None}


def prompt_dangerous_approval(
    command: str,
    description: str,
    timeout_seconds: int = 60,
    allow_permanent: bool = True,
    approval_callback=None,
) -> str:
    """Prompt the user to approve a dangerous command (CLI only).

    Returns: 'once' | 'session' | 'always' | 'deny'
    """
    if approval_callback is not None:
        try:
            return approval_callback(command, description, allow_permanent=allow_permanent)
        except Exception as exc:
            logger.error("Approval callback failed: %s", exc)
            return "deny"

    os.environ["MIQI_SPINNER_PAUSE"] = "1"
    try:
        while True:
            print()
            print(f"  ⚠️  DANGEROUS COMMAND: {description}")
            print(f"      {command}")
            print()
            if allow_permanent:
                print("      [o]nce  |  [s]ession  |  [a]lways  |  [d]eny")
            else:
                print("      [o]nce  |  [s]ession  |  [d]eny")
            print()
            sys.stdout.flush()

            result: dict[str, str] = {"choice": ""}

            def _get_input() -> None:
                try:
                    prompt_str = "      Choice [o/s/a/D]: " if allow_permanent else "      Choice [o/s/D]: "
                    result["choice"] = input(prompt_str).strip().lower()
                except (EOFError, OSError):
                    result["choice"] = ""

            thread = threading.Thread(target=_get_input, daemon=True)
            thread.start()
            thread.join(timeout=timeout_seconds)

            if thread.is_alive():
                print("\n      ⏱ Timeout - denying command")
                return "deny"

            choice = result["choice"]
            if choice in ("o", "once"):
                print("      ✓ Allowed once")
                return "once"
            elif choice in ("s", "session"):
                print("      ✓ Allowed for this session")
                return "session"
            elif choice in ("a", "always"):
                if not allow_permanent:
                    print("      ✓ Allowed for this session")
                    return "session"
                print("      ✓ Added to permanent allowlist")
                return "always"
            else:
                print("      ✗ Denied")
                return "deny"

    except (EOFError, KeyboardInterrupt):
        print("\n      ✗ Cancelled")
        return "deny"
    finally:
        os.environ.pop("MIQI_SPINNER_PAUSE", None)
        print()
        sys.stdout.flush()


def _save_permanent_allowlist() -> None:
    """Persist permanent allowlist to config (best-effort)."""
    try:
        from miqi.config.loader import load_config, save_config_allowlist
        patterns = get_permanent_allowlist()
        save_config_allowlist(patterns)
    except Exception as exc:
        logger.warning("Could not save permanent allowlist: %s", exc)
