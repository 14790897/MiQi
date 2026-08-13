"""KUN runtime contracts — Pydantic v2 data models.

All models match the KUN TypeScript schemas (``kun/src/contracts/*.ts``)
so HTTP/SSE payloads are wire-compatible with the DeepSeek-GUI frontend.

Field names use camelCase to match the KUN JSON payloads directly;
Python code accesses them via attribute (``item.turnId``) with
``model_config.populate_by_name`` disabled — strict camelCase only.
"""

# ruff: noqa: N815  # camelCase field names match KUN HTTP/SSE wire format

from __future__ import annotations

from enum import Enum
from typing import Annotated, Any, Literal

from pydantic import BaseModel, Field, field_validator

# ═══════════════════════════════════════════════════════════════════════════════
# Shared primitives
# ═══════════════════════════════════════════════════════════════════════════════


class TurnItemRole(str, Enum):
    user = "user"
    assistant = "assistant"
    system = "system"
    tool = "tool"


class TurnItemStatus(str, Enum):
    pending = "pending"
    running = "running"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"


class TurnStatus(str, Enum):
    queued = "queued"
    running = "running"
    completed = "completed"
    failed = "failed"
    aborted = "aborted"


class ThreadStatus(str, Enum):
    idle = "idle"
    running = "running"
    archived = "archived"
    deleted = "deleted"


class ThreadMode(str, Enum):
    agent = "agent"
    plan = "plan"


class ThreadRelation(str, Enum):
    primary = "primary"
    fork = "fork"
    side = "side"


class ApprovalPolicy(str, Enum):
    never = "never"
    auto = "auto"
    suggest = "suggest"
    untrusted = "untrusted"


class SandboxMode(str, Enum):
    workspace_write = "workspace-write"
    readonly = "readonly"


class ThreadGoalStatus(str, Enum):
    active = "active"
    paused = "paused"
    blocked = "blocked"
    usage_limited = "usageLimited"
    budget_limited = "budgetLimited"
    complete = "complete"


class ThreadTodoStatus(str, Enum):
    pending = "pending"
    in_progress = "in_progress"
    completed = "completed"


class ToolKind(str, Enum):
    tool_call = "tool_call"
    command_execution = "command_execution"
    file_change = "file_change"


class ToolProviderKind(str, Enum):
    built_in = "built-in"
    mcp = "mcp"
    web = "web"
    memory = "memory"
    delegation = "delegation"
    gui = "gui"


class GuiPlanOperation(str, Enum):
    draft = "draft"
    refine = "refine"


class TurnReasoningEffort(str, Enum):
    auto = "auto"
    off = "off"
    low = "low"
    medium = "medium"
    high = "high"
    max = "max"


class TurnItemKind(str, Enum):
    user_message = "user_message"
    assistant_text = "assistant_text"
    assistant_reasoning = "assistant_reasoning"
    tool_call = "tool_call"
    tool_result = "tool_result"
    approval = "approval"
    user_input = "user_input"
    compaction = "compaction"
    review = "review"
    error = "error"


# ═══════════════════════════════════════════════════════════════════════════════
# TurnItem base
# ═══════════════════════════════════════════════════════════════════════════════


class _TurnItemBase(BaseModel):
    """Shared fields for all TurnItem variants."""

    id: str = Field(min_length=1)
    turnId: str = Field(min_length=1)
    threadId: str = Field(min_length=1)
    role: TurnItemRole
    status: TurnItemStatus
    createdAt: str
    finishedAt: str | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# TurnItem variants
# ═══════════════════════════════════════════════════════════════════════════════


class UserInputOption(BaseModel):
    label: str = Field(min_length=1)
    description: str


class UserInputQuestion(BaseModel):
    header: str = Field(min_length=1)
    id: str = Field(min_length=1)
    question: str = Field(min_length=1)
    options: list[UserInputQuestion] = Field(default_factory=list)
    """Recursive for nesting; a leaf question has empty options."""


