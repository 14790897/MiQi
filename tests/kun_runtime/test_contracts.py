"""Phase 1 tests — KUN runtime contracts: serialization, discriminator validation, defaults."""

from __future__ import annotations

import json

import pytest

from miqi.kun_runtime.contracts import (
    PIPELINE_STAGE_LABELS,
    ApprovalDecisionRequest,
    ApprovalItem,
    ApprovalPolicy,
    AssistantReasoningItem,
    AssistantTextItem,
    CompactionItem,
    CompactRequest,
    CompactResponse,
    CreateThreadRequest,
    ErrorItem,
    InterruptTurnRequest,
    InterruptTurnResponse,
    ModelCapabilityMetadata,
    ModelToolSpec,
    PipelineStageEvent,
    ReviewItem,
    ReviewTarget,
    SandboxMode,
    SetThreadGoalRequest,
    StartTurnRequest,
    StartTurnResponse,
    SteerTurnRequest,
    ThreadGoal,
    ThreadMode,
    ThreadRecord,
    ThreadStatus,
    ThreadTodoItem,
    ThreadTodoList,
    ThreadTodoStatus,
    ToolCallItem,
    ToolKind,
    ToolProviderKind,
    ToolResultItem,
    Turn,
    TurnItemKind,
    TurnStatus,
    UpdateThreadRequest,
    UsageEvent,
    UsageSnapshot,
    UserInputItem,
    UserInputResolveRequest,
    UserMessageItem,
)

# ═══════════════════════════════════════════════════════════════════════════════
# TurnItem round-trip tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUserMessageItem:
    def test_defaults(self) -> None:
        item = UserMessageItem(
            id="u1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            text="hello",
        )
        assert item.kind == TurnItemKind.user_message
        assert item.role == "user"
        assert item.attachmentIds == []
        assert item.finishedAt is None
        assert item.displayText is None

    def test_round_trip_json(self) -> None:
        item = UserMessageItem(
            id="u1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            text="hello world",
            displayText="hi",
            attachmentIds=["att1"],
            finishedAt="2026-01-01T00:01:00Z",
        )
        raw = item.model_dump_json()
        parsed = UserMessageItem.model_validate_json(raw)
        assert parsed.id == item.id
        assert parsed.text == "hello world"
        assert parsed.displayText == "hi"
        assert parsed.attachmentIds == ["att1"]

    def test_rejects_empty_id(self) -> None:
        with pytest.raises(ValueError):
            UserMessageItem(
                id="",
                turnId="t1",
                threadId="th1",
                status="completed",
                createdAt="2026-01-01T00:00:00Z",
                text="hello",
            )


class TestAssistantTextItem:
    def test_defaults(self) -> None:
        item = AssistantTextItem(
            id="a1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            text="response",
        )
        assert item.kind == TurnItemKind.assistant_text
        assert item.role == "assistant"

    def test_round_trip_json(self) -> None:
        item = AssistantTextItem(
            id="a1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            text="I will help with that",
        )
        raw = item.model_dump_json()
        parsed = AssistantTextItem.model_validate_json(raw)
        assert parsed.text == "I will help with that"


class TestAssistantReasoningItem:
    def test_round_trip_json(self) -> None:
        item = AssistantReasoningItem(
            id="r1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            text="Let me think about this...",
        )
        raw = item.model_dump_json()
        parsed = AssistantReasoningItem.model_validate_json(raw)
        assert parsed.kind == TurnItemKind.assistant_reasoning
        assert parsed.role == "assistant"


class TestToolCallItem:
    def test_round_trip_json(self) -> None:
        item = ToolCallItem(
            id="tc1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            toolName="read",
            callId="call_1",
            toolKind=ToolKind.tool_call,
            arguments={"path": "test.txt"},
        )
        raw = item.model_dump_json()
        parsed = ToolCallItem.model_validate_json(raw)
        assert parsed.toolName == "read"
        assert parsed.callId == "call_1"
        assert parsed.arguments == {"path": "test.txt"}

    def test_rejects_empty_tool_name(self) -> None:
        with pytest.raises(ValueError):
            ToolCallItem(
                id="tc1",
                turnId="t1",
                threadId="th1",
                status="completed",
                createdAt="2026-01-01T00:00:00Z",
                toolName="",
                callId="call_1",
                toolKind=ToolKind.tool_call,
                arguments={},
            )


