"""Permission policy decision engine.

Consults (in order):
1. Read-only tools → always allow
2. Config-based deny rules
3. Permanent whitelist
4. Falls through to APPROVAL_REQUIRED for dangerous operations
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class PermissionVerdict(str, Enum):
    ALLOW = "allow"
    DENY = "deny"
    APPROVAL_REQUIRED = "approval_required"


@dataclass
class PermissionDecision:
    verdict: PermissionVerdict
    category: str = ""
    description: str = ""
    reason: str = ""
    details: dict[str, Any] = field(default_factory=dict)
    allow_permanent: bool = False


class PermissionEngine:
    """Central permission decision engine."""

    # Read-only tools: auto-allow
    READ_ONLY_TOOLS: frozenset[str] = frozenset({
        "read_file", "list_dir", "web_search", "web_fetch",
        "session_search", "trace_search", "paper_search", "paper_get",
        "docx_read", "pptx_read", "xlsx_read", "memory",
    })

    # Safe shell commands: auto-allow
    SAFE_COMMAND_PREFIXES: tuple[str, ...] = (
        "ls ", "cat ", "head ", "tail ", "wc ", "grep ",
        "find ", "which ", "pwd", "echo ", "date", "whoami",
        "git status", "git log", "git diff", "git branch",
        "git show", "python --version", "node --version",
        "cargo --version", "npm --version", "pip list",
        "poetry --version", "uv --version", "dir ", "type ",
    )

    def __init__(
        self,
        permanent_allowlist: set[str] | None = None,
        deny_patterns: set[str] | None = None,
    ):
        self.permanent_allowlist = permanent_allowlist or set()
        self.deny_patterns = deny_patterns or set()

    async def check(self, ctx: Any) -> PermissionDecision:
        """Check whether a tool call is permitted.

        Args:
            ctx: ToolExecutionContext with tool_name, arguments.

        Returns:
            PermissionDecision with the verdict.
        """
        tool_name = ctx.tool_name

        # 1. Read-only tools: always allow
        if tool_name in self.READ_ONLY_TOOLS:
            return PermissionDecision(verdict=PermissionVerdict.ALLOW)

        # 2. Deny list check (patterns match tool_name or arguments)
        for pattern in self.deny_patterns:
            if pattern in tool_name or pattern in str(ctx.arguments):
                return PermissionDecision(
                    verdict=PermissionVerdict.DENY,
                    reason=f"Matches deny pattern: {pattern}",
                )

        # 3. Permanent allowlist (keyed by tool + arguments)
        cmd_key = self._make_key(ctx)
        if cmd_key in self.permanent_allowlist:
            return PermissionDecision(verdict=PermissionVerdict.ALLOW)

        # 4. Shell commands: check safety
        if tool_name == "exec":
            cmd = ctx.arguments.get("command", "")
            if self._is_safe_command(cmd):
                return PermissionDecision(verdict=PermissionVerdict.ALLOW)
            return PermissionDecision(
                verdict=PermissionVerdict.APPROVAL_REQUIRED,
                category="exec",
                description=f"Run: {cmd[:100]}",
                details={"command": cmd},
                allow_permanent=True,
            )

        # 5. File writes: require approval unless whitelisted
        if tool_name in frozenset({"write_file", "edit_file", "delete_file"}):
            path = ctx.arguments.get("path", "") or ctx.arguments.get("file_path", "")
            return PermissionDecision(
                verdict=PermissionVerdict.APPROVAL_REQUIRED,
                category="file_write",
                description=f"{tool_name}: {path}",
                details={"path": path, "operation": tool_name},
                allow_permanent=True,
            )

        # 6. Default: allow unknown/safe tools
        return PermissionDecision(verdict=PermissionVerdict.ALLOW)

    def _is_safe_command(self, cmd: str) -> bool:
        """Check if a shell command is safe to auto-approve."""
        cmd_lower = cmd.strip().lower()
        return any(cmd_lower.startswith(p) for p in self.SAFE_COMMAND_PREFIXES)

    @staticmethod
    def _make_key(ctx: Any) -> str:
        """Create a stable key for permanent allowlisting."""
        tool = ctx.tool_name
        if tool == "exec":
            return f"exec:{ctx.arguments.get('command', '')}"
        if tool in ("write_file", "edit_file", "delete_file"):
            return f"{tool}:{ctx.arguments.get('path', '') or ctx.arguments.get('file_path', '')}"
        return f"{tool}:{hash(str(ctx.arguments))}"
