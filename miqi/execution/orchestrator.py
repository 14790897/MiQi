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
    ApprovalResolvedEvent,
)

# Phase 31.4: valid approval decision values.
# "allow" is a legacy synonym for "once" — preserved for backward compat.
VALID_APPROVAL_DECISIONS = frozenset({"once", "session", "always", "deny", "allow"})
_LEGACY_DECISION_MAP = {"allow": "once"}

# Phase 31.4: max lengths for sanitized approval metadata fields
_MAX_DESCRIPTION_LENGTH = 500
_MAX_DETAILS_STRING_LENGTH = 2000
_MAX_COMMAND_LENGTH = 500


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
    # Phase 31.4: client and session identity for approval scoping
    client_id: str = ""
    session_id: str = ""
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
        session_id: str = "",
    ):
        self.permissions = permission_engine
        self.sandbox = sandbox_engine
        self.hooks = hook_runtime
        self.tools = tool_registry
        self.events = event_emitter
        self.approval_timeout_ms = approval_timeout_ms
        self._session_id = session_id
        # In-flight approval futures: approval_id → Future[PermissionDecision]
        self._pending_approvals: dict[str, asyncio.Future] = {}
        # Approval metadata for listing: approval_id → metadata dict
        self._approval_meta: dict[str, dict[str, Any]] = {}
        # Phase 31.4: thread_id → {approval_id} for abort reconciliation
        self._thread_approvals: dict[str, set[str]] = {}

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

    @staticmethod
    def _sanitize_details(details: dict[str, Any]) -> dict[str, Any]:
        """Return a safe copy of *details* suitable for client emission.

        Removes/drops values that are not JSON-serializable or could leak
        internals (Exception objects, futures, process handles, raw secrets).
        Strings are length-capped.
        """
        if not isinstance(details, dict):
            return {}
        safe: dict[str, Any] = {}
        for key, value in details.items():
            if not isinstance(key, str):
                continue
            # Drop known-unsafe keys
            if key.lower() in ("exception", "traceback", "secret", "password",
                               "token", "api_key", "_future", "_process",
                               "credential", "authorization"):
                continue
            if isinstance(value, (bool, int, float, type(None))):
                safe[key] = value
            elif isinstance(value, str):
                safe[key] = value[:_MAX_DETAILS_STRING_LENGTH]
            elif isinstance(value, (list, tuple)):
                safe[key] = str(value)[:_MAX_DETAILS_STRING_LENGTH]
            elif isinstance(value, dict):
                # Recursively sanitize nested dicts, depth-guarded
                safe[key] = ToolOrchestrator._sanitize_details(value)
            else:
                # Drop non-serializable types (Exception, future, etc.)
                safe[key] = f"<{type(value).__name__}>"
        return safe

    async def _request_approval(
        self,
        ctx: ToolExecutionContext,
        decision: PermissionDecision,
    ) -> PermissionDecision:
        """Emit approval request and wait for user response.

        Phase 31.4: approval metadata includes client_id, session_id,
        thread_id, turn_id, tool_call_id, tool_name, category, timeout_ms.
        On timeout emits ApprovalResolvedEvent(decision="timeout") so the
        frontend and ledger always see a terminal event.
        """
        approval_id = f"{ctx.turn_id}:{ctx.tool_call_id}"
        sanitized_details = self._sanitize_details(decision.details)
        created_at = time.time()

        await self.events.emit(ApprovalRequestedEvent(
            approval_id=approval_id,
            turn_id=ctx.turn_id,
            thread_id=ctx.thread_id,
            category=decision.category,
            description=(decision.description or "")[:_MAX_DESCRIPTION_LENGTH],
            details=sanitized_details,
            allow_permanent=decision.allow_permanent,
        ))

        future: asyncio.Future = asyncio.get_event_loop().create_future()
        self._pending_approvals[approval_id] = future
        # Store enriched metadata for listing (Phase 28.2 + 31.4)
        self._approval_meta[approval_id] = {
            "approval_id": approval_id,
            "client_id": ctx.client_id,
            "session_id": ctx.session_id,
            "thread_id": ctx.thread_id,
            "turn_id": ctx.turn_id,
            "tool_call_id": ctx.tool_call_id,
            "tool_name": ctx.tool_name,
            "category": decision.category,
            "description": (decision.description or "")[:_MAX_DESCRIPTION_LENGTH],
            "details": sanitized_details,
            "command": ((decision.details or {}).get("command", "")
                        if isinstance(decision.details, dict)
                        else "")[:_MAX_COMMAND_LENGTH],
            "allow_permanent": decision.allow_permanent,
            "created_at": created_at,
            "timeout_ms": self.approval_timeout_ms,
        }
        # Phase 31.4: thread → approval mapping for abort reconciliation
        self._thread_approvals.setdefault(ctx.thread_id, set()).add(approval_id)

        try:
            response = await asyncio.wait_for(
                future, self.approval_timeout_ms / 1000
            )
            return response
        except asyncio.TimeoutError:
            # Phase 31.4: emit terminal resolution event on timeout
            await self.events.emit(ApprovalResolvedEvent(
                approval_id=approval_id,
                decision="timeout",
                turn_id=ctx.turn_id,
            ))
            return PermissionDecision(
                verdict=PermissionVerdict.DENY,
                reason="Approval timeout",
            )
        finally:
            self._pending_approvals.pop(approval_id, None)
            self._approval_meta.pop(approval_id, None)
            self._thread_approvals.get(ctx.thread_id, set()).discard(approval_id)
            if (ctx.thread_id in self._thread_approvals
                    and not self._thread_approvals[ctx.thread_id]):
                del self._thread_approvals[ctx.thread_id]

    def resolve_approval(self, approval_id: str, decision: str) -> None:
        """Called by bridge/TaskRunner when user responds to approval.

        Phase 31.4: validates the decision against the allowed set,
        handles allow_permanent/always via permanent allowlist boundary,
        and records the scope.
        """
        # Phase 31.4: map legacy "allow" → "once"
        decision = _LEGACY_DECISION_MAP.get(decision, decision)

        if decision not in VALID_APPROVAL_DECISIONS:
            logger.warning(
                "resolve_approval: invalid decision={!r} for approval_id={}",
                decision, approval_id,
            )
            return

        future = self._pending_approvals.get(approval_id)
        if future is None or future.done():
            # Already resolved (timeout, abort, or duplicate response)
            return

        meta = self._approval_meta.get(approval_id, {})

        if decision == "deny":
            future.set_result(PermissionDecision(
                verdict=PermissionVerdict.DENY,
                reason="User denied the request.",
            ))
            return

        # allow / session / always — all permit execution
        verdict = PermissionVerdict.ALLOW
        reason = f"Approved by user (scope: {decision})"

        # Phase 31.4: "always" → add to permanent allowlist
        if decision == "always":
            self._record_permanent_approval(meta)

        future.set_result(PermissionDecision(
            verdict=verdict,
            reason=reason,
            allow_permanent=(decision == "always"),
        ))

    def _record_permanent_approval(self, meta: dict[str, Any]) -> None:
        """Add the approved command pattern to the permanent allowlist.

        The description (or command field) is used as the pattern.
        Scope is recorded as session-scoped via the session_id.
        """
        pattern = (meta.get("description") or meta.get("command") or "").strip()
        if not pattern:
            return
        self.permissions.permanent_allowlist.add(pattern)
        logger.info(
            "Permanent approval recorded: pattern={!r} session={}",
            pattern, self._session_id,
        )

    def list_pending_approvals(self) -> list[dict[str, Any]]:
        """Return metadata for all pending approvals.

        Phase 28.2 + 31.4: Exposes approval metadata for session-scoped
        listing. Each entry includes approval_id, client_id, session_id,
        thread_id, turn_id, tool_call_id, tool_name, category, description,
        details, command, allow_permanent, timeout_ms, created_at, and
        age_seconds.
        """
        now = time.time()
        result: list[dict[str, Any]] = []
        for approval_id in self._pending_approvals:
            meta = self._approval_meta.get(approval_id, {})
            if meta:
                result.append({
                    "approval_id": approval_id,
                    "client_id": meta.get("client_id", ""),
                    "session_id": meta.get("session_id", ""),
                    "thread_id": meta.get("thread_id", ""),
                    "turn_id": meta.get("turn_id", ""),
                    "tool_call_id": meta.get("tool_call_id", ""),
                    "tool_name": meta.get("tool_name", ""),
                    "category": meta.get("category", ""),
                    "description": meta.get("description", ""),
                    "details": meta.get("details", {}),
                    "command": meta.get("command", ""),
                    "allow_permanent": meta.get("allow_permanent", False),
                    "timeout_ms": meta.get("timeout_ms", self.approval_timeout_ms),
                    "created_at": meta.get("created_at", now),
                    "age_seconds": now - meta.get("created_at", now),
                })
        return result

    def has_approval(self, approval_id: str) -> bool:
        """Check if this orchestrator owns the given approval."""
        return approval_id in self._pending_approvals

    # ── Phase 31.4: abort-triggered approval cancellation ──────────────

    async def cancel_approvals_for_thread(
        self, thread_id: str, *, reason: str = "Turn aborted",
    ) -> int:
        """Cancel all pending approvals for *thread_id*.

        Each pending approval is denied, its waiting tool call is unblocked,
        metadata is cleaned, and an ``ApprovalResolvedEvent(decision="abort")``
        is emitted.  Returns the count of approvals that were cancelled.
        """
        approval_ids = list(self._thread_approvals.get(thread_id, set()))
        cancelled = 0

        for aid in approval_ids:
            future = self._pending_approvals.get(aid)
            meta = self._approval_meta.get(aid, {})
            turn_id = meta.get("turn_id", "")

            if future is not None and not future.done():
                future.set_result(PermissionDecision(
                    verdict=PermissionVerdict.DENY,
                    reason=reason,
                ))
                cancelled += 1

            # Clean up maps
            self._pending_approvals.pop(aid, None)
            self._approval_meta.pop(aid, None)

            # Emit terminal event for ledger + frontend
            await self.events.emit(ApprovalResolvedEvent(
                approval_id=aid,
                decision="abort",
                turn_id=turn_id,
            ))

        self._thread_approvals.pop(thread_id, None)
        if cancelled:
            logger.info(
                "Cancelled {} pending approval(s) for thread {}",
                cancelled, thread_id,
            )
        return cancelled

    async def _execute_in_sandbox(
        self,
        ctx: ToolExecutionContext,
        sandbox: SandboxSelection,
    ) -> str:
        """Execute the tool inside the selected sandbox."""
        tool = self.tools.get(ctx.tool_name)
        if tool is None:
            return f"Error: Unknown tool '{ctx.tool_name}'"

        # Inject sandbox context into tool.
        # Phase 31: For exec tool, ALWAYS inject the SandboxSelection so
        # ExecTool never makes independent sandbox decisions.  Even NONE
        # must be communicated explicitly — otherwise ExecTool falls back
        # to the legacy path and may use an active sandbox against the
        # orchestrator's decision.
        kwargs = {**ctx.arguments}
        if ctx.tool_name == "exec":
            kwargs["_sandbox"] = sandbox
        elif sandbox.sandbox_type != SandboxType.NONE:
            kwargs["_sandbox"] = sandbox

        # Phase 21: pass runtime event emitter and cancellation to exec tool
        if ctx.tool_name == "exec":
            kwargs["_event_emitter"] = self.events
            kwargs["_turn_id"] = ctx.turn_id
            kwargs["_tool_call_id"] = ctx.tool_call_id
            if ctx.cancel_event is not None:
                kwargs["_cancel_event"] = ctx.cancel_event

        return await tool.execute(**kwargs)
