"""Agent Task Lifecycle 数据模型 — #646-v2 v3.3 最终拍板（2026-08-18）。

核心（ChatGPT 最终评审 + Grok todo 研究吸收）：
- PlanSnapshot = 用户批准事实（immutable）——一旦 confirm 不可静默修改
- TodoState = Agent 执行状态（mutable）——模型 todo_write / harness 事件写入
- Timeline = TodoState 的 projection（前端只见 id/title/status）
- 状态机：QUEUED→IN_PROGRESS→COMPLETED；IN_PROGRESS⇄BLOCKED；任何→CANCELLED
  （禁止 COMPLETED→IN_PROGRESS 除非人工）
- plan item 只允许 status transition（禁 delete/rename/改 content）
  ——改核心计划 → PLAN_MUTATION_REQUIRES_CONFIRMATION
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import datetime, timezone
from typing import Literal

# ── Todo 状态（v3.3：QUEUED 新增——已批准等待 Agent 开始）──────────
TodoStatus = Literal["queued", "in_progress", "blocked", "completed", "cancelled"]

# 允许的状态转换（transition validator）
_ALLOWED_TRANSITIONS: dict[TodoStatus, set[TodoStatus]] = {
    "queued": {"in_progress", "cancelled"},
    "in_progress": {"completed", "blocked", "cancelled"},
    "blocked": {"in_progress", "cancelled"},
    "completed": {"cancelled"},   # 任何状态→CANCELLED（v3.3）；禁止回滚到 IN_PROGRESS
    "cancelled": set(),           # 终态
}


def validate_transition(old: TodoStatus, new: TodoStatus) -> bool:
    """transition validator（v3.3 Q7）——P0 必须。"""
    if old == new:
        return True
    return new in _ALLOWED_TRANSITIONS.get(old, set())


# ── TodoItem（kind/source 仅后端——前端 DTO 不暴露）────────────────
@dataclasses.dataclass
class TodoItem:
    id: str
    content: str
    status: TodoStatus = "queued"
    kind: Literal["plan", "auxiliary", "observed"] = "plan"
    source: Literal["model", "harness"] = "model"
    blocked_reason: str | None = None


# ── TodoState（merge 更新 + revision）──────────────────────────────
class TodoMutationError(Exception):
    """error-as-output 语义（v3.3：不抛给模型的普通 error——rejected 结果）。"""


@dataclasses.dataclass
class TodoState:
    run_id: str
    revision: int = 0
    items: list[TodoItem] = dataclasses.field(default_factory=list)

    def item(self, item_id: str) -> TodoItem | None:
        return next((i for i in self.items if i.id == item_id), None)

    def initialize_from_plan(self, steps: list[tuple[str, str]]) -> None:
        """Plan confirm → TodoState 初始化（plan-kind，QUEUED，稳定 ID）。"""
        self.items = [
            TodoItem(id=step_id, content=content, status="queued", kind="plan", source="model")
            for step_id, content in steps
        ]
        self.revision += 1

    def merge(self, patches: list[dict]) -> list[dict]:
        """merge 增量更新（v3.3）：
        - {id, status} → 状态翻转（transition validator 校验）
        - {id, content, kind:"auxiliary", status?} → 新增辅助步骤
        - plan item 改 content / 删除 / rename → 拒绝（error-as-output）
        """
        rejected: list[dict] = []
        for p in patches:
            item_id = str(p.get("id") or "")
            status = p.get("status")
            content = p.get("content")
            kind = p.get("kind")

            existing = self.item(item_id)
            if existing is None:
                # 新增：只允许 auxiliary/observed（plan 新增必须走 PlanCard）
                if kind in ("auxiliary", "observed") and content:
                    self.items.append(TodoItem(
                        id=item_id, content=str(content),
                        status=str(status or "queued"),  # type: ignore[arg-type]
                        kind=kind,  # type: ignore[arg-type]
                        source="model" if kind == "auxiliary" else "harness",
                    ))
                    self.revision += 1
                    continue
                rejected.append({
                    "status": "rejected",
                    "reason": "PLAN_MUTATION_REQUIRES_CONFIRMATION",
                    "suggestion": "ask_user_plan_confirm",
                    "id": item_id,
                })
                continue

            # 已有条目
            if content and existing.kind == "plan":
                # plan item 改 content → 拒绝（v3.3：merge 禁止 rename/改内容）
                rejected.append({
                    "status": "rejected",
                    "reason": "PLAN_MUTATION_REQUIRES_CONFIRMATION",
                    "suggestion": "ask_user_plan_confirm",
                    "id": item_id,
                })
                continue
            if content and existing.kind == "auxiliary":
                existing.content = str(content)
                self.revision += 1
                continue
            if status:
                if not validate_transition(existing.status, str(status)):  # type: ignore[arg-type]
                    rejected.append({
                        "status": "rejected",
                        "reason": f"INVALID_TRANSITION: {existing.status} -> {status}",
                        "id": item_id,
                    })
                    continue
                existing.status = status  # type: ignore[assignment]
                if status == "blocked" and p.get("blocked_reason"):
                    existing.blocked_reason = str(p["blocked_reason"])
                elif status != "blocked":
                    # kimi-k2.6 审：离开 blocked 状态清残留 reason（避免过期信息）
                    existing.blocked_reason = None
                self.revision += 1
        return rejected

    def summary(self) -> dict:
        """summary_for_prompt（v3.3：结构化短摘要——不塞全列表）。"""
        counts = {"queued": 0, "in_progress": 0, "blocked": 0, "completed": 0, "cancelled": 0}
        in_progress: list[str] = []
        for it in self.items:
            counts[it.status] = counts.get(it.status, 0) + 1
            if it.status == "in_progress":
                in_progress.append(it.content)
        return {
            "total": len(self.items),
            "completed": counts["completed"],
            "in_progress": in_progress,
            "pending": counts["queued"] + counts["in_progress"],
            "blocked": counts["blocked"],
        }


# ── PlanSnapshot（immutable——用户批准事实）────────────────────────
@dataclasses.dataclass
class ArtifactRef:
    type: str
    name: str


@dataclasses.dataclass
class ExternalAction:
    provider: str
    operation: str


@dataclasses.dataclass(frozen=True)
class ApprovedScope:
    """结构化 scope（v3.3 Q5）——mutation detection 可比较（非字符串匹配）。
    frozen + tuple：kimi-k2.6 审——PlanSnapshot 深不可变（防
    approved_scope.sources.append 破坏'用户批准事实'）。"""
    sources: tuple[str, ...] = ()
    artifacts: tuple[ArtifactRef, ...] = ()
    external_actions: tuple[ExternalAction, ...] = ()

    def __post_init__(self) -> None:
        object.__setattr__(self, "sources", tuple(self.sources))
        object.__setattr__(self, "artifacts", tuple(self.artifacts))
        object.__setattr__(self, "external_actions", tuple(self.external_actions))


@dataclasses.dataclass(frozen=True)
class PlanSnapshot:
    """不可变（Frozen Plan——用户批准的事实，CodeRabbit 强化）。"""
    plan_id: str
    goal: str
    steps: tuple[tuple[str, str], ...]  # [(id, content)]——tuple 不可变

    def __post_init__(self) -> None:
        # CodeRabbit Major：深不可变——调用方传入的 list 也归一为 tuple
        object.__setattr__(self, "steps", tuple(tuple(p) for p in self.steps))
    approved_scope: ApprovedScope = dataclasses.field(default_factory=ApprovedScope)
    plan_version: int = 1
    approved_at: str = dataclasses.field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    approved_by: str = "user"


# ── AgentRunContext（v3.3 Q1：一次 Agent 工作流执行实例——非 session）─
@dataclasses.dataclass
class AgentRunContext:
    run_id: str = dataclasses.field(default_factory=lambda: uuid.uuid4().hex[:12])
    session_key: str = ""
    plan_snapshot: PlanSnapshot | None = None
    todo_state: TodoState = dataclasses.field(default_factory=lambda: TodoState(run_id=""))
    action_history: list[dict] = dataclasses.field(default_factory=list)

    def __post_init__(self):
        if not self.todo_state.run_id:
            self.todo_state.run_id = self.run_id