class TestToolResultItem:
    def test_round_trip_json(self) -> None:
        item = ToolResultItem(
            id="tr1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            toolName="read",
            callId="call_1",
            toolKind=ToolKind.tool_call,
            output="file contents here",
        )
        raw = item.model_dump_json()
        parsed = ToolResultItem.model_validate_json(raw)
        assert parsed.output == "file contents here"
        assert parsed.isError is False

    def test_error_default(self) -> None:
        item = ToolResultItem(
            id="tr1",
            turnId="t1",
            threadId="th1",
            status="failed",
            createdAt="2026-01-01T00:00:00Z",
            toolName="read",
            callId="call_1",
            toolKind=ToolKind.tool_call,
            output="not found",
            isError=True,
        )
        assert item.isError is True


class TestApprovalItem:
    def test_round_trip_json(self) -> None:
        item = ApprovalItem(
            id="ap1",
            turnId="t1",
            threadId="th1",
            status="pending",
            createdAt="2026-01-01T00:00:00Z",
            approvalId="app_1",
            toolName="bash",
            summary="rm -rf / important-dir",
        )
        raw = item.model_dump_json()
        parsed = ApprovalItem.model_validate_json(raw)
        assert parsed.kind == TurnItemKind.approval
        assert parsed.status == "pending"


class TestUserInputItem:
    def test_round_trip_json(self) -> None:
        item = UserInputItem(
            id="ui1",
            turnId="t1",
            threadId="th1",
            status="pending",
            createdAt="2026-01-01T00:00:00Z",
            inputId="input_1",
            prompt="Which file?",
            questions=[],
        )
        raw = item.model_dump_json()
        parsed = UserInputItem.model_validate_json(raw)
        assert parsed.kind == TurnItemKind.user_input
        assert parsed.status == "pending"


class TestCompactionItem:
    def test_round_trip_json(self) -> None:
        item = CompactionItem(
            id="c1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            summary="Earlier conversation summarized.",
            replacedTokens=5000,
        )
        raw = item.model_dump_json()
        parsed = CompactionItem.model_validate_json(raw)
        assert parsed.kind == TurnItemKind.compaction
        assert parsed.replacedTokens == 5000

    def test_rejects_negative_tokens(self) -> None:
        with pytest.raises(ValueError):
            CompactionItem(
                id="c1",
                turnId="t1",
                threadId="th1",
                status="completed",
                createdAt="2026-01-01T00:00:00Z",
                summary="bad",
                replacedTokens=-1,
            )


class TestReviewItem:
    def test_round_trip_json(self) -> None:
        item = ReviewItem(
            id="rv1",
            turnId="t1",
            threadId="th1",
            status="completed",
            createdAt="2026-01-01T00:00:00Z",
            target=ReviewTarget(threadId="th1", turnId="t1"),
            title="Code review",
        )
        raw = item.model_dump_json()
        parsed = ReviewItem.model_validate_json(raw)
        assert parsed.kind == TurnItemKind.review
        assert parsed.target.threadId == "th1"


class TestErrorItem:
    def test_round_trip_json(self) -> None:
        item = ErrorItem(
            id="e1",
            turnId="t1",
            threadId="th1",
            status="failed",
            createdAt="2026-01-01T00:00:00Z",
            message="something went wrong",
            code="INTERNAL_ERROR",
        )
        raw = item.model_dump_json()
        parsed = ErrorItem.model_validate_json(raw)
        assert parsed.kind == TurnItemKind.error
        assert parsed.code == "INTERNAL_ERROR"

    def test_no_code_default(self) -> None:
        item = ErrorItem(
            id="e1",
            turnId="t1",
            threadId="th1",
            status="failed",
            createdAt="2026-01-01T00:00:00Z",
            message="oops",
        )
        assert item.code is None


