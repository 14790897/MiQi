"""request_action_confirmation — 危险动作最后确认工具（#646-v2，GPT 第五轮拍板）。

与 ask_user_confirm_card 的关系：**语义独立**——本工具是 Action Guard 专用：
上传/支付/破坏性删除/外发数据执行前**最后一道确认**（永远阻塞，所有模式）。
ask_user_confirm_card 保留为兼容层（内部路由到 ActionCard UI）。

payload（schema）：
    action      动作类型：upload / payment / delete / external
    target      目标（如 Qraft / 外部平台）
    file_name   文件（upload 时）
    size_bytes  大小
    sha256      文件指纹（防 TOCTOU——确认 A 上传 B）
"""

from __future__ import annotations

import json
from typing import Any, Awaitable, Callable

from miqi.agent.tools.base import Tool

DEFAULT_TIMEOUT_SECONDS = 120

REQUEST_ACTION_CONFIRM_INSTRUCTION = (
    "执行**危险动作**前（向外部平台上传、支付/产生费用、破坏性删除、外发数据），"
    "必须调用 request_action_confirmation 工具弹确认卡，等待用户确认。\n"
    "规则：\n"
    "1. 单次删除临时文件/普通写文件**不要**调用本工具；\n"
    "2. 多步骤任务开始前的计划确认使用 ask_user_plan_confirm（本工具只管危险动作）；\n"
    "3. 用户取消（status=cancelled）时停止该动作并说明。"
)


class RequestActionConfirmationTool(Tool):
    """Tool for the model to request final confirmation for a dangerous action."""

    def __init__(
        self,
        resolver: Callable[[dict[str, Any]], Awaitable[dict[str, Any]]] | None = None,
    ):
        self._resolver = resolver

    @property
    def name(self) -> str:
        return "request_action_confirmation"

    @property
    def description(self) -> str:
        return (
            "危险动作执行前的最后确认：向外部平台上传、支付、破坏性删除、外发数据。"
            "展示动作目标/文件/指纹，等待用户[确认上传]/[取消]。"
            "（多步骤任务计划确认用 ask_user_plan_confirm，两者不混用）"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["upload", "payment", "delete", "external"],
                    "description": "动作类型",
                },
                "target": {"type": "string", "description": "目标（如 Qraft / 外部平台 / 文件系统）"},
                "file_name": {"type": "string", "description": "（upload/delete 时）文件名"},
                "size_bytes": {"type": "integer", "description": "（upload 时）文件大小字节"},
                "sha256": {"type": "string", "description": "（upload 时）文件指纹——确认绑定，防确认 A 上传 B"},
                "description": {"type": "string", "description": "动作描述（用户可理解）"},
                "timeout_seconds": {"type": "integer", "default": DEFAULT_TIMEOUT_SECONDS, "minimum": 5, "maximum": 600},
            },
            "required": ["action", "target"],
        }

    def normalize_args(self, args: dict[str, Any]) -> dict[str, Any]:
        return {
            "action": str(args.get("action", "external")),
            "target": str(args.get("target", "")),
            "file_name": str(args.get("file_name") or ""),
            "size_bytes": args.get("size_bytes"),
            "sha256": str(args.get("sha256") or ""),
            "description": str(args.get("description") or ""),
            "timeout_seconds": self._safe_timeout(args),
        }

    @staticmethod
    def _safe_timeout(args: dict[str, Any]) -> int:
        """CodeRabbit: timeout_seconds 防御（模型发 'soon'/null 不炸）。"""
        try:
            return max(5, min(600, int(args.get("timeout_seconds", DEFAULT_TIMEOUT_SECONDS))))
        except (TypeError, ValueError):
            return DEFAULT_TIMEOUT_SECONDS

    @staticmethod
    def build_result(gate_result: dict[str, Any]) -> str:
        status = gate_result.get("status", "cancelled")
        answers = gate_result.get("answers") or {}
        choice_id = answers.get("choice_id") or "cancel"
        if status == "submitted" and choice_id == "confirm":
            return json.dumps({
                "status": "confirmed",
                "action_confirmed": True,
                "choice_id": "confirm",
                "remembered": gate_result.get("remembered", False),
            }, ensure_ascii=False)
        return json.dumps({
            "status": "cancelled",
            "action_confirmed": False,
            "choice_id": choice_id,
            "reason": "用户未确认危险动作",
        }, ensure_ascii=False)

    async def execute(self, **kwargs: Any) -> str:
        if self._resolver is not None:
            try:
                payload = self.normalize_args(kwargs)
                gate_result = await self._resolver(payload)
                return self.build_result(gate_result)
            except Exception as exc:  # noqa: BLE001
                return f"错误：request_action_confirmation 执行失败：{exc}"
        return (
            "错误：request_action_confirmation 需要桌面端用户输入通道，当前环境未接线。"
            "请先向用户说明危险动作并等待确认。"
        )
