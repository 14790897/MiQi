"""TaskPolicy / ActionPolicy — #646-v2 双策略（GPT 第三轮评审拍板）。

替代单一 collab_policy.evaluate：
- TaskPolicy  ：任务级「要不要弹计划卡」（harness 任务边界）
- ActionPolicy：工具级「危险动作要不要最后确认」（Action Guard）

风险模型（TaskIntentRisk）：
    READ_ONLY = 0        搜索/读取——不弹
    MODIFY_LOCAL = 1     写本地文件——协作模式弹计划卡
    EXECUTE = 2          执行命令/脚本——弹
    EXTERNAL_EFFECT = 3  上传/支付/删除/外发——永远弹（计划卡 + Action Card）

复杂度（complexity_score）= 预估步骤 + 预计时长 + Skill 使用——
harness 首轮按 tool_calls 序列估算。

计划卡展示：工具 → 用户语言（TOOL_DESCRIPTION），不让模型写计划
（模型可能「说只查询实际上传」——来源只信 harness 工具序列）。
"""

from __future__ import annotations

from enum import IntEnum


class TaskIntentRisk(IntEnum):
    READ_ONLY = 0
    MODIFY_LOCAL = 1
    EXECUTE = 2
    EXTERNAL_EFFECT = 3


# 工具 → 风险等级（单一事实来源，与工具注册表同步维护）
TOOL_RISK: dict[str, TaskIntentRisk] = {
    # READ_ONLY
    "web_search": TaskIntentRisk.READ_ONLY,
    "web_fetch": TaskIntentRisk.READ_ONLY,
    "paper_search": TaskIntentRisk.READ_ONLY,
    "paper_get": TaskIntentRisk.READ_ONLY,
    "read_file": TaskIntentRisk.READ_ONLY,
    "list_dir": TaskIntentRisk.READ_ONLY,
    "search_files": TaskIntentRisk.READ_ONLY,
    "grep": TaskIntentRisk.READ_ONLY,
    "memory_search": TaskIntentRisk.READ_ONLY,
    "session_search": TaskIntentRisk.READ_ONLY,
    # MODIFY_LOCAL
    "write_file": TaskIntentRisk.MODIFY_LOCAL,
    "edit_file": TaskIntentRisk.MODIFY_LOCAL,
    "apply_patch": TaskIntentRisk.MODIFY_LOCAL,
    "create_doc": TaskIntentRisk.MODIFY_LOCAL,
    "append_file": TaskIntentRisk.MODIFY_LOCAL,
    # EXECUTE
    "exec": TaskIntentRisk.EXECUTE,
    "run_script": TaskIntentRisk.EXECUTE,
    "python": TaskIntentRisk.EXECUTE,
    # EXTERNAL_EFFECT
    "upload": TaskIntentRisk.EXTERNAL_EFFECT,
    "upload_run": TaskIntentRisk.EXTERNAL_EFFECT,
    "qraft_upload": TaskIntentRisk.EXTERNAL_EFFECT,
    "delete_file": TaskIntentRisk.EXTERNAL_EFFECT,
    "delete_dir": TaskIntentRisk.EXTERNAL_EFFECT,
    "payment": TaskIntentRisk.EXTERNAL_EFFECT,
    "send_message": TaskIntentRisk.EXTERNAL_EFFECT,
    "spawn": TaskIntentRisk.EXTERNAL_EFFECT,
}


def tool_risk(tool_name: str) -> TaskIntentRisk:
    return TOOL_RISK.get(tool_name, TaskIntentRisk.READ_ONLY)


# 工具 → 用户语言（PlanCard 展示，GPT：用户不懂 web_fetch/write_file）
TOOL_DESCRIPTION: dict[str, str] = {
    "web_search": "搜索公开资料",
    "web_fetch": "读取网页内容",
    "paper_search": "搜索学术论文",
    "paper_get": "读取论文内容",
    "read_file": "读取文件",
    "list_dir": "查看目录",
    "search_files": "查找文件",
    "grep": "搜索文件内容",
    "memory_search": "检索记忆",
    "session_search": "检索历史会话",
    "write_file": "创建/写入文件",
    "edit_file": "修改文件",
    "apply_patch": "应用补丁修改",
    "create_doc": "生成文档",
    "append_file": "追加写入文件",
    "exec": "运行命令/脚本",
    "run_script": "运行脚本",
    "python": "执行 Python",
    "upload": "上传到外部平台",
    "upload_run": "上传运行结果",
    "qraft_upload": "上传到 Qraft",
    "delete_file": "删除文件",
    "delete_dir": "删除目录",
    "payment": "支付/产生费用",
    "send_message": "发送外部消息",
    "spawn": "启动外部进程",
}


