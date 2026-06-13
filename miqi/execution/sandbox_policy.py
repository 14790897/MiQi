"""Sandbox policy resolution engine.

Determines which sandbox type and permissions to use for a tool execution.
Supports escalating from strict to weaker isolation on denial.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from miqi.protocol.permissions import (
    FileSystemAccessMode,
    FileSystemPathRule,
    FileSystemSandboxPolicy,
    NetworkSandboxPolicy,
)


class SandboxType(str, Enum):
    """Available sandbox isolation levels."""
    NONE = "none"          # No sandbox — direct execution
    BWRAP = "bwrap"        # Linux bubblewrap (strongest isolation)
    LANDLOCK = "landlock"  # Linux Landlock LSM (lighter than bwrap)
    RESTRICTED = "restricted"  # Process-level restrictions only


class SandboxDeniedError(Exception):
    """Raised when the selected sandbox denies the execution."""
    pass


@dataclass
class SandboxSelection:
    """Resolved sandbox configuration for a tool execution."""
    sandbox_type: SandboxType
    filesystem_policy: FileSystemSandboxPolicy
    network_policy: NetworkSandboxPolicy
    env_passthrough: list[str] = field(default_factory=list)
    timeout_ms: int = 30_000
    reason: str = ""


class SandboxPolicyEngine:
    """Resolves sandbox policy for tool executions.

    Escalation strategy (on denial):
      Attempt 0 → bwrap (strongest)
      Attempt 1 → landlock (medium)
      Attempt 2 → restricted (weakest)
      Attempt 3 → none (fallback, if allowed by policy)
    """

    # Tools that never need sandboxing (pure read operations)
    NO_SANDBOX_TOOLS: frozenset[str] = frozenset({
        "read_file", "list_dir", "web_search", "web_fetch",
        "paper_search", "paper_get", "session_search",
        "trace_search", "memory", "plan_create", "plan_update",
        "docx_read", "pptx_read", "xlsx_read",
    })

    # Tools that always benefit from strongest sandbox
    STRONG_SANDBOX_TOOLS: frozenset[str] = frozenset({
        "exec",
    })

    def __init__(
        self,
        bwrap_available: bool = False,
        landlock_available: bool = False,
        default_timeout_ms: int = 30_000,
        allow_fallback_to_none: bool = True,
    ):
        self.bwrap_available = bwrap_available
        self.landlock_available = landlock_available
        self.default_timeout_ms = default_timeout_ms
        self.allow_fallback_to_none = allow_fallback_to_none

    async def select(
        self,
        ctx: Any,
        attempt: int = 0,
    ) -> SandboxSelection:
        """Select the appropriate sandbox for a tool execution."""
        tool_name = ctx.tool_name

        # 1. Read-only tools: no sandbox needed
        if tool_name in self.NO_SANDBOX_TOOLS:
            return SandboxSelection(
                sandbox_type=SandboxType.NONE,
                filesystem_policy=FileSystemSandboxPolicy(
                    default_mode=FileSystemAccessMode.READ,
                ),
                network_policy=NetworkSandboxPolicy.ALLOW_ALL,
                reason="Read-only tool, sandbox not required",
            )

        # 2. Determine base sandbox type
        base_type = self._base_sandbox_type(tool_name)

        # 3. Escalate on retry
        escalation = self._escalation_chain(base_type)
        if attempt >= len(escalation):
            if self.allow_fallback_to_none:
                selected = SandboxType.NONE
            else:
                raise SandboxDeniedError(
                    f"No sandbox available after {attempt} attempts for {tool_name}"
                )
        else:
            selected = escalation[attempt]

        # 4. Build permissions
        fs_policy = self._filesystem_policy_for_tool(tool_name, ctx)
        net_policy = self._network_policy_for_tool(tool_name, ctx)

        # Phase 33.3: RESTRICTED cannot enforce network isolation via
        # direct host execution.  Default to BLOCK_ALL so
        # _execute_restricted() fails closed — unless the permission
        # profile explicitly sets network_allowed=True.
        if selected == SandboxType.RESTRICTED and tool_name == "exec":
            profile = getattr(ctx, "permission_profile", None)
            network_allowed = (
                getattr(profile, "network_allowed", False)
                if profile is not None
                else False
            )
            if not network_allowed:
                net_policy = NetworkSandboxPolicy.BLOCK_ALL

        return SandboxSelection(
            sandbox_type=selected,
            filesystem_policy=fs_policy,
            network_policy=net_policy,
            env_passthrough=ctx.arguments.get("env_passthrough", []),
            timeout_ms=self.default_timeout_ms,
            reason=f"Selected {selected.value} (attempt {attempt}) for {tool_name}",
        )

    def _base_sandbox_type(self, tool_name: str) -> SandboxType:
        """Determine the preferred sandbox type for a tool."""
        if tool_name in self.STRONG_SANDBOX_TOOLS:
            if self.bwrap_available:
                return SandboxType.BWRAP
            if self.landlock_available:
                return SandboxType.LANDLOCK
            return SandboxType.RESTRICTED

        # File write tools: moderate isolation
        if tool_name in frozenset({"write_file", "edit_file", "delete_file"}):
            return SandboxType.RESTRICTED

        return SandboxType.NONE

    @staticmethod
    def _escalation_chain(base: SandboxType) -> list[SandboxType]:
        """Build the escalation chain from base type downward."""
        chain: list[SandboxType] = [base]
        all_types = [SandboxType.BWRAP, SandboxType.LANDLOCK, SandboxType.RESTRICTED, SandboxType.NONE]
        try:
            start_idx = all_types.index(base)
            for t in all_types[start_idx + 1:]:
                chain.append(t)
        except ValueError:
            pass
        return chain

    @staticmethod
    def _filesystem_policy_for_tool(
        tool_name: str,
        ctx: Any,
    ) -> FileSystemSandboxPolicy:
        """Build filesystem policy for a tool execution."""
        if tool_name == "exec":
            return FileSystemSandboxPolicy(
                rules=[],
                default_mode=FileSystemAccessMode.READ,
                deny_hidden=False,
            )

        if tool_name in frozenset({"write_file", "edit_file", "delete_file"}):
            path = ctx.arguments.get("path") or ctx.arguments.get("file_path", "")
            rules = []
            if path:
                rules.append(FileSystemPathRule(
                    path=path,
                    mode=FileSystemAccessMode.WRITE,
                ))
            return FileSystemSandboxPolicy(
                rules=rules,
                default_mode=FileSystemAccessMode.READ,
            )

        return FileSystemSandboxPolicy(
            default_mode=FileSystemAccessMode.READ,
        )

    @staticmethod
    def _network_policy_for_tool(
        tool_name: str,
        ctx: Any,
    ) -> NetworkSandboxPolicy:
        """Build network policy for a tool execution."""
        if tool_name in frozenset({"web_search", "web_fetch"}):
            return NetworkSandboxPolicy.ALLOW_ALL
        if tool_name == "exec":
            return NetworkSandboxPolicy.ALLOW_ALL
        return NetworkSandboxPolicy.ALLOW_ALL