# ═══════════════════════════════════════════════════════════════════════════════
# Discriminated union tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestTurnItemDiscriminator:
    """Verify that JSON with kind fields deserializes to the correct variant."""

    def test_user_message(self) -> None:
        raw = json.dumps({
            "kind": "user_message",
            "id": "u1",
            "turnId": "t1",
            "threadId": "th1",
            "role": "user",
            "status": "completed",
            "createdAt": "2026-01-01T00:00:00Z",
            "text": "hello",
        })
        item = UserMessageItem.model_validate_json(raw)
        assert isinstance(item, UserMessageItem)

    def test_tool_call(self) -> None:
        raw = json.dumps({
            "kind": "tool_call",
            "id": "tc1",
            "turnId": "t1",
            "threadId": "th1",
            "role": "assistant",
            "status": "completed",
            "createdAt": "2026-01-01T00:00:00Z",
            "toolName": "read",
            "callId": "call_1",
            "toolKind": "tool_call",
            "arguments": {"path": "a.txt"},
        })
        item = ToolCallItem.model_validate_json(raw)
        assert isinstance(item, ToolCallItem)

    def test_tool_result(self) -> None:
        raw = json.dumps({
            "kind": "tool_result",
            "id": "tr1",
            "turnId": "t1",
            "threadId": "th1",
            "role": "tool",
            "status": "completed",
            "createdAt": "2026-01-01T00:00:00Z",
            "toolName": "read",
            "callId": "call_1",
            "toolKind": "tool_call",
            "output": "content",
        })
        item = ToolResultItem.model_validate_json(raw)
        assert isinstance(item, ToolResultItem)

    def test_approval(self) -> None:
        raw = json.dumps({
            "kind": "approval",
            "id": "ap1",
            "turnId": "t1",
            "threadId": "th1",
            "role": "system",
            "status": "pending",
            "createdAt": "2026-01-01T00:00:00Z",
            "approvalId": "app_1",
            "toolName": "bash",
            "summary": "dangerous",
        })
        item = ApprovalItem.model_validate_json(raw)
        assert isinstance(item, ApprovalItem)

    def test_compaction(self) -> None:
        raw = json.dumps({
            "kind": "compaction",
            "id": "c1",
            "turnId": "t1",
            "threadId": "th1",
            "role": "system",
            "status": "completed",
            "createdAt": "2026-01-01T00:00:00Z",
            "summary": "...",
            "replacedTokens": 100,
        })
        item = CompactionItem.model_validate_json(raw)
        assert isinstance(item, CompactionItem)

    def test_error(self) -> None:
        raw = json.dumps({
            "kind": "error",
            "id": "e1",
            "turnId": "t1",
            "threadId": "th1",
            "role": "system",
            "status": "failed",
            "createdAt": "2026-01-01T00:00:00Z",
            "message": "fail",
        })
        item = ErrorItem.model_validate_json(raw)
        assert isinstance(item, ErrorItem)


# ═══════════════════════════════════════════════════════════════════════════════
# TurnItem enum validation
# ═══════════════════════════════════════════════════════════════════════════════


class TestTurnItemEnumRejection:
    def test_rejects_invalid_status(self) -> None:
        with pytest.raises(ValueError):
            UserMessageItem(
                id="u1",
                turnId="t1",
                threadId="th1",
                status="bogus",  # type: ignore[arg-type]
                createdAt="2026-01-01T00:00:00Z",
                text="hello",
            )

    def test_rejects_invalid_role(self) -> None:
        with pytest.raises(ValueError):
            UserMessageItem(
                id="u1",
                turnId="t1",
                threadId="th1",
                role="bogus",  # type: ignore[arg-type]
                status="completed",
                createdAt="2026-01-01T00:00:00Z",
                text="hello",
            )

    def test_rejects_wrong_kind(self) -> None:
        with pytest.raises(ValueError):
            UserMessageItem(
                id="u1",
                turnId="t1",
                threadId="th1",
                kind="assistant_text",  # type: ignore[arg-type]
                status="completed",
                createdAt="2026-01-01T00:00:00Z",
                text="hello",
            )


