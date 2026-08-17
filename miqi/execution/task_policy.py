"""TaskPolicy / ActionPolicy — #646-v2 最终版（GPT 第五轮拍板，2026-08-17）。

两个分数**完全分离**（GPT：工具数量≠复杂度，复杂度和风险必须拆开）：

1. complexity_score —— 决定是否弹 PlanCard（任务规模）
    complexity = 0
    if tool_calls >= 3:          +1   任务规模（≥3 工具）
    if uses_skill:               +3   Skill 执行
    if estimated_duration>5min:  +2   预计时长
    if produces_artifact:        +2   产生文件产物
    if multi_stage_reasoning:    +2   多阶段推理（跨多轮规划）
    >= COMPLEXITY_THRESHOLD(4) → Plan Card

2. action_risk_score —— 决定是否弹 ActionCard（危险动作，永远阻塞）
    upload:    10
    delete:    10（分级：临时文件删除由模式放行，破坏性删除确认）
    payment:   10
    exec:       5
    write:      2
    read:       0

Mode 语义（最终）：
    Plan      ：PlanCard 展示（非阻塞）、ActionCard 禁止
    Manual    ：PlanCard 确认、ActionCard 确认
    Edit(默认)：PlanCard 确认、ActionCard 确认——不看到文件/shell/web 审批
    Auto      ：TaskTimeline 展示（非阻塞）、ActionCard 确认（危险分级）
"""

from __future__ import annotations

from enum import IntEnum


class TaskIntentRisk(IntEnum):
    """工具风险等级（Action Risk 用，GPT 第五轮数值表）。"""

    READ_ONLY = 0
    MODIFY_LOCAL = 2      # write
    EXECUTE = 5           # exec
    EXTERNAL_EFFECT = 10  # upload / payment / destructive delete


# 工具 → 风险值（Action Guard 依据）
TOOL_RISK: dict[str, int] = {
    # read = 0
    "web_search": 0,
    "web_fetch": 0,
    "paper_search": 0,
    "paper_get": 0,
    "read_file": 0,
    "list_dir": 0,
    "search_files": 0,
    "grep": 0,
    "memory_search": 0,
    "session_search": 0,
    # write = 2
    "write_file": 2,
    "edit_file": 2,
    "apply_patch": 2,
    "create_doc": 2,
    "append_file": 2,
    # exec = 5
    "exec": 5,
    "run_script": 5,
    "python": 5,
    # external = 10
    "upload": 10,
    "upload_run": 10,
    "qraft_upload": 10,
    "delete_file": 10,
    "delete_dir": 10,
    "payment": 10,
    "send_message": 10,
    "spawn": 10,
}


def tool_risk(tool_name: str) -> int:
    return TOOL_RISK.get(tool_name, 0)


# 工具 → 用户语言（PlanCard 展示行为短语——GPT：绝对不要工具名）
TOOL_DESCRIPTION: dict[str, str] = {
    "web_search": "搜集资料",
    "web_fetch": "读取网页内容",
    "paper_search": "搜集论文",
    "paper_get": "阅读论文",
    "read_file": "读取文件",
    "list_dir": "查看目录",
    "search_files": "查找文件",
    "grep": "搜索文件内容",
    "memory_search": "检索记忆",
    "session_search": "检索历史会话",
    "write_file": "创建文档",
    "edit_file": "修改文件",
    "apply_patch": "修改代码",
    "create_doc": "生成文档",
    "append_file": "追加写入",
    "exec": "运行命令",
    "run_script": "运行脚本",
    "python": "执行 Python",
    "upload": "上传结果到外部平台",
    "upload_run": "上传运行结果",
    "qraft_upload": "上传到 Qraft",
    "payment": "支付/产生费用",
    "send_message": "发送外部消息",
    "spawn": "启动外部进程",
}


def describe_tool(tool_name: str) -> str:
    return TOOL_DESCRIPTION.get(tool_name, tool_name)


# ── ActionPolicy：危险动作确认（ActionCard，永远阻塞）──────────
ACTION_CONFIRM_THRESHOLD = 10  # upload/delete-destructive/payment/外发


def action_risk_score(tool_names: list[str]) -> int:
    """危险动作风险分（GPT 数值表：upload 10 / delete 10 / exec 5 / write 2）。"""
    if not tool_names:
        return 0
    return max(tool_risk(t) for t in tool_names)


