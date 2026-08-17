"""ask_user_plan_confirm — 任务计划确认工具（#646-v2，GPT 评审拍板）。

与 ask_user_confirm_card 的分工：
- ask_user_confirm_card   → 危险动作最后确认（上传/支付/删除/外发）
- ask_user_plan_confirm   → **任务开始前一次**的计划确认（Plan Card）

Plan Card 触发（Agent 判断，非工具级）：
- 多工具调用 / Skill 执行 / 外部副作用组合 / 预计超过 30 秒

payload（schema）：
    title       任务标题（用户可理解，非工具名）
    goal        目标描述
    steps       [{name, tools[]}] 执行计划步骤
    permissions [network_read | workspace_write | external_upload | exec]
    timeout_seconds（可选）
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

DEFAULT_TIMEOUT_SECONDS = 180

ASK_PLAN_CONFIRM_INSTRUCTION = (
    "执行**多步骤任务**前（预计多个工具调用、执行 Skill、涉及外部副作用、"
    "或超过 30 秒），必须先调用 ask_user_plan_confirm 工具展示任务计划卡，"
    "等待用户确认后再开始执行。计划卡展示：任务标题、目标、执行步骤、所需权限。\n"
    "规则：\n"
    "1. 单个工具调用**不要**调用本工具（直接执行）；\n"
    "2. 上传/支付/删除等危险动作执行前系统会单独弹确认卡，无需在本计划中重复确认；\n"
    "3. 用户拒绝计划（status=cancelled）时停止任务并说明；choice_id=modify 时"
    "重新规划并再次调用。"
)


class AskUserPlanConfirmTool:
    """Tool for the model to present a task plan and await user approval."""

    def __init__(
        self,
        resolver: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    ):
        self._resolver = resolver

    @property
    def name(self) -> str:
        return "ask_user_plan_confirm"

    @property
    def description(self) -> str:
        return (
            "在开始多步骤任务前展示任务计划卡（标题/目标/步骤/所需权限），"
            "等待用户确认。用户确认后开始执行；拒绝则停止。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "title": {
                    "type": "string",
                    "description": "任务标题（用户可理解的描述，非工具名）",
                },
                "goal": {
                    "type": "string",
                    "description": "目标描述：本次任务要完成什么",
                },
                "steps": {
                    "type": "array",
                    "description": "执行计划步骤（3-8 步）",
                    "items": {
                        "type": "object",
                        "properties": {
                            "name": {"type": "string", "description": "步骤名（用户可理解）"},
                            "tools": {
                                "type": "array",
                                "items": {"type": "string"},
                                "description": "该步骤预计使用的工具",
                            },
                        },
                        "required": ["name"],
                    },
                },
                "permissions": {
                    "type": "array",
                    "description": "所需权限清单：network_read / workspace_write / external_upload / exec",
                    "items": {"type": "string"},
                },
                "timeout_seconds": {
                    "type": "integer",
                    "description": "（可选）等待秒数，默认 180",
                    "minimum": 5,
                    "maximum": 600,
                    "default": DEFAULT_TIMEOUT_SECONDS,
                },
            },
            "required": ["title", "goal", "steps"],
        }

    def normalize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        steps = []
        for i, s in enumerate(args.get("steps") or []):
            if not isinstance(s, dict):
                continue
            steps.append({
                "name": str(s.get("name", f"步骤 {i + 1}")),
                "tools": [str(t) for t in (s.get("tools") or []) if isinstance(t, str)],
            })
        perms = [str(p) for p in (args.get("permissions") or []) if isinstance(p, str)]
        try:
            timeout_raw = int(args.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))
        except (TypeError, ValueError):
            timeout_raw = DEFAULT_TIMEOUT_SECONDS
        return {
            "title": str(args.get("title", "任务计划")),
            "goal": str(args.get("goal", "")),
            "steps": steps,
            "permissions": perms,
            "timeout_seconds": max(5, min(600, timeout_raw)),
        }

    @staticmethod
    def build_result(gate_result: dict[str, Any]) -> str:
        status = gate_result.get("status", "cancelled")
        answers = gate_result.get("answers") or {}
        choice_id = answers.get("choice_id") or "cancel"
        if status == "submitted" and choice_id == "confirm":
            return json.dumps({
                "status": "confirmed",
                "plan_confirmed": True,
                "choice_id": "confirm",
                "remembered": gate_result.get("remembered", False),
            }, ensure_ascii=False)
        return json.dumps({
            "status": "cancelled",
            "plan_confirmed": False,
            "choice_id": choice_id,
            "reason": "用户未确认任务计划",
        }, ensure_ascii=False)

    async def execute(self, **kwargs: Any) -> str:
        if self._resolver is not None:
            try:
                payload = self.normalize_args(kwargs)
                gate_result = await self._resolver(payload)
                return self.build_result(gate_result)
            except Exception as exc:  # noqa: BLE001
                return f"Error: ask_user_plan_confirm failed: {exc}"
        return (
            "Error: ask_user_plan_confirm 需要桌面端用户输入通道，当前环境未接线。"
            "请先向用户展示计划并等待聊天内确认。"
        )
