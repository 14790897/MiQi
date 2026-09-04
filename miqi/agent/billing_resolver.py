"""Slurm MCP 作业计费握手桥（issue #927）。

Desktop 主进程是扣费发起方（复用 /oauth2/points/deduct，memo 记录作业
信息），Python 侧在 slurm MCP 工具实际执行前发起一次「扣费请求-决议」
握手：工具等待 Desktop 扣费结果，余额不足/扣费失败时阻止 MCP 调用
（fail-closed），同一工具调用只发起一次请求。

接线（与 user_input_resolver 同模式）：
  bridge/loop.py（chat.send drain）：
      set_billing_charge_emitter(session_key, lambda payload:
          asyncio.create_task(_emit("slurm_job_charge_request", payload)))
      app_server.register_method("billing.slurmResolve", handler)
"""

from __future__ import annotations

import asyncio
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable

from loguru import logger

# 与 Desktop 侧协商的握手超时（秒）：扣费请求含平台网络重试，
# 决议必须在该时限内返回，否则按 fail-closed 阻止本次调用。
CHARGE_RESOLVE_TIMEOUT_S = 25.0

# slurm MCP 服务器识别：服务器名包含该关键字（不区分大小写）即启用计费。
SLURM_SERVER_KEYWORD = "slurm"

# 每会话一个发射器槽位（session_key → emit 回调）。进程级单槽会串会话
#（user_input_resolver 教训，CodeRabbit #711）。
_emitters: dict[str, Callable[[dict[str, Any]], Any]] = {}

# 待决议的扣费请求：charge_id → _ChargeRequest（含决议 Future）。
_pending: dict[str, "_ChargeRequest"] = {}


@dataclass
class _ChargeRequest:
    session_key: str
    future: asyncio.Future = field(
        default_factory=lambda: asyncio.get_event_loop().create_future()
    )


def set_billing_charge_emitter(
    session_key: str, emitter: Callable[[dict[str, Any]], Any] | None
) -> None:
    """注册（或清除）某会话的扣费请求发射器。

    由 bridge 的 chat.send drain 按 session_key 注册；无发射器
    （headless/CLI）时 slurm MCP 计费无法发起，工具按 fail-closed 阻止。
    """
    if emitter is None:
        _emitters.pop(session_key, None)
    else:
        _emitters[session_key] = emitter


def billing_charge_emitter_for(session_key: str) -> Callable[[dict[str, Any]], Any] | None:
    return _emitters.get(session_key)


def is_slurm_server(server_name: str) -> bool:
    """服务器名是否属于 slurm 计费范围（包含关键字，不区分大小写）。"""
    return SLURM_SERVER_KEYWORD in (server_name or "").lower()


async def request_charge(
    *,
    session_key: str,
    payload: dict[str, Any],
) -> dict[str, Any]:
    """发起一次扣费请求并等待 Desktop 决议。

    Returns:
        {"ok": true, "balance": int} 放行；{"ok": false, "code": str,
        "message": str} 阻止（余额不足/扣费失败/超时/通道不可用）。
    """
    emitter = _emitters.get(session_key)
    if emitter is None:
        return {
            "ok": False,
            "code": "NO_DESKTOP_CHANNEL",
            "message": (
                "Slurm MCP 计费通道不可用（需要 MiQroForge Desktop 登录后执行），"
                "本次作业未提交。"
            ),
        }

    charge_id = payload.get("charge_id") or uuid.uuid4().hex
    payload = {**payload, "charge_id": charge_id, "session_key": session_key}
    req = _ChargeRequest(session_key=session_key)
    _pending[charge_id] = req

    try:
        # 发射器为异步回调（drain 的 _emit）；若返回协程必须等待其执行，
        # 否则决议永远送不出去。失败时回收挂起项并阻止。
        try:
            result = emitter(payload)
            if asyncio.iscoroutine(result):
                await result
        except Exception as exc:
            logger.warning("billing: 扣费请求发射失败（{}）", exc)
            return {
                "ok": False,
                "code": "CHARGE_REQUEST_FAILED",
                "message": "计费请求发送失败，本次作业未提交。请稍后重试。",
            }
        try:
            return await asyncio.wait_for(req.future, timeout=CHARGE_RESOLVE_TIMEOUT_S)
        except asyncio.TimeoutError:
            logger.error("billing: 扣费决议超时（charge_id={}）", charge_id)
            return {
                "ok": False,
                "code": "CHARGE_TIMEOUT",
                "message": "计费确认超时，本次作业未提交。请稍后重试。",
            }
    finally:
        _pending.pop(charge_id, None)


def resolve_charge(charge_id: str, result: dict[str, Any]) -> bool:
    """Desktop 决议回传（bridge billing.slurmResolve handler 调用）。

    Returns True 当决议成功送达一个等待中的请求。
    """
    req = _pending.get(charge_id)
    if req is None:
        return False
    if not req.future.done():
        req.future.set_result(result)
    return True


def pending_session_for_charge(charge_id: str) -> str | None:
    """待决议扣费请求所属的会话 key（决议鉴权用）。"""
    req = _pending.get(charge_id)
    return req.session_key if req else None
