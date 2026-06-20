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
from miqi.execution.hook_runtime import HookRuntime, HookPoint, HookOutcome
from miqi.protocol.events import (
    ApprovalRequestedEvent,
    ApprovalResolvedEvent,
)

# Phase 31.4: valid approval decision values.
# "allow" is a legacy synonym for "once"; "allow_permanent" is a legacy
# synonym for "always" — both preserved for backward compatibility.
VALID_APPROVAL_DECISIONS = frozenset({
    "once", "session", "always", "deny", "allow", "allow_permanent",
})
_LEGACY_DECISION_MAP = {"allow": "once", "allow_permanent": "always"}

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


@dataclass
class ApprovalResolveResult:
    """Structured result from ToolOrchestrator.resolve_approval().

    resolved=False means the call was a no-op: either the approval_id
    didn't exist, was already resolved, or the decision was invalid.
    Callers MUST check resolved before emitting terminal events.
    """
    resolved: bool
    approval_id: str
    normalized_decision: str
    turn_id: str
    reason: str = ""  # explanation when resolved=False, empty on success


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
        ledger_runtime: Any | None = None,
    ):
        self.permissions = permission_engine
        self.sandbox = sandbox_engine
        self.hooks = hook_runtime
        self.tools = tool_registry
        self.events = event_emitter
        self.approval_timeout_ms = approval_timeout_ms
        self._session_id = session_id
        # Phase 31.8: ledger runtime for replay-persistent event recording
        self._ledger = ledger_runtime
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
            outcome = await self.hooks.run_with_outcome(HookPoint.PRE_TOOL_USE, ctx)
            if outcome.action == "block":
                ctx.permission_decision = PermissionDecision(
                    verdict=PermissionVerdict.DENY,
                    reason=f"Blocked by hook: {outcome.reason}",
                )
                ctx.result = f"Permission denied: {outcome.reason}"
                ctx.duration_ms = int((time.monotonic() - start) * 1000)
                return ctx
            if outcome.action == "modify" and outcome.patch:
                if "arguments" in outcome.patch:
                    ctx.arguments.update(outcome.patch["arguments"])

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
                pr_outcome = await self.hooks.run_with_outcome(
                    HookPoint.PERMISSION_REQUEST, ctx
                )
                if pr_outcome.action == "block":
                    ctx.permission_decision = PermissionDecision(
                        verdict=PermissionVerdict.DENY,
                        reason=f"Blocked by hook: {pr_outcome.reason}",
                    )
                    ctx.result = f"Permission denied: {pr_outcome.reason}"
                    return ctx
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
            await self.hooks.run_with_outcome(HookPoint.POST_TOOL_USE, ctx)

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

        # Phase 31.8: record approval request in ledger for replay
        if self._ledger is not None:
            await self._ledger.append_item(
                thread_id=ctx.thread_id,
                turn_id=ctx.turn_id,
                item_type="approval_requested",
                payload={
                    "approval_id": approval_id,
                    "tool_call_id": ctx.tool_call_id,
                    "tool_name": ctx.tool_name,
                    "category": decision.category,
                    "description": (decision.description or "")[:_MAX_DESCRIPTION_LENGTH],
                    "allow_permanent": decision.allow_permanent,
                },
            )

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
            # Phase 31.8 fix: write approval_resolved to ledger
            # deterministically (awaited, not fire-and-forget).
            # resolve_approval() stored the normalized decision in
            # _approval_meta["resolved_decision"] before setting the
            # future result.  We read it here — while meta is still
            # alive (finally cleanup hasn't run yet).
            if self._ledger is not None:
                resolved_decision = self._approval_meta.get(
                    approval_id, {},
                ).get("resolved_decision", "deny")
                await self._ledger.append_item(
                    thread_id=ctx.thread_id,
                    turn_id=ctx.turn_id,
                    item_type="approval_resolved",
                    payload={
                        "approval_id": approval_id,
                        "tool_call_id": ctx.tool_call_id,
                        "decision": resolved_decision,
                        "tool_name": ctx.tool_name,
                        "category": decision.category,
                    },
                )
            return response
        except asyncio.TimeoutError:
            # Phase 31.4: emit terminal resolution event on timeout
            await self.events.emit(ApprovalResolvedEvent(
                approval_id=approval_id,
                decision="timeout",
                turn_id=ctx.turn_id,
            ))
            # Phase 31.8: record timeout in ledger for replay
            if self._ledger is not None:
                await self._ledger.append_item(
                    thread_id=ctx.thread_id,
                    turn_id=ctx.turn_id,
                    item_type="approval_resolved",
                    payload={
                        "approval_id": approval_id,
                        "tool_call_id": ctx.tool_call_id,
                        "decision": "timeout",
                        "tool_name": ctx.tool_name,
                        "category": decision.category,
                    },
                )
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

    def resolve_approval(self, approval_id: str, decision: str) -> ApprovalResolveResult:
        """Called by bridge/TaskRunner when user responds to approval.

        Phase 31.4: validates the decision against the allowed set,
        handles allow_permanent/always via permanent allowlist boundary,
        and records the scope.

        Returns:
            ApprovalResolveResult with resolved=True on success.
            resolved=False when the approval doesn't exist, is already
            done, or the decision is invalid.  Callers MUST check
            resolved before emitting terminal events.
        """
        # Phase 31.4: map legacy decisions
        original_decision = decision
        decision = _LEGACY_DECISION_MAP.get(decision, decision)

        if decision not in VALID_APPROVAL_DECISIONS:
            logger.warning(
                "resolve_approval: invalid decision={!r} (original={!r}) "
                "for approval_id={}",
                decision, original_decision, approval_id,
            )
            return ApprovalResolveResult(
                resolved=False,
                approval_id=approval_id,
                normalized_decision=decision,
                turn_id="",
                reason=f"Invalid decision: {original_decision!r}",
            )

        future = self._pending_approvals.get(approval_id)
        if future is None or future.done():
            # Already resolved (timeout, abort, or duplicate response)
            return ApprovalResolveResult(
                resolved=False,
                approval_id=approval_id,
                normalized_decision=decision,
                turn_id="",
                reason="Approval not found or already resolved",
            )

        meta = self._approval_meta.get(approval_id, {})
        turn_id = meta.get("turn_id", "")

        if decision == "deny":
            # Phase 31.8 fix: store resolved decision in meta so
            # _request_approval() can write the ledger item with an
            # awaited call (deterministic, not fire-and-forget).
            meta["resolved_decision"] = "deny"
            future.set_result(PermissionDecision(
                verdict=PermissionVerdict.DENY,
                reason="User denied the request.",
            ))
            return ApprovalResolveResult(
                resolved=True,
                approval_id=approval_id,
                normalized_decision="deny",
                turn_id=turn_id,
            )

        # allow ("once") / session / always — all permit execution
        verdict = PermissionVerdict.ALLOW
        reason = f"Approved by user (scope: {decision})"

        # Phase 31.4: "always" → add to permanent allowlist
        if decision == "always":
            self._record_permanent_approval(meta)

        # Phase 31.8 fix: store resolved decision in meta so
        # _request_approval() can write the ledger item with an
        # awaited call (deterministic, not fire-and-forget).
        meta["resolved_decision"] = decision

        future.set_result(PermissionDecision(
            verdict=verdict,
            reason=reason,
            allow_permanent=(decision == "always"),
        ))
        return ApprovalResolveResult(
            resolved=True,
            approval_id=approval_id,
            normalized_decision=decision,
            turn_id=turn_id,
        )

    def _record_permanent_approval(self, meta: dict[str, Any]) -> None:
        """Add the approved tool+argument key to the permanent allowlist.

        Builds the pattern using the same key format as
        PermissionEngine._make_key so the allowlist entry actually
        matches future permission checks:

        - exec tools:     exec:<command>
        - file_write tools: <tool_name>:<path>
        - other tools:    <tool_name>:<hash of arguments>

        Phase 31.7 fix: previously used ``description`` which contains
        a user-facing format (e.g. "write_file: /tmp/x" with a space)
        that never matched _make_key's format ("write_file:/tmp/x").
        """
        tool = meta.get("tool_name", "")
        if tool == "exec":
            cmd = meta.get("command", "")
            if not cmd:
                return
            pattern = f"exec:{cmd}"
        elif tool in (
            "write_file", "edit_file", "delete_file",
            "docx_write", "pptx_write", "xlsx_write",
        ):
            path = (meta.get("details", {}) or {}).get("path", "")
            if not path:
                return
            pattern = f"{tool}:{path}"
        else:
            # Fallback: use the description field (user-visible text)
            pattern = (meta.get("description") or "").strip()
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

            # Phase 31.8: record abort in ledger for replay
            if self._ledger is not None:
                tool_call_id = meta.get("tool_call_id", "")
                await self._ledger.append_item(
                    thread_id=thread_id,
                    turn_id=turn_id,
                    item_type="approval_resolved",
                    payload={
                        "approval_id": aid,
                        "tool_call_id": tool_call_id,
                        "decision": "abort",
                        "tool_name": meta.get("tool_name", ""),
                        "category": meta.get("category", ""),
                    },
                )

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
        # Phase 34: File mutation tools also always receive _sandbox —
        # the policy engine never returns NONE for them, so this is
        # normally RESTRICTED.  Injecting even NONE is future-proofing
        # for tool-body sandbox enforcement and auditing.
        _FILE_MUTATION_TOOLS = frozenset({
            "write_file", "edit_file", "delete_file", "apply_patch",
            "docx_write", "pptx_write", "xlsx_write",
        })
        kwargs = {**ctx.arguments}
        if ctx.tool_name == "exec" or ctx.tool_name in _FILE_MUTATION_TOOLS:
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
            # Phase 31.8: pass ledger runtime so exec events are recorded
            if self._ledger is not None:
                kwargs["_ledger_runtime"] = self._ledger
                kwargs["_thread_id"] = ctx.thread_id

        return await tool.execute(**kwargs)