# ═══════════════════════════════════════════════════════════════════════════════
# Thread / Turn model tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestThreadRecord:
    def test_minimal_creation(self) -> None:
        th = ThreadRecord(
            id="th1",
            title="Test Thread",
            workspace="/tmp/ws",
            model="deepseek-chat",
            mode=ThreadMode.agent,
            status=ThreadStatus.idle,
            createdAt="2026-01-01T00:00:00Z",
            updatedAt="2026-01-01T00:00:00Z",
        )
        assert th.mode == ThreadMode.agent
        assert th.status == ThreadStatus.idle
        assert th.approvalPolicy == ApprovalPolicy.auto
        assert th.sandboxMode == SandboxMode.workspace_write
        assert th.relation == "primary"
        assert th.turns == []
        assert th.costBudgetWarningSent is False

    def test_round_trip_json(self) -> None:
        th = ThreadRecord(
            id="th1",
            title="My Thread",
            workspace="/tmp/ws",
            model="deepseek-chat",
            mode=ThreadMode.agent,
            status=ThreadStatus.idle,
            createdAt="2026-01-01T00:00:00Z",
            updatedAt="2026-01-01T00:00:00Z",
        )
        raw = th.model_dump_json()
        parsed = ThreadRecord.model_validate_json(raw)
        assert parsed.id == "th1"
        assert parsed.title == "My Thread"

    def test_with_goal(self) -> None:
        th = ThreadRecord(
            id="th1",
            title="Goal Thread",
            workspace="/tmp/ws",
            model="deepseek-chat",
            mode=ThreadMode.agent,
            status=ThreadStatus.idle,
            createdAt="2026-01-01T00:00:00Z",
            updatedAt="2026-01-01T00:00:00Z",
            goal=ThreadGoal(
                threadId="th1",
                objective="Build a web app",
                status="active",
                createdAt="2026-01-01T00:00:00Z",
                updatedAt="2026-01-01T00:00:00Z",
            ),
        )
        assert th.goal is not None
        assert th.goal.objective == "Build a web app"
        raw = th.model_dump_json()
        parsed = ThreadRecord.model_validate_json(raw)
        assert parsed.goal is not None
        assert parsed.goal.objective == "Build a web app"


class TestThreadTodoList:
    def test_valid_todos(self) -> None:
        todos = ThreadTodoList(
            threadId="th1",
            items=[
                ThreadTodoItem(
                    id="todo_1",
                    content="Add auth",
                    status=ThreadTodoStatus.in_progress,
                    createdAt="2026-01-01T00:00:00Z",
                    updatedAt="2026-01-01T00:00:00Z",
                ),
                ThreadTodoItem(
                    id="todo_2",
                    content="Add dashboard",
                    status=ThreadTodoStatus.pending,
                    createdAt="2026-01-01T00:00:00Z",
                    updatedAt="2026-01-01T00:00:00Z",
                ),
            ],
            updatedAt="2026-01-01T00:00:00Z",
        )
        assert len(todos.items) == 2

    def test_rejects_multiple_in_progress(self) -> None:
        with pytest.raises(ValueError):
            ThreadTodoList(
                threadId="th1",
                items=[
                    ThreadTodoItem(
                        id="todo_1",
                        content="A",
                        status=ThreadTodoStatus.in_progress,
                        createdAt="2026-01-01T00:00:00Z",
                        updatedAt="2026-01-01T00:00:00Z",
                    ),
                    ThreadTodoItem(
                        id="todo_2",
                        content="B",
                        status=ThreadTodoStatus.in_progress,
                        createdAt="2026-01-01T00:00:00Z",
                        updatedAt="2026-01-01T00:00:00Z",
                    ),
                ],
                updatedAt="2026-01-01T00:00:00Z",
            )


class TestTurn:
    def test_minimal_creation(self) -> None:
        turn = Turn(
            id="t1",
            threadId="th1",
            status=TurnStatus.queued,
            prompt="hello",
            createdAt="2026-01-01T00:00:00Z",
        )
        assert turn.status == TurnStatus.queued
        assert turn.steering == []
        assert turn.items == []
        assert turn.attachmentIds == []

    def test_round_trip_json(self) -> None:
        turn = Turn(
            id="t1",
            threadId="th1",
            status=TurnStatus.completed,
            prompt="hello world",
            model="deepseek-chat",
            createdAt="2026-01-01T00:00:00Z",
            startedAt="2026-01-01T00:00:01Z",
            finishedAt="2026-01-01T00:00:05Z",
        )
        raw = turn.model_dump_json()
        parsed = Turn.model_validate_json(raw)
        assert parsed.id == "t1"
        assert parsed.prompt == "hello world"
        assert parsed.status == TurnStatus.completed