def describe_tool(tool_name: str) -> str:
    """工具 → 用户可懂短语（未收录时回退工具名）。"""
    return TOOL_DESCRIPTION.get(tool_name, tool_name)


# ── ActionPolicy：危险动作最后确认（Action Card）──────────────
def should_confirm_action(tool_name: str) -> bool:
    """是否需要在执行前弹危险动作确认卡（上传/删除/支付/外发）。

    协作/手动模式调用方自行决定（Mode 在调用侧判定）；
    此函数只回答「该工具是否属于危险动作类」。
    """
    return tool_risk(tool_name) >= TaskIntentRisk.EXTERNAL_EFFECT


# ── TaskPolicy：任务级「要不要弹计划卡」──────────────────────
def task_risk_score(tool_calls: list[str]) -> TaskIntentRisk:
    """任务风险 = 工具序列中的最高风险等级（GPT：sum 也行，取 max 更稳）。"""
    if not tool_calls:
        return TaskIntentRisk.READ_ONLY
    return max(tool_risk(t) for t in tool_calls)


def complexity_score(
    n_tool_calls: int,
    *,
    uses_skill: bool = False,
    expected_minutes: float = 0.0,
) -> float:
    """复杂度 = 预估步骤 + 时长 + Skill（GPT：estimated_steps + duration + skill）。"""
    return float(n_tool_calls) + (3.0 if uses_skill else 0.0) + expected_minutes / 5.0


COMPLEXITY_THRESHOLD = 4.0


def should_plan_confirm(
    tool_calls: list[str],
    *,
    mode: str = "collaboration",
    uses_skill: bool = False,
    expected_minutes: float = 0.0,
) -> bool:
    """协作（允许编辑）模式任务级判定——是否弹计划卡。

    GPT 拍板规则：
      - 简单任务（聊天/搜索/读论文）不弹
      - risk >= MODIFY_LOCAL（生成文件/改代码/执行/上传/Skill）→ 弹
      - 复杂度 > threshold（多来源总结等）→ 弹
      - 自动模式 → 不弹（非阻塞展示由调用方处理）
    """
    if mode == "autonomous":
        return False
    if task_risk_score(tool_calls) >= TaskIntentRisk.MODIFY_LOCAL:
        return True
    return complexity_score(
        len(tool_calls), uses_skill=uses_skill, expected_minutes=expected_minutes
    ) > COMPLEXITY_THRESHOLD


def plan_card_steps(tool_calls: list[tuple[str, str]]) -> list[dict[str, str]]:
    """工具序列 → 计划卡步骤（用户语言）。

    来源只信 harness 工具序列（模型可能说谎）——GPT 拍板：
    优先 tool metadata，不让模型写计划。
    """
    seen: set[str] = set()
    steps: list[dict[str, str]] = []
    for name, _arg_hint in tool_calls:
        label = describe_tool(name)
        if label in seen:
            continue
        seen.add(label)
        steps.append({"name": label, "tools": [name]})
    return steps


def permissions_for_tools(tool_calls: list[str]) -> list[str]:
    """工具序列 → 权限清单（PlanCard 需要权限）。"""
    perms: list[str] = []
    for t in tool_calls:
        risk = tool_risk(t)
        if risk >= TaskIntentRisk.EXTERNAL_EFFECT and "external_upload" not in perms:
            perms.append("external_upload")
        elif risk == TaskIntentRisk.EXECUTE and "exec" not in perms:
            perms.append("exec")
        elif risk == TaskIntentRisk.MODIFY_LOCAL and "workspace_write" not in perms:
            perms.append("workspace_write")
        elif risk == TaskIntentRisk.READ_ONLY and "network_read" not in perms and t.startswith(("web_", "paper_")):
            perms.append("network_read")
    return perms
