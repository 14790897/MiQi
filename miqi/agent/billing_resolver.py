"""Slurm MCP 作业计费桥（issue #927）。

计费触发点（2026-09-04 产品确认）：**slurm 作业状态变为 RUNNING 时**由
Desktop 发起扣费（10 分/次，memo 携带作业信息）。Python 侧在
submit_slurm_job / check_job_status 的返回中发现 state=RUNNING 时，
经会话发射器向 Desktop 发一次 fire-and-forget 扣费事件；作业已在运行，
不阻止调用——余额不足等扣费失败由 Desktop 记录并提示。

接线（与 user_input_resolver 同模式）：
  bridge/loop.py（chat.send drain）：
      set_billing_charge_emitter(session_key, emit_fn)
      （emit_fn 把事件转发为 "slurm_job_running" 桥事件）
"""

from __future__ import annotations

from typing import Any, Callable

# slurm MCP 服务器识别：服务器名包含该关键字（不区分大小写）即启用计费。
SLURM_SERVER_KEYWORD = "slurm"

# 每会话一个发射器槽位（session_key → emit 回调）。进程级单槽会串会话
#（user_input_resolver 教训，CodeRabbit #711）。
_emitters: dict[str, Callable[[dict[str, Any]], Any]] = {}

# 每会话已报告过的作业 ID（check_job_status 轮询会反复观察 RUNNING，
# 同一作业只发一次计费事件；Desktop 侧仍有 charge_id/job_id 去重兜底）。
_seen_job_ids: dict[str, set[str]] = {}
# 每会话去重集合上限（防长会话无界增长；超限清空重建，最坏退化为
# 重复事件，由 Desktop 去重兜底）。
_MAX_SEEN_JOB_IDS_PER_SESSION = 500


def mark_job_reported(session_key: str, job_id: str) -> bool:
    """标记某会话已对 job_id 发过计费事件；返回 True 表示首次（应发送）。"""
    if not session_key or not job_id:
        return True
    seen = _seen_job_ids.get(session_key)
    if seen is None:
        seen = set()
        _seen_job_ids[session_key] = seen
    if job_id in seen:
        return False
    if len(seen) >= _MAX_SEEN_JOB_IDS_PER_SESSION:
        seen.clear()
    seen.add(job_id)
    return True


def set_billing_charge_emitter(
    session_key: str, emitter: Callable[[dict[str, Any]], Any] | None
) -> None:
    """注册（或清除）某会话的扣费请求发射器。

    由 bridge 的 chat.send drain 按 session_key 注册；无发射器
    （headless/CLI）时 slurm 计费事件无处可发，静默跳过（作业照常运行，
    Desktop 登录后同一作业不会补扣）。
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