# ═══════════════════════════════════════════════════════════════════════════════
# Request / Response tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestStartTurnRequest:
    def test_minimal(self) -> None:
        req = StartTurnRequest(prompt="hello")
        assert req.prompt == "hello"
        assert req.attachmentIds == []
        assert req.model is None

    def test_full(self) -> None:
        req = StartTurnRequest(
            prompt="do the thing",
            model="deepseek-chat",
            mode=ThreadMode.plan,
            attachmentIds=["att1"],
        )
        raw = req.model_dump_json()
        parsed = StartTurnRequest.model_validate_json(raw)
        assert parsed.mode == ThreadMode.plan
        assert parsed.attachmentIds == ["att1"]

    def test_rejects_empty_prompt(self) -> None:
        with pytest.raises(ValueError):
            StartTurnRequest(prompt="")


class TestStartTurnResponse:
    def test_round_trip(self) -> None:
        resp = StartTurnResponse(
            threadId="th1",
            turnId="t1",
            userMessageItemId="item_t1_user",
        )
        raw = resp.model_dump_json()
        parsed = StartTurnResponse.model_validate_json(raw)
        assert parsed.threadId == "th1"


class TestSteerTurnRequest:
    def test_round_trip(self) -> None:
        req = SteerTurnRequest(text="also check the logs")
        raw = req.model_dump_json()
        parsed = SteerTurnRequest.model_validate_json(raw)
        assert parsed.text == "also check the logs"

    def test_rejects_empty(self) -> None:
        with pytest.raises(ValueError):
            SteerTurnRequest(text="")


class TestInterruptTurn:
    def test_request_default(self) -> None:
        req = InterruptTurnRequest()
        assert req.discard is False

    def test_response_round_trip(self) -> None:
        resp = InterruptTurnResponse(
            threadId="th1",
            turnId="t1",
            status=TurnStatus.aborted,
        )
        raw = resp.model_dump_json()
        parsed = InterruptTurnResponse.model_validate_json(raw)
        assert parsed.status == TurnStatus.aborted


class TestCompactRequest:
    def test_round_trip(self) -> None:
        req = CompactRequest(reason="context too large", budgetTokens=10000)
        raw = req.model_dump_json()
        parsed = CompactRequest.model_validate_json(raw)
        assert parsed.reason == "context too large"
        assert parsed.budgetTokens == 10000


class TestCompactResponse:
    def test_round_trip(self) -> None:
        resp = CompactResponse(
            threadId="th1",
            replacedTokens=5000,
            summary="Earlier conversation was about...",
        )
        raw = resp.model_dump_json()
        parsed = CompactResponse.model_validate_json(raw)
        assert parsed.replacedTokens == 5000
        assert parsed.summary == "Earlier conversation was about..."


class TestCreateThreadRequest:
    def test_minimal(self) -> None:
        req = CreateThreadRequest(workspace="/tmp/ws", model="deepseek-chat")
        assert req.mode == ThreadMode.agent

    def test_round_trip(self) -> None:
        req = CreateThreadRequest(
            title="My Project",
            workspace="/tmp/ws",
            model="deepseek-chat",
            mode=ThreadMode.plan,
            approvalPolicy=ApprovalPolicy.suggest,
            costBudgetUsd=1.0,
        )
        raw = req.model_dump_json()
        parsed = CreateThreadRequest.model_validate_json(raw)
        assert parsed.title == "My Project"
        assert parsed.costBudgetUsd == 1.0


class TestUpdateThreadRequest:
    def test_partial_update(self) -> None:
        req = UpdateThreadRequest(title="New Title")
        raw = req.model_dump_json()
        parsed = UpdateThreadRequest.model_validate_json(raw)
        assert parsed.title == "New Title"
        assert parsed.status is None


class TestSetThreadGoalRequest:
    def test_round_trip(self) -> None:
        req = SetThreadGoalRequest(
            objective="Build a CLI tool",
            status="active",
            tokenBudget=100000,
        )
        raw = req.model_dump_json()
        parsed = SetThreadGoalRequest.model_validate_json(raw)
        assert parsed.objective == "Build a CLI tool"