class UserMessageItem(_TurnItemBase):
    kind: Literal[TurnItemKind.user_message] = TurnItemKind.user_message
    role: TurnItemRole = TurnItemRole.user
    text: str
    displayText: str | None = None
    attachmentIds: list[str] = Field(default_factory=list)


class AssistantTextItem(_TurnItemBase):
    kind: Literal[TurnItemKind.assistant_text] = TurnItemKind.assistant_text
    role: TurnItemRole = TurnItemRole.assistant
    text: str


class AssistantReasoningItem(_TurnItemBase):
    kind: Literal[TurnItemKind.assistant_reasoning] = TurnItemKind.assistant_reasoning
    role: TurnItemRole = TurnItemRole.assistant
    text: str


class ToolCallItem(_TurnItemBase):
    kind: Literal[TurnItemKind.tool_call] = TurnItemKind.tool_call
    role: TurnItemRole = TurnItemRole.assistant
    toolName: str = Field(min_length=1)
    callId: str = Field(min_length=1)
    toolKind: ToolKind
    arguments: dict[str, Any] = Field(default_factory=dict)
    summary: str | None = None


class ToolResultItem(_TurnItemBase):
    kind: Literal[TurnItemKind.tool_result] = TurnItemKind.tool_result
    role: TurnItemRole = TurnItemRole.tool
    toolName: str = Field(min_length=1)
    callId: str = Field(min_length=1)
    toolKind: ToolKind
    output: Any = None
    isError: bool = False


class ApprovalItem(_TurnItemBase):
    kind: Literal[TurnItemKind.approval] = TurnItemKind.approval
    role: TurnItemRole = TurnItemRole.system
    approvalId: str = Field(min_length=1)
    toolName: str = Field(min_length=1)
    summary: str
    status: Literal["pending", "allowed", "denied", "expired"]


class UserInputItem(_TurnItemBase):
    kind: Literal[TurnItemKind.user_input] = TurnItemKind.user_input
    role: TurnItemRole = TurnItemRole.system
    inputId: str = Field(min_length=1)
    prompt: str
    questions: list[dict[str, Any]] = Field(default_factory=list)
    status: Literal["pending", "submitted", "cancelled"]


class CompactionItem(_TurnItemBase):
    kind: Literal[TurnItemKind.compaction] = TurnItemKind.compaction
    role: TurnItemRole = TurnItemRole.system
    summary: str
    replacedTokens: int = Field(ge=0)
    pinnedConstraints: list[str] = Field(default_factory=list)
    sourceDigest: str | None = None
    digestMarker: str | None = None
    sourceItemIds: list[str] | None = None


class ReviewTarget(BaseModel):
    threadId: str = Field(min_length=1)
    turnId: str | None = None
    itemId: str | None = None


class ReviewOutput(BaseModel):
    findings: list[dict[str, Any]] = Field(default_factory=list)
    summary: str = ""


class ReviewItem(_TurnItemBase):
    kind: Literal[TurnItemKind.review] = TurnItemKind.review
    role: TurnItemRole = TurnItemRole.system
    target: ReviewTarget
    title: str = Field(min_length=1)
    reviewText: str | None = None
    output: ReviewOutput | None = None


class ErrorItem(_TurnItemBase):
    kind: Literal[TurnItemKind.error] = TurnItemKind.error
    role: TurnItemRole = TurnItemRole.system
    message: str
    code: str | None = None


