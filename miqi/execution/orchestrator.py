"""Unified tool execution orchestrator.

Implements the approval→sandbox→execute→retry pipeline for all tool calls.

Lifecycle:
  1. Pre-tool-use hooks run
  2. Permission policy engine checks the request
  3. If denied by policy → return error (no approval needed)
  4. If requires approval → emit ApprovalRequested, wait for response
  5. Sandbox policy engine selects sandbox type + permissions
  6. Tool executes inside the selected sandbox
  7. On sandbox denial → retry with escalated sandbox (weaker isolation)
  8. Post-tool-use hooks run
  9. Tool output is formatted and returned
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from loguru import logger

from miqi.execution.sandbox_policy import (
    SandboxPolicyEngine,
    SandboxSelection,
    SandboxType,
    SandboxDeniedError,
)
from miqi.execution.permission_engine import (
    PermissionEngine,
    PermissionDecision,
    PermissionVerdict,
)
from miqi.execution.hook_runtime import HookRuntime, HookPoint
from miqi.protocol.events import (
    ApprovalRequestedEvent,
)


class OrchestrationResult(str, Enum):
    SUCCESS = "success"
    DENIED_BY_POLICY = "denied_by_policy"
    DENIED_BY_USER = "denied_by_user"
    SANDBOX_FAILED = "sandbox_failed"
    TOOL_ERROR = "tool_error"
    TIMEOUT = "timeout"
    CANCELLED = "cancelled"


@dataclass
class ToolExecutionContext:
    """Context passed through the orchestration pipeline."""
    tool_name: str
    tool_call_id: str
    arguments: dict[str, Any]
    turn_id: str
    thread_id: str
    agent_type: str
    # Phase 13: per-turn permission profile (set by TurnRunner/AgentControl)
    permission_profile: Any | None = None
    # Phase 21: cancellation event for long-running tool calls
    cancel_event: Any | None = None
    # Filled by orchestrator
    permission_decision: PermissionDecision | None = None
    sandbox_selection: SandboxSelection | None = None
    result: str | None = None
    duration_ms: int = 0
    retry_count: int = 0


class ToolOrchestrator:
    """Orchestrates the full tool execution lifecycle."""

    MAX_RETRIES = 2

    def __init__(
        self,
        permission_engine: PermissionEngine,
        sandbox_engine: SandboxPolicyEngine,
        hook_runtime: HookRuntime,
        tool_registry: Any,  # ToolRegistry
        event_emitter: Any,  # EventEmitter
        approval_timeout_ms: int = 60_000,
    ):
        self.permissions = permission_engine
        self.sandbox = sandbox_engine
        self.hooks = hook_runtime
        self.tools = tool_registry
        self.events = event_emitter
        self.approval_timeout_ms = approval_timeout_ms
        # In-flight approval futures: approval_id → Future[PermissionDecision]
        self._pending_approvals: dict[str, asyncio.Future] = {}
        # Approval metadata for listing: approval_id → metadata dict
        self._approval_meta: dict[str, dict[str, Any]] = {}

    async def execute(self, ctx: ToolExecutionContext) -> ToolExecutionContext:
        """Execute a tool call through the full orchestration pipeline."""
        start = time.monotonic()

        try:
            # 1. Pre-tool-use hooks
            await self.hooks.run(HookPoint.PRE_TOOL_USE, ctx)

            # Phase 13: apply per-turn permission profile overrides
            permission_profile = getattr(ctx, "permission_profile", None)
            if permission_profile is not None:
                if hasattr(permission_profile, "permanent_allowlist"):
                    self.permissions.permanent_allowlist.update(
                        permission_profile.permanent_allowlist
                    )

            # 2. Permission check
            decision = await self.permissions.check(ctx)
            ctx.permission_decision = decision

            if decision.verdict == PermissionVerdict.DENY:
                ctx.result = f"Permission denied: {decision.reason}"
                return ctx

            if decision.verdict == PermissionVerdict.APPROVAL_REQUIRED:
                decision = await self._request_approval(ctx, decision)
                if decision.verdict != PermissionVerdict.ALLOW:
                    ctx.result = f"User denied: {decision.reason or 'no reason given'}"
                    return ctx

            # 3. Try execution with retry-escalation
            while ctx.retry_count <= self.MAX_RETRIES:
                try:
                    # 3a. Select sandbox
                    sandbox_sel = await self.sandbox.select(
                        ctx, attempt=ctx.retry_count
                    )
                    ctx.sandbox_selection = sandbox_sel

                    # 3b. Execute inside sandbox
                    ctx.result = await self._execute_in_sandbox(ctx, sandbox_sel)
                    break  # success

                except SandboxDeniedError:
                    # Escalate: weaker isolation on retry
                    ctx.retry_count += 1
                    logger.warning(
                        "Sandbox denied for {} (attempt {}); escalating",
                        ctx.tool_name, ctx.retry_count,
                    )
                    if ctx.retry_count > self.MAX_RETRIES:
                        ctx.result = "Error: sandbox denied after max retries"
                        return ctx

                except asyncio.TimeoutError:
                    ctx.result = f"Error: tool '{ctx.tool_name}' timed out"
                    return ctx

            # 4. Post-tool-use hooks
            await self.hooks.run(HookPoint.POST_TOOL_USE, ctx)

        except asyncio.CancelledError:
            ctx.result = "Tool execution cancelled"
        except Exception as e:
            logger.exception("Tool orchestrator error for {}", ctx.tool_name)
            ctx.result = f"Error executing {ctx.tool_name}: {e}"

        finally:
            ctx.duration_ms = int((time.monotonic() - start) * 1000)

        return ctx

    async def _request_approval(
        self,
        ctx: ToolExecutionContext,
        decision: PermissionDecision,
    ) -> PermissionDecision:
        """Emit approval request and wait for user response."""
        approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
        await self.events.emit(ApprovalRequestedEvent(
            approval_id=approval_id,
            turn_id=ctx.turn_id,
            category=decision.category,
            description=decision.description,
            details=decision.details,
            allow_permanent=decision.allow_permanent,
        ))

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_approvals[approval_id] = future
        # Store metadata for listing (Phase 28.2)
        self._approval_meta[approval_id] = {
            "approval_id": approval_id,
            "turn_id": ctx.turn_id,
            "command": decision.description or "",
            "description": decision.description or "",
            "details": decision.details or "",
            "allow_permanent": decision.allow_permanent,
            "created_at": time.time(),
        }

        try:
            response = await asyncio.wait_for(
                future, self.approval_timeout_ms / 1000
            )
            return response
        except asyncio.TimeoutError:
            return PermissionDecision(
                verdict=PermissionVerdict.DENY,
                reason="Approval timeout",
            )
        finally:
            self._pending_approvals.pop(approval_id, None)
            self._approval_meta.pop(approval_id, None)

    def resolve_approval(self, approval_id: str, decision: str) -> None:
        """Called by bridge when user responds to approval request."""
        future = self._pending_approvals.get(approval_id)
        if future and not future.done():
            future.set_result(PermissionDecision(
                verdict=PermissionVerdict.ALLOW if decision.startswith("allow")
                else PermissionVerdict.DENY,
                reason=f"User chose: {decision}",
            ))

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        """Return metadata for all pending approvals.

        Phase 28.2: Exposes approval metadata for session-scoped listing.
        Each entry includes approval_id, command, description, details,
        allow_permanent, created_at, and age_seconds.
        """
        now = time.time()
        result: list[dict[str, Any]] = []
        for approval_id in self._pending_approvals:
            meta = self._approval_meta.get(approval_id, {})
            if meta:
                result.append({
                    "approval_id": approval_id,
                    "command": meta.get("command", ""),
                    "description": meta.get("description", ""),
                    "details": meta.get("details", ""),
                    "allow_permanent": meta.get("allow_permanent", True),
                    "created_at": meta.get("created_at", now),
                    "age_seconds": now - meta.get("created_at", now),
                })
        return result

    def has_approval(self, approval_id: str) -> bool:
        """Check if this orchestrator owns the given approval."""
        return approval_id in self._pending_approvals

    async def _execute_in_sandbox(
        self,
        ctx: ToolExecutionContext,
        sandbox: SandboxSelection,
    ) -> str:
        """Execute the tool inside the selected sandbox."""
        tool = self.tools.get(ctx.tool_name)
        if tool is None:
            return f"Error: Unknown tool '{ctx.tool_name}'"

        # Inject sandbox context into tool
        kwargs = {**ctx.arguments}
        if sandbox.sandbox_type != SandboxType.NONE:
            kwargs["_sandbox"] = sandbox

        # Phase 21: pass runtime event emitter and cancellation to exec tool
        if ctx.tool_name == "exec":
            kwargs["_event_emitter"] = self.events
            kwargs["_turn_id"] = ctx.turn_id
            kwargs["_tool_call_id"] = ctx.tool_call_id
            if ctx.cancel_event is not None:
                kwargs["_cancel_event"] = ctx.cancel_event

        return await tool.execute(**kwargs)