class TestApprovalDecisionRequest:
    def test_allow(self) -> None:
        req = ApprovalDecisionRequest(decision="allow")
        raw = req.model_dump_json()
        parsed = ApprovalDecisionRequest.model_validate_json(raw)
        assert parsed.decision == "allow"

    def test_rejects_bogus(self) -> None:
        with pytest.raises(ValueError):
            ApprovalDecisionRequest(decision="maybe")  # type: ignore[arg-type]


class TestUserInputResolveRequest:
    def test_defaults(self) -> None:
        req = UserInputResolveRequest()
        assert req.answers == {}

    def test_with_answers(self) -> None:
        req = UserInputResolveRequest(answers={"q1": "yes"})
        raw = req.model_dump_json()
        parsed = UserInputResolveRequest.model_validate_json(raw)
        assert parsed.answers == {"q1": "yes"}


# ═══════════════════════════════════════════════════════════════════════════════
# Usage snapshot tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestUsageSnapshot:
    def test_defaults(self) -> None:
        snap = UsageSnapshot()
        assert snap.promptTokens == 0
        assert snap.completionTokens == 0
        assert snap.totalTokens == 0
        assert snap.costUsd == 0.0

    def test_round_trip_json(self) -> None:
        snap = UsageSnapshot(
            promptTokens=1000,
            completionTokens=500,
            totalTokens=1500,
            costUsd=0.003,
        )
        raw = snap.model_dump_json()
        parsed = UsageSnapshot.model_validate_json(raw)
        assert parsed.promptTokens == 1000
        assert parsed.costUsd == 0.003


# ═══════════════════════════════════════════════════════════════════════════════
# Model spec tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestModelToolSpec:
    def test_round_trip(self) -> None:
        spec = ModelToolSpec(
            name="read",
            description="Read a file",
            inputSchema={
                "type": "object",
                "properties": {
                    "path": {"type": "string"}
                },
            },
            toolKind="tool_call",
            providerKind=ToolProviderKind.built_in,
        )
        raw = spec.model_dump_json()
        parsed = ModelToolSpec.model_validate_json(raw)
        assert parsed.name == "read"
        assert parsed.inputSchema["type"] == "object"


class TestModelCapabilityMetadata:
    def test_defaults(self) -> None:
        cap = ModelCapabilityMetadata(id="deepseek-chat")
        assert cap.id == "deepseek-chat"
        assert cap.maxInputTokens == 128_000
        assert cap.supportsPromptCaching is False

    def test_round_trip(self) -> None:
        cap = ModelCapabilityMetadata(
            id="deepseek-chat",
            inputModalities=["text"],
            messageParts=["text"],
            maxInputTokens=96000,
            maxOutputTokens=8192,
        )
        raw = cap.model_dump_json()
        parsed = ModelCapabilityMetadata.model_validate_json(raw)
        assert parsed.maxInputTokens == 96000


# ═══════════════════════════════════════════════════════════════════════════════
# RuntimeEvent tests
# ═══════════════════════════════════════════════════════════════════════════════


class TestRuntimeEvent:
    def test_usage_event_round_trip(self) -> None:
        snap = UsageSnapshot(
            promptTokens=100,
            completionTokens=50,
            totalTokens=150,
            costUsd=0.0003,
        )
        event = UsageEvent(
            seq=1,
            timestamp="2026-01-01T00:00:00Z",
            threadId="th1",
            turnId="t1",
            model="deepseek-chat",
            usage=snap,
        )
        raw = event.model_dump_json()
        parsed = UsageEvent.model_validate_json(raw)
        assert parsed.kind == "usage"
        assert parsed.usage.promptTokens == 100

    def test_pipeline_stage_event(self) -> None:
        event = PipelineStageEvent(
            seq=1,
            timestamp="2026-01-01T00:00:00Z",
            threadId="th1",
            turnId="t1",
            stage="setup",
            label=PIPELINE_STAGE_LABELS["setup"],
            details={"stepIndex": 0},
        )
        raw = event.model_dump_json()
        parsed = PipelineStageEvent.model_validate_json(raw)
        assert parsed.kind == "pipeline_stage"
        assert parsed.stage == "setup"
