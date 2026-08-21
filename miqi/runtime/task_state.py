"""TaskState — #646-v2 任务级状态机（GPT 评审拍板）。

区分于工具级确认：#646 是「任务计划决策点」——状态跟随一个 task 生命周期：

    PLANNING → WAIT_CONFIRM → RUNNING → WAIT_DANGEROUS_ACTION → COMPLETED
                                  │                                  │
                                  └──────── CANCELLED ←─────────────┘

用法（挂 session/task 上下文，前端进度面板读取）：
    task = TaskState.create(session_key, title, goal, steps, permissions)
    task.confirm() / task.cancel() / task.mark_dangerous() / task.complete()
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TaskPhase(str, Enum):
    PLANNING = "planning"                    # Agent 正在规划
    WAIT_USER_PLAN_CONFIRM = "wait_user_plan_confirm"  # Plan Card 等待用户确认（GPT 冻结命名）
    RUNNING = "running"                      # 已确认，执行中
    WAIT_ACTION_CONFIRM = "wait_action_confirm"        # 危险动作前（Action Card）
    COMPLETED = "completed"
    CANCELLED = "cancelled"


@dataclass
class TaskState:
    task_id: str
    session_key: str
    phase: TaskPhase = TaskPhase.PLANNING
    title: str = ""
    goal: str = ""
    steps: list[dict[str, Any]] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    step_status: dict[str, str] = field(default_factory=dict)  # name → pending/running/done/failed
    created_at: float = field(default_factory=time.time)
    updated_at: float = field(default_factory=time.time)

    @classmethod
    def create(
        cls,
        session_key: str,
        *,
        title: str,
        goal: str,
        steps: list[dict[str, Any]],
        permissions: list[str],
    ) -> "TaskState":
        return cls(
            task_id=f"task_{uuid.uuid4().hex[:12]}",
            session_key=session_key,
            phase=TaskPhase.WAIT_CONFIRM,
            title=title,
            goal=goal,
            steps=steps,
            permissions=permissions,
            step_status={s.get("name", f"step_{i}"): "pending" for i, s in enumerate(steps)},
        )

    # ── transitions ────────────────────────────────────────────────
    def confirm(self) -> None:
        self.phase = TaskPhase.RUNNING
        self._touch()

    def cancel(self) -> None:
        self.phase = TaskPhase.CANCELLED
        self._touch()

    def mark_dangerous(self) -> None:
        self.phase = TaskPhase.WAIT_ACTION_CONFIRM
        self._touch()

    def complete(self) -> None:
        self.phase = TaskPhase.COMPLETED
        self._touch()

    def set_step(self, name: str, status: str) -> None:
        self.step_status[name] = status
        self._touch()

    def _touch(self) -> None:
        self.updated_at = time.time()

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_key": self.session_key,
            "phase": self.phase.value,
            "title": self.title,
            "goal": self.goal,
            "steps": self.steps,
            "permissions": self.permissions,
            "step_status": self.step_status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
