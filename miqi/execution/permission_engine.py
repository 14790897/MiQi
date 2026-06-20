"""Permission policy decision engine.

Consults (in order):
1. Config-based deny rules (checked first — explicit blocks always win)
2. Read-only tools → auto-allow (unless blocked by deny pattern)
3. Permanent whitelist
4. Shell safety check (metacharacter-aware)
5. File write approval
6. Default: deny-by-default (APPROVAL_REQUIRED)
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from miqi.execution.approval_policy import ApprovalPolicy
from miqi.execution.exec_policy import PolicyVerdict


# Shell metacharacters that indicate command chaining or injection
_SHELL_METACHAR_PATTERN = re.compile(r"[;&|`$(){}\[\]<>!\n\r]")


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
    """Central permission decision engine.

    Deny-by-default architecture: unknown tools require approval.
    Explicit deny patterns take precedence over everything else.
    """

    # Read-only tools: auto-allow (but deny patterns still checked first)
    READ_ONLY_TOOLS: frozenset[str] = frozenset({
        "read_file", "list_dir", "web_search", "web_fetch",
        "session_search", "trace_search", "paper_search", "paper_get",
        "docx_read", "pptx_read", "xlsx_read", "memory",
    })

    # Safe shell commands: auto-allow (metacharacter-free commands only)
    SAFE_COMMAND_PREFIXES: tuple[str, ...] = (
        "ls ", "cat ", "head ", "tail ", "wc ", "grep ",
        "find ", "which ", "pwd", "echo ", "date", "whoami",
        "git status", "git log", "git diff", "git branch",
        "python --version", "node --version",
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
        profile = getattr(ctx, "permission_profile", None)

        # 1. Deny list check FIRST — explicit blocks always win
        for pattern in self.deny_patterns:
            if pattern in tool_name or pattern in str(ctx.arguments):
                return PermissionDecision(
                    verdict=PermissionVerdict.DENY,
                    reason=f"Matches deny pattern: {pattern}",
                )

        # 2. Read-only tools: auto-allow (unless blocked above)
        if tool_name in self.READ_ONLY_TOOLS:
            return PermissionDecision(verdict=PermissionVerdict.ALLOW)

        # 3. Permanent allowlist (keyed by tool + arguments)
        cmd_key = self._make_key(ctx)
        if cmd_key in self.permanent_allowlist:
            return PermissionDecision(verdict=PermissionVerdict.ALLOW)

        # 4. Exec tool branch
        if tool_name == "exec":
            cmd = str(ctx.arguments.get("command", ""))

            # Declarative ExecPolicy takes precedence when present
            if profile is not None and getattr(profile, "exec_policy", None) is not None:
                policy_decision = profile.exec_policy.evaluate_command(cmd)
                if policy_decision.verdict == PolicyVerdict.DENY:
                    return PermissionDecision(
                        verdict=PermissionVerdict.DENY,
                        reason=f"Denied by exec policy: {policy_decision.source}",
                    )
                if policy_decision.verdict == PolicyVerdict.ALLOW:
                    # Policy allows override the legacy safe-prefix whitelist, but
                    # shell metacharacters still force approval to prevent injection.
                    if _SHELL_METACHAR_PATTERN.search(cmd.strip()):
                        return self._apply_approval_policy(
                            PermissionDecision(
                                verdict=PermissionVerdict.APPROVAL_REQUIRED,
                                category="exec",
                                description=f"Policy allowed but command contains shell metacharacters: {cmd[:100]}",
                                details={"command": cmd},
                                allow_permanent=True,
                            ),
                            profile,
                        )
                    return PermissionDecision(
                        verdict=PermissionVerdict.ALLOW,
                        reason=f"Allowed by exec policy: {policy_decision.source}",
                    )
                # PROMPT → require approval
                return self._apply_approval_policy(
                    PermissionDecision(
                        verdict=PermissionVerdict.APPROVAL_REQUIRED,
                        category="exec",
                        description=f"Run: {cmd[:100]}",
                        details={"command": cmd},
                        allow_permanent=True,
                    ),
                    profile,
                )

            # Fall-through: legacy profile prefix rules + safe command checks
            if profile is not None:
                parts = cmd.split()
                # Deny rules checked first — explicit blocks always win
                for prefix in getattr(profile, "exec_deny_prefixes", []):
                    if parts[:len(prefix)] == prefix:
                        return PermissionDecision(
                            verdict=PermissionVerdict.DENY,
                            reason=f"Denied by permission profile prefix: {' '.join(prefix)}",
                        )
                # Allow rules — still require metacharacter safety
                for prefix in getattr(profile, "exec_allow_prefixes", []):
                    if parts[:len(prefix)] == prefix:
                        if not self._is_safe_command(cmd):
                            return self._apply_approval_policy(
                                PermissionDecision(
                                    verdict=PermissionVerdict.APPROVAL_REQUIRED,
                                    category="exec",
                                    description=f"Allowed prefix but command contains shell metacharacters: {cmd[:100]}",
                                    details={"command": cmd},
                                ),
                                profile,
                            )
                        return PermissionDecision(
                            verdict=PermissionVerdict.ALLOW,
                            reason=f"Allowed by permission profile prefix: {' '.join(prefix)}",
                        )

            # 5. Shell commands: metacharacter-aware safety check
            if self._is_safe_command(cmd):
                return PermissionDecision(verdict=PermissionVerdict.ALLOW)
            return self._apply_approval_policy(
                PermissionDecision(
                    verdict=PermissionVerdict.APPROVAL_REQUIRED,
                    category="exec",
                    description=f"Run: {cmd[:100]}",
                    details={"command": cmd},
                    allow_permanent=True,
                ),
                profile,
            )

        # 6. File writes: require approval unless whitelisted.
        # Phase 31.7: includes office document write tools so they are
        # explicitly categorized (not falling through to "unknown_tool")
        # and support permanent allowlisting.
        _FILE_WRITE_TOOLS = frozenset({
            "write_file", "edit_file", "delete_file",
            "docx_write", "pptx_write", "xlsx_write",
        })
        if tool_name in _FILE_WRITE_TOOLS:
            path = ctx.arguments.get("path", "") or ctx.arguments.get("file_path", "")
            return self._apply_approval_policy(
                PermissionDecision(
                    verdict=PermissionVerdict.APPROVAL_REQUIRED,
                    category="file_write",
                    description=f"{tool_name}: {path}",
                    details={"path": path, "operation": tool_name},
                    allow_permanent=True,
                ),
                profile,
            )

        # 7. Default: deny-by-default — unknown tools require approval
        return self._apply_approval_policy(
            PermissionDecision(
                verdict=PermissionVerdict.APPROVAL_REQUIRED,
                category="unknown_tool",
                description=f"Unknown tool: {tool_name}",
                details={"tool_name": tool_name},
            ),
            profile,
        )

    def _is_safe_command(self, cmd: str) -> bool:
        """Check if a shell command is safe to auto-approve.

        Rejects any command containing shell metacharacters
        (;, &, |, `, $, etc.) even if the prefix matches.
        """
        cmd_stripped = cmd.strip()
        if _SHELL_METACHAR_PATTERN.search(cmd_stripped):
            return False
        cmd_lower = cmd_stripped.lower()
        return any(cmd_lower.startswith(p) for p in self.SAFE_COMMAND_PREFIXES)

    def _apply_approval_policy(
        self,
        decision: PermissionDecision,
        profile: Any | None,
        *,
        failed: bool = False,
    ) -> PermissionDecision:
        """Potentially auto-approve a decision based on the active policy."""
        if decision.verdict != PermissionVerdict.APPROVAL_REQUIRED:
            return decision
        policy = getattr(profile, "approval_policy", None)
        if policy is None:
            return decision
        if not policy.requires_prompt(category=decision.category, failed=failed):
            return PermissionDecision(
                verdict=PermissionVerdict.ALLOW,
                category=decision.category,
                reason=f"Auto-approved by policy ({policy.mode.value})",
                description=decision.description,
                details=decision.details,
                allow_permanent=decision.allow_permanent,
            )
        return decision

    @staticmethod
    def _make_key(ctx: Any) -> str:
        """Create a stable key for permanent allowlisting."""
        tool = ctx.tool_name
        if tool == "exec":
            return f"exec:{ctx.arguments.get('command', '')}"
        if tool in ("write_file", "edit_file", "delete_file",
                      "docx_write", "pptx_write", "xlsx_write"):
            return f"{tool}:{ctx.arguments.get('path', '') or ctx.arguments.get('file_path', '')}"
        return f"{tool}:{hash(str(ctx.arguments))}"