TurnItem = Annotated[
    UserMessageItem
    | AssistantTextItem
    | AssistantReasoningItem
    | ToolCallItem
    | ToolResultItem
    | ApprovalItem
    | UserInputItem
    | CompactionItem
    | ReviewItem
    | ErrorItem,
    Field(discriminator="kind"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Thread / Turn models
# ═══════════════════════════════════════════════════════════════════════════════


class ThreadTodoSource(BaseModel):
    kind: Literal["plan"] = "plan"
    planId: str = Field(min_length=1)
    relativePath: str = Field(min_length=1)
    ordinal: int = Field(ge=0)
    contentHash: str = Field(min_length=1)


class ThreadTodoItem(BaseModel):
    id: str = Field(min_length=1)
    content: str = Field(min_length=1, max_length=1000)
    status: ThreadTodoStatus
    source: ThreadTodoSource | None = None
    createdAt: str
    updatedAt: str


class ThreadTodoList(BaseModel):
    threadId: str = Field(min_length=1)
    items: list[ThreadTodoItem] = Field(default_factory=list)
    updatedAt: str

    @field_validator("items")
    @classmethod
    def _at_most_one_in_progress(cls, v: list[ThreadTodoItem]) -> list[ThreadTodoItem]:
        in_progress = sum(1 for item in v if item.status == ThreadTodoStatus.in_progress)
        if in_progress > 1:
            raise ValueError("at most one todo can be in_progress")
        return v


class ThreadGoal(BaseModel):
    threadId: str = Field(min_length=1)
    objective: str = Field(min_length=1, max_length=4000)
    status: ThreadGoalStatus
    tokenBudget: int | None = None
    tokensUsed: int = Field(default=0, ge=0)
    timeUsedSeconds: int = Field(default=0, ge=0)
    createdAt: str
    updatedAt: str


class GuiPlanContext(BaseModel):
    operation: GuiPlanOperation
    workspaceRoot: str = Field(min_length=1)
    relativePath: str = Field(min_length=1)
    planId: str = Field(min_length=1)
    sourceRequest: str | None = None
    title: str | None = None


class Turn(BaseModel):
    id: str = Field(min_length=1)
    threadId: str = Field(min_length=1)
    status: TurnStatus
    prompt: str
    model: str | None = None
    reasoningEffort: TurnReasoningEffort | None = None
    steering: list[str] = Field(default_factory=list)
    createdAt: str
    startedAt: str | None = None
    finishedAt: str | None = None
    items: list[dict[str, Any]] = Field(default_factory=list)
    attachmentIds: list[str] = Field(default_factory=list)
    activeSkillIds: list[str] = Field(default_factory=list)
    injectedMemoryIds: list[str] = Field(default_factory=list)
    skillInjectionBytes: int | None = None
    toolCatalogFingerprint: str | None = None
    toolCatalogToolCount: int | None = None
    toolCatalogDrift: bool | None = None
    guiPlan: GuiPlanContext | None = None
    mode: ThreadMode | None = None
    error: str | None = None


class ThreadRecord(BaseModel):
    id: str = Field(min_length=1)
    title: str
    workspace: str
    model: str
    mode: ThreadMode
    status: ThreadStatus
    approvalPolicy: ApprovalPolicy = ApprovalPolicy.auto
    sandboxMode: SandboxMode = SandboxMode.workspace_write
    costBudgetUsd: float | None = None
    costBudgetWarningSent: bool = False
    relation: ThreadRelation = ThreadRelation.primary
    parentThreadId: str | None = None
    forkedFromThreadId: str | None = None
    forkedFromTitle: str | None = None
    forkedAt: str | None = None
    forkedFromMessageCount: int | None = None
    forkedFromTurnCount: int | None = None
    goal: ThreadGoal | None = None
    todos: ThreadTodoList | None = None
    createdAt: str
    updatedAt: str
    turns: list[Turn] = Field(default_factory=list)


class ThreadSummary(BaseModel):
    id: str = Field(min_length=1)
    title: str
    workspace: str
    model: str
    mode: ThreadMode
    status: ThreadStatus
    costBudgetUsd: float | None = None
    costBudgetWarningSent: bool = False
    relation: ThreadRelation = ThreadRelation.primary
    parentThreadId: str | None = None
    forkedFromThreadId: str | None = None
    forkedFromTitle: str | None = None
    forkedAt: str | None = None
    forkedFromMessageCount: int | None = None
    forkedFromTurnCount: int | None = None
    goal: ThreadGoal | None = None
    todos: ThreadTodoList | None = None
    createdAt: str
    updatedAt: str


# ═══════════════════════════════════════════════════════════════════════════════
# Usage
# ═══════════════════════════════════════════════════════════════════════════════


class UsageSnapshot(BaseModel):
    promptTokens: int = Field(default=0, ge=0)
    completionTokens: int = Field(default=0, ge=0)
    totalTokens: int = Field(default=0, ge=0)
    costUsd: float = Field(default=0.0, ge=0.0)
    cacheCreationInputTokens: int | None = None
    cacheReadInputTokens: int | None = None
    interStepTokens: int | None = None
    tokenEconomySavingsTokens: int | None = None
    tokenEconomySavingsUsd: float | None = None
    tokenEconomySavingsCny: float | None = None


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response models
# ═══════════════════════════════════════════════════════════════════════════════


class StartTurnRequest(BaseModel):
    prompt: str = Field(min_length=1)
    displayText: str | None = None
    model: str | None = None
    reasoningEffort: TurnReasoningEffort | None = None
    approvalPolicy: ApprovalPolicy | None = None
    mode: ThreadMode | None = None
    attachmentIds: list[str] = Field(default_factory=list)
    guiPlan: GuiPlanContext | None = None


class StartTurnResponse(BaseModel):
    threadId: str = Field(min_length=1)
    turnId: str = Field(min_length=1)
    userMessageItemId: str = Field(min_length=1)


class SteerTurnRequest(BaseModel):
    text: str = Field(min_length=1)


class InterruptTurnRequest(BaseModel):
    discard: bool = False


class InterruptTurnResponse(BaseModel):
    threadId: str = Field(min_length=1)
    turnId: str = Field(min_length=1)
    status: TurnStatus


class CompactRequest(BaseModel):
    reason: str | None = None
    budgetTokens: int | None = None


class CompactResponse(BaseModel):
    threadId: str = Field(min_length=1)
    replacedTokens: int = Field(ge=0)
    summary: str
    pinnedConstraints: list[str] = Field(default_factory=list)
    sourceDigest: str | None = None
    digestMarker: str | None = None
    sourceItemIds: list[str] | None = None


class CreateThreadRequest(BaseModel):
    title: str | None = None
    workspace: str = Field(min_length=1)
    model: str = Field(min_length=1)
    mode: ThreadMode = ThreadMode.agent
    approvalPolicy: ApprovalPolicy | None = None
    sandboxMode: SandboxMode | None = None
    costBudgetUsd: float | None = None


class ForkThreadRequest(BaseModel):
    relation: ThreadRelation = ThreadRelation.fork
    title: str | None = None


class UpdateThreadRequest(BaseModel):
    title: str | None = None
    status: ThreadStatus | None = None
    approvalPolicy: ApprovalPolicy | None = None
    sandboxMode: SandboxMode | None = None
    costBudgetUsd: float | None = None
    costBudgetWarningSent: bool | None = None
    relation: ThreadRelation | None = None


class SetThreadGoalRequest(BaseModel):
    objective: str | None = None
    status: ThreadGoalStatus | None = None
    tokenBudget: int | None = None


class ApprovalDecisionRequest(BaseModel):
    decision: Literal["allow", "deny"]


class UserInputResolveRequest(BaseModel):
    answers: dict[str, str] = Field(default_factory=dict)


# ═══════════════════════════════════════════════════════════════════════════════
# Model / tool specs
# ═══════════════════════════════════════════════════════════════════════════════


class ModelToolSpec(BaseModel):
    name: str = Field(min_length=1)
    description: str
    inputSchema: dict[str, Any] = Field(default_factory=dict)
    toolKind: ToolKind | None = None
    providerId: str | None = None
    providerKind: ToolProviderKind | None = None


class ModelCapabilityMetadata(BaseModel):
    id: str
    inputModalities: list[str] = Field(default_factory=list)
    messageParts: list[str] = Field(default_factory=list)
    maxInputTokens: int = Field(default=128_000, ge=0)
    maxOutputTokens: int = Field(default=8_192, ge=0)
    supportsPromptCaching: bool = False
    supportsReasoning: bool = False


# ═══════════════════════════════════════════════════════════════════════════════
# Pipeline stage
# ═══════════════════════════════════════════════════════════════════════════════

PipelineStage = Literal[
    "setup",
    "pre_start",
    "post_start",
    "input_received",
    "input_cached",
    "input_routed",
    "input_compressed",
    "input_remembered",
    "pre_send",
    "post_send",
    "response_received",
]

PIPELINE_STAGE_LABELS: dict[PipelineStage, str] = {
    "setup": "Setup",
    "pre_start": "Pre-Start",
    "post_start": "Post-Start",
    "input_received": "Input Received",
    "input_cached": "Input Cached",
    "input_routed": "Input Routed",
    "input_compressed": "Input Compressed",
    "input_remembered": "Input Remembered",
    "pre_send": "Pre-Send",
    "post_send": "Post-Send",
    "response_received": "Response Received",
}


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeEvent discriminated union
# ═══════════════════════════════════════════════════════════════════════════════


class _RuntimeEventBase(BaseModel):
    """Shared fields for all RuntimeEvent variants."""

    seq: int = Field(ge=0)
    timestamp: str
    threadId: str = Field(min_length=1)
    turnId: str | None = None
    itemId: str | None = None


class ThreadCreatedEvent(_RuntimeEventBase):
    kind: Literal["thread_created"] = "thread_created"
    title: str | None = None
    status: str | None = None


class ThreadUpdatedEvent(_RuntimeEventBase):
    kind: Literal["thread_updated"] = "thread_updated"
    title: str | None = None
    status: str | None = None


class TurnStartedEvent(_RuntimeEventBase):
    kind: Literal["turn_started"] = "turn_started"


class TurnCompletedEvent(_RuntimeEventBase):
    kind: Literal["turn_completed"] = "turn_completed"
    status: str | None = None


class TurnFailedEvent(_RuntimeEventBase):
    kind: Literal["turn_failed"] = "turn_failed"
    message: str | None = None


class TurnAbortedEvent(_RuntimeEventBase):
    kind: Literal["turn_aborted"] = "turn_aborted"
    message: str | None = None


class TurnSteeredEvent(_RuntimeEventBase):
    kind: Literal["turn_steered"] = "turn_steered"
    text: str | None = None


class ItemCreatedEvent(_RuntimeEventBase):
    kind: Literal["item_created"] = "item_created"
    item: dict[str, Any]


class ItemUpdatedEvent(_RuntimeEventBase):
    kind: Literal["item_updated"] = "item_updated"
    item: dict[str, Any]


class ItemCompletedEvent(_RuntimeEventBase):
    kind: Literal["item_completed"] = "item_completed"
    item: dict[str, Any] | None = None


class AssistantTextDeltaEvent(_RuntimeEventBase):
    kind: Literal["assistant_text_delta"] = "assistant_text_delta"
    item: dict[str, Any] | None = None


class AssistantReasoningDeltaEvent(_RuntimeEventBase):
    kind: Literal["assistant_reasoning_delta"] = "assistant_reasoning_delta"
    item: dict[str, Any] | None = None


class ToolCallReadyEvent(_RuntimeEventBase):
    kind: Literal["tool_call_ready"] = "tool_call_ready"
    toolName: str = Field(min_length=1)
    callId: str = Field(min_length=1)
    readyCount: int = Field(ge=1)


class ToolCallStartedEvent(_RuntimeEventBase):
    kind: Literal["tool_call_started"] = "tool_call_started"
    item: dict[str, Any] | None = None


class ToolCallFinishedEvent(_RuntimeEventBase):
    kind: Literal["tool_call_finished"] = "tool_call_finished"
    item: dict[str, Any] | None = None


class ToolResultUploadWaitEvent(_RuntimeEventBase):
    kind: Literal["tool_result_upload_wait"] = "tool_result_upload_wait"
    status: Literal["waiting"] = "waiting"
    toolResultCount: int = Field(ge=0)


class ToolStormSuppressedEvent(_RuntimeEventBase):
    kind: Literal["tool_storm_suppressed"] = "tool_storm_suppressed"
    toolName: str = Field(min_length=1)
    callId: str = Field(min_length=1)
    message: str


class ToolCatalogChangedEvent(_RuntimeEventBase):
    kind: Literal["tool_catalog_changed"] = "tool_catalog_changed"
    fingerprint: str = Field(min_length=1)
    toolCount: int = Field(ge=0)
    changeKind: Literal["additive", "breaking"] | None = None
    toolNames: list[str] | None = None
    message: str | None = None


class ApprovalRequestedEvent(_RuntimeEventBase):
    kind: Literal["approval_requested"] = "approval_requested"
    approvalId: str = Field(min_length=1)
    toolName: str = Field(min_length=1)
    status: Literal["pending"] = "pending"
    summary: str | None = None


class ApprovalResolvedEvent(_RuntimeEventBase):
    kind: Literal["approval_resolved"] = "approval_resolved"
    approvalId: str = Field(min_length=1)
    toolName: str = Field(min_length=1)
    status: Literal["allowed", "denied", "expired"]
    summary: str | None = None


class UserInputRequestedEvent(_RuntimeEventBase):
    kind: Literal["user_input_requested"] = "user_input_requested"
    inputId: str = Field(min_length=1)
    status: Literal["pending"] = "pending"
    prompt: str | None = None
    questions: list[dict[str, Any]] | None = None


class UserInputResolvedEvent(_RuntimeEventBase):
    kind: Literal["user_input_resolved"] = "user_input_resolved"
    inputId: str = Field(min_length=1)
    status: Literal["submitted", "cancelled"]
    prompt: str | None = None
    questions: list[dict[str, Any]] | None = None


class CompactionStartedEvent(_RuntimeEventBase):
    kind: Literal["compaction_started"] = "compaction_started"
    summary: str | None = None
    replacedTokens: int | None = None


class CompactionCompletedEvent(_RuntimeEventBase):
    kind: Literal["compaction_completed"] = "compaction_completed"
    summary: str | None = None
    replacedTokens: int | None = None
    pinnedConstraints: list[str] | None = None
    sourceDigest: str | None = None
    digestMarker: str | None = None
    sourceItemIds: list[str] | None = None


class GoalUpdatedEvent(_RuntimeEventBase):
    kind: Literal["goal_updated"] = "goal_updated"
    goal: dict[str, Any] | None = None


class GoalClearedEvent(_RuntimeEventBase):
    kind: Literal["goal_cleared"] = "goal_cleared"
    cleared: bool = True


class TodosUpdatedEvent(_RuntimeEventBase):
    kind: Literal["todos_updated"] = "todos_updated"
    todos: dict[str, Any] | None = None


class TodosClearedEvent(_RuntimeEventBase):
    kind: Literal["todos_cleared"] = "todos_cleared"
    cleared: bool = True


class PipelineStageEvent(_RuntimeEventBase):
    kind: Literal["pipeline_stage"] = "pipeline_stage"
    stage: PipelineStage
    label: str | None = None
    details: dict[str, Any] | None = None


class UsageEvent(_RuntimeEventBase):
    kind: Literal["usage"] = "usage"
    model: str | None = None
    usage: UsageSnapshot


class ErrorEvent(_RuntimeEventBase):
    kind: Literal["error"] = "error"
    message: str
    code: str | None = None


class HeartbeatEvent(_RuntimeEventBase):
    kind: Literal["heartbeat"] = "heartbeat"


RuntimeEvent = Annotated[
    ThreadCreatedEvent
    | ThreadUpdatedEvent
    | TurnStartedEvent
    | TurnCompletedEvent
    | TurnFailedEvent
    | TurnAbortedEvent
    | TurnSteeredEvent
    | ItemCreatedEvent
    | ItemUpdatedEvent
    | ItemCompletedEvent
    | AssistantTextDeltaEvent
    | AssistantReasoningDeltaEvent
    | ToolCallReadyEvent
    | ToolCallStartedEvent
    | ToolCallFinishedEvent
    | ToolResultUploadWaitEvent
    | ToolStormSuppressedEvent
    | ToolCatalogChangedEvent
    | ApprovalRequestedEvent
    | ApprovalResolvedEvent
    | UserInputRequestedEvent
    | UserInputResolvedEvent
    | CompactionStartedEvent
    | CompactionCompletedEvent
    | GoalUpdatedEvent
    | GoalClearedEvent
    | TodosUpdatedEvent
    | TodosClearedEvent
    | PipelineStageEvent
    | UsageEvent
    | ErrorEvent
    | HeartbeatEvent,
    Field(discriminator="kind"),
]


# ═══════════════════════════════════════════════════════════════════════════════
# Convenience re-exports
# ═══════════════════════════════════════════════════════════════════════════════

__all__ = [
    # Enums
    "TurnItemRole",
    "TurnItemStatus",
    "TurnStatus",
    "ThreadStatus",
    "ThreadMode",
    "ThreadRelation",
    "ApprovalPolicy",
    "SandboxMode",
    "ThreadGoalStatus",
    "ThreadTodoStatus",
    "ToolKind",
    "ToolProviderKind",
    "GuiPlanOperation",
    "TurnReasoningEffort",
    "TurnItemKind",
    # TurnItem variants
    "UserMessageItem",
    "AssistantTextItem",
    "AssistantReasoningItem",
    "ToolCallItem",
    "ToolResultItem",
    "ApprovalItem",
    "UserInputItem",
    "CompactionItem",
    "ReviewItem",
    "ErrorItem",
    "ReviewTarget",
    "ReviewOutput",
    "UserInputOption",
    "UserInputQuestion",
    "TurnItem",
    # Thread / Turn
    "ThreadRecord",
    "ThreadSummary",
    "Turn",
    "ThreadGoal",
    "ThreadTodoList",
    "ThreadTodoItem",
    "ThreadTodoSource",
    "GuiPlanContext",
    # Usage
    "UsageSnapshot",
    # Requests
    "StartTurnRequest",
    "StartTurnResponse",
    "SteerTurnRequest",
    "InterruptTurnRequest",
    "InterruptTurnResponse",
    "CompactRequest",
    "CompactResponse",
    "CreateThreadRequest",
    "ForkThreadRequest",
    "UpdateThreadRequest",
    "SetThreadGoalRequest",
    "ApprovalDecisionRequest",
    "UserInputResolveRequest",
    # Model
    "ModelToolSpec",
    "ModelCapabilityMetadata",
    # Events
    "PipelineStage",
    "PIPELINE_STAGE_LABELS",
    "ThreadCreatedEvent",
    "ThreadUpdatedEvent",
    "TurnStartedEvent",
    "TurnCompletedEvent",
    "TurnFailedEvent",
    "TurnAbortedEvent",
    "TurnSteeredEvent",
    "ItemCreatedEvent",
    "ItemUpdatedEvent",
    "ItemCompletedEvent",
    "AssistantTextDeltaEvent",
    "AssistantReasoningDeltaEvent",
    "ToolCallReadyEvent",
    "ToolCallStartedEvent",
    "ToolCallFinishedEvent",
    "ToolResultUploadWaitEvent",
    "ToolStormSuppressedEvent",
    "ToolCatalogChangedEvent",
    "ApprovalRequestedEvent",
    "ApprovalResolvedEvent",
    "UserInputRequestedEvent",
    "UserInputResolvedEvent",
    "CompactionStartedEvent",
    "CompactionCompletedEvent",
    "GoalUpdatedEvent",
    "GoalClearedEvent",
    "TodosUpdatedEvent",
    "TodosClearedEvent",
    "PipelineStageEvent",
    "UsageEvent",
    "ErrorEvent",
    "HeartbeatEvent",
    "RuntimeEvent",
]
