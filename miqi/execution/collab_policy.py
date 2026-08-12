"""Collaboration policy — the confirm-card gate (issue #646, design v2).

Two AI reviews converged on: the model must never be the final decision
maker. The harness decides *when to ask*, the model decides *what to propose*.

This module is the Collaboration Policy layer:

    User Mode (Autonomy)
        ↓
    Policy Engine
        ├─ Safety Policy      → approval gate (allow/deny, bypassable)
        └─ Collaboration Policy → confirm card (this file, NOT bypassable)

Key design points (from the design-review doc in D:/Desktop/811):
- Risk-based autonomy: "automatic" is NOT "fully autonomous" — low-risk runs
  automatically, high-risk always confirms.
- Intent vs Safety: approval answers "may I?" (permission), the confirm card
  answers "is this the plan?" (decision). External transfers and payments
  ALWAYS confirm, regardless of approval bypass settings.
"""

from __future__ import annotations

from enum import Enum


class RiskLevel(str, Enum):
    """Risk classes for tool intents (9月演示 hard-coded table)."""

    READ = "read"              # search/read/analyze — always auto
    WRITE = "write"            # write file / edit — confirm in supervised
    EXEC = "exec"              # shell / command — confirm + safety approval
    EXTERNAL = "external"      # upload / outbound transfer — ALWAYS confirm
    PAYMENT = "payment"        # money — always confirm (future)


class AutonomyMode(str, Enum):
    """User-selected autonomy level (maps to the desktop mode picker)."""

    PLAN = "plan"              # 规划: analyse only, no execution
    MANUAL = "manual"          # 手动: every step confirmed
    SUPERVISED = "supervised"  # 允许编辑: writes auto, risky confirms (new)
    AUTONOMOUS = "autonomous"  # 自动: low-risk auto, high-risk confirms


class CollabVerdict(str, Enum):
    ALLOW = "allow"            # run without asking
    CONFIRM = "confirm"        # block and show confirm card
    DENY = "deny"              # blocked by policy (plan mode etc.)


# Tool-name → risk class. Single source of truth — keep in sync with
# runtime/tool_policy.py (safety side) and tool_registry_factory.py.
READ_TOOLS: frozenset[str] = frozenset({
    "web_search", "web_fetch", "paper_search", "paper_get", "read", "read_file",
    "grep", "find", "ls", "list_dir", "tavily_search", "arxiv_search",
})
WRITE_TOOLS: frozenset[str] = frozenset({
    "write_file", "edit_file", "apply_patch", "edit_diff", "write", "edit",
    "delete", "move", "create_docx", "create_pdf", "create_spreadsheet",
})
EXEC_TOOLS: frozenset[str] = frozenset({
    "exec", "bash", "shell", "run_command", "execute",
})
# External transfer: uploading to microforge/Qraft or any outbound send.
# ALWAYS confirm — independent of approval bypass.
EXTERNAL_TOOLS: frozenset[str] = frozenset({
    "upload_workflow", "upload", "platform_upload", "data_upload",
    "send_message", "send_file", "email_send", "slack_post", "feishu_send",
})
PAYMENT_TOOLS: frozenset[str] = frozenset({
    "purchase", "pay", "payment", "charge",
})

# Confirmation gate (9月 demo): (mode, risk) → verdict.
# Rules are explicit; unknown tools default to ALLOW (safety layer handles them).
_CONFIRM_MATRIX: dict[tuple[AutonomyMode, RiskLevel], CollabVerdict] = {
    # plan mode: everything not read-only is denied
    (AutonomyMode.PLAN, RiskLevel.WRITE): CollabVerdict.DENY,
    (AutonomyMode.PLAN, RiskLevel.EXEC): CollabVerdict.DENY,
    (AutonomyMode.PLAN, RiskLevel.EXTERNAL): CollabVerdict.DENY,
    (AutonomyMode.PLAN, RiskLevel.PAYMENT): CollabVerdict.DENY,
    # manual: every write/exec/external needs the card
    (AutonomyMode.MANUAL, RiskLevel.WRITE): CollabVerdict.CONFIRM,
    (AutonomyMode.MANUAL, RiskLevel.EXEC): CollabVerdict.CONFIRM,
    (AutonomyMode.MANUAL, RiskLevel.EXTERNAL): CollabVerdict.CONFIRM,
    (AutonomyMode.MANUAL, RiskLevel.PAYMENT): CollabVerdict.CONFIRM,
    # supervised: writes auto (like "允许编辑"), exec/external confirm
    (AutonomyMode.SUPERVISED, RiskLevel.EXEC): CollabVerdict.CONFIRM,
    (AutonomyMode.SUPERVISED, RiskLevel.EXTERNAL): CollabVerdict.CONFIRM,
    (AutonomyMode.SUPERVISED, RiskLevel.PAYMENT): CollabVerdict.CONFIRM,
    # autonomous: external/payment ALWAYS confirm (never bypassable)
    (AutonomyMode.AUTONOMOUS, RiskLevel.EXTERNAL): CollabVerdict.CONFIRM,
    (AutonomyMode.AUTONOMOUS, RiskLevel.PAYMENT): CollabVerdict.CONFIRM,
}


def risk_of(tool_name: str) -> RiskLevel:
    """Classify a tool name into a risk level (unknown → READ)."""
    if tool_name in PAYMENT_TOOLS:
        return RiskLevel.PAYMENT
    if tool_name in EXTERNAL_TOOLS:
        return RiskLevel.EXTERNAL
    if tool_name in EXEC_TOOLS:
        return RiskLevel.EXEC
    if tool_name in WRITE_TOOLS:
        return RiskLevel.WRITE
    return RiskLevel.READ


def evaluate(tool_name: str, mode: AutonomyMode) -> CollabVerdict:
    """Decide whether a tool call needs the confirm card.

    Independent of approval bypass: EXTERNAL/PAYMENT always confirm in every
    execution mode — the collaboration gate is not a safety toggle.
    """
    risk = risk_of(tool_name)
    verdict = _CONFIRM_MATRIX.get((mode, risk))
    if verdict is not None:
        return verdict
    # READ is always auto; anything unlisted defaults to allow.
    return CollabVerdict.ALLOW