def should_confirm_action(tool_name: str, arguments: dict | None = None) -> bool:
    """危险动作最后确认判定（GPT 第五轮：delete 分级——临时删除放行、
    破坏性删除确认；其余风险 >= 10 确认）。"""
    risk = tool_risk(tool_name)
    if risk < ACTION_CONFIRM_THRESHOLD:
        return False
    if tool_name in ("delete_file", "delete_dir", "remove_file", "rm"):
        # 分级：删除刚刚生成的临时文件 → 模式放行；破坏性删除（目录/通配/工作区外）→ 确认
        return _is_destructive_delete(arguments or {})
    return True


def _is_destructive_delete(args: dict) -> bool:
    """破坏性删除判定：目录删除 / 通配符 / 递归 / 关键路径。"""
    path = str(args.get("path") or args.get("file_path") or "")
    if args.get("recursive") or args.get("rec"):
        return True
    if any(ch in path for ch in "*?["):
        return True
    if args.get("dir") or args.get("directory"):
        return True
    if path in ("/", "~", str(args.get("workspace", "")) or "", ".", ".."):
        return True
    if path.endswith(("/", "\\")):
        return True
    return False


# ── TaskPolicy：任务复杂度 → 是否弹 PlanCard（GPT 第五轮公式）──
COMPLEXITY_THRESHOLD = 4


def complexity_score(
    *,
    n_tool_calls: int,
    uses_skill: bool = False,
    estimated_duration_min: float = 0.0,
    produces_artifact: bool = False,
    multi_stage_reasoning: bool = False,
) -> int:
    """GPT 第五轮复杂度公式（只考虑任务规模，不看工具名）。"""
    score = 0
    if n_tool_calls >= 3:
        score += 1
    if uses_skill:
        score += 3
    if estimated_duration_min > 5:
        score += 2
    if produces_artifact:
        score += 2
    if multi_stage_reasoning:
        score += 2
    return score


def should_plan_confirm(
    tool_calls: list[str],
    *,
    mode: str = "edit",
    uses_skill: bool = False,
    estimated_duration_min: float = 0.0,
    produces_artifact: bool | None = None,
    multi_stage_reasoning: bool = False,
) -> bool:
    """PlanCard 触发判定。

    GPT 第五轮：
      - Plan/Auto 模式：不阻塞（展示由调用方处理）——这里返回 False（确认类）
      - Manual/Edit：complexity_score >= 4 → 确认
      - 复杂度只看规模（工具数量/时长/产物/Skill），不看工具名
    """
    if mode in ("plan", "auto"):
        return False  # 展示型（Timeline），不阻塞
    if produces_artifact is None:
        produces_artifact = any(
            tool_risk(t) >= 2 for t in tool_calls  # 含写/执行/外发 → 有产物倾向
        )
    return (
        complexity_score(
            n_tool_calls=len(tool_calls),
            uses_skill=uses_skill,
            estimated_duration_min=estimated_duration_min,
            produces_artifact=produces_artifact,
            multi_stage_reasoning=multi_stage_reasoning,
        )
        >= COMPLEXITY_THRESHOLD
    )


def plan_card_steps(tool_calls: list[tuple[str, str]]) -> list[dict[str, str]]:
    """工具序列 → PlanCard 步骤（行为短语，不显示工具名）。"""
    seen: set[str] = set()
    steps: list[dict[str, str]] = []
    for name, _arg_hint in tool_calls:
        if not name:
            continue
        label = describe_tool(str(name))
        if not label or label in seen:
            continue
        seen.add(label)
        steps.append({"name": label, "tools": [name]})
    return steps


def permissions_for_tools(tool_calls: list[str]) -> list[str]:
    """工具序列 → 权限清单（PlanCard「需要」——GPT：允许权限图标，不要工具名）。"""
    perms: list[str] = []
    for t in tool_calls:
        risk = tool_risk(t)
        if risk >= 10 and "external_upload" not in perms:
            perms.append("external_upload")
        elif risk == 5 and "exec" not in perms:
            perms.append("exec")
        elif risk == 2 and "workspace_write" not in perms:
            perms.append("workspace_write")
        elif risk == 0 and "network_read" not in perms and t.startswith(("web_", "paper_")):
            perms.append("network_read")
    return perms
