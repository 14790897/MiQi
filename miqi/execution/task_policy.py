"""TaskPolicy / ActionPolicy — #646-v2 冻结版（GPT 第二轮评审拍板，2026-08-18）。

两个分数**完全分离**（GPT：工具数量≠复杂度，复杂度和风险必须拆开）：

1. complexity_score —— 决定是否弹 PlanCard（任务规模 + 阶段）
    complexity = 0
    if 1~2 tools:          +0   工具数量阶梯（数量≠复杂度，只是弱信号）
    if 3~5 tools:          +1
    if >5 tools:           +2
    if len(unique(phases))>=2:  +2   阶段跨类型（READ→WRITE 跨轮累计，
                                     TaskContext.phase_history——GPT 第二轮）
    if produces_artifact:  +2   产生文件产物
    if uses_skill:         +3   Skill 执行
    >= COMPLEXITY_THRESHOLD(4) → Plan Card

    （GPT 第二轮：删除 estimated_duration_min——无 Planner 前是伪信号；
      删除 multi_stage_reasoning——用 phase_history 替代）

2. action_risk_score —— 决定是否弹 ActionCard（危险动作，永远阻塞）
    upload:    10
    delete:    10（分级：临时文件删除由模式放行，破坏性删除确认）
    payment:   10
    exec:       5
    write:      2
    read:       0

3. mutation gate（GPT 第二轮 P0-2）：PlanCard 确认前——
    READ_ONLY 工具允许执行；WRITE/EXEC/EXTERNAL 禁止（必须经过 PlanCard）。

Mode 语义（最终冻结表，GPT 第二轮）：
    Plan      ：PlanCard 展示（非阻塞）、Timeline 无、Action 禁止
    Manual    ：PlanCard 确认、Timeline 有、Action 确认
    Edit(默认)：PlanCard 确认、Timeline 有、Action 确认——不看到文件/shell/web 审批
    Auto      ：无阻塞 Timeline（always visible，complex 定详细度）、Action 确认
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
    "remove_file": 10,
    "rm": 10,
    "payment": 10,
    "send_message": 10,
    "spawn": 10,
}


def tool_risk(tool_name: str) -> int:
    # CodeRabbit Major：fail-closed——未注册工具保守非零（未知工具不当只读）
    return TOOL_RISK.get(tool_name, 1)


# ── 阶段分类（GPT 第二轮：READ/WRITE/EXEC/EXTERNAL，不要 THINK）──
PHASE_READ = "READ"
PHASE_WRITE = "WRITE"
PHASE_EXEC = "EXEC"
PHASE_EXTERNAL = "EXTERNAL"

TOOL_PHASE: dict[str, str] = {
    # READ
    "web_search": PHASE_READ,
    "web_fetch": PHASE_READ,
    "paper_search": PHASE_READ,
    "paper_get": PHASE_READ,
    "read_file": PHASE_READ,
    "list_dir": PHASE_READ,
    "search_files": PHASE_READ,
    "grep": PHASE_READ,
    "memory_search": PHASE_READ,
    "session_search": PHASE_READ,
    # WRITE
    "write_file": PHASE_WRITE,
    "edit_file": PHASE_WRITE,
    "apply_patch": PHASE_WRITE,
    "create_doc": PHASE_WRITE,
    "append_file": PHASE_WRITE,
    # EXEC
    "exec": PHASE_EXEC,
    "run_script": PHASE_EXEC,
    "python": PHASE_EXEC,
    # EXTERNAL
    "upload": PHASE_EXTERNAL,
    "upload_run": PHASE_EXTERNAL,
    "qraft_upload": PHASE_EXTERNAL,
    "delete_file": PHASE_EXTERNAL,
    "delete_dir": PHASE_EXTERNAL,
    "payment": PHASE_EXTERNAL,
    "send_message": PHASE_EXTERNAL,
    "spawn": PHASE_EXTERNAL,
}


def phase_for_tool(tool_name: str) -> str | None:
    """工具 → 阶段（未知工具返回 None——不计阶段，不弹阶段分）。"""
    return TOOL_PHASE.get(tool_name)


def is_mutation_tool(tool_name: str) -> bool:
    """mutation gate（GPT P0-2）：WRITE/EXEC/EXTERNAL → True（PlanCard 前禁止）。"""
    phase = phase_for_tool(tool_name)
    return phase in (PHASE_WRITE, PHASE_EXEC, PHASE_EXTERNAL)


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
        # 分级：删除刚刚生成的临时文件 → 模式放行；破坏性删除（目录/通配/递归/关键路径）→ 确认
        if tool_name == "delete_dir":
            return True  # 目录删除本身即破坏性
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


# ── TaskPolicy：任务复杂度 → 是否弹 PlanCard（GPT 第二轮冻结公式）──
COMPLEXITY_THRESHOLD = 4


def complexity_score(
    *,
    n_tool_calls: int,
    uses_skill: bool = False,
    produces_artifact: bool = False,
    phase_history: list[str] | None = None,
) -> int:
    """GPT 第二轮冻结公式：

    - 工具数量阶梯：1~2:+0 / 3~5:+1 / >5:+2（数量是弱信号，不是复杂度本身）
    - 阶段跨类型：len(unique(phase_history)) >= 2 → +2（READ→WRITE 任务升级）
    - 产生 artifact：+2
    - Skill：+3
    - 删除了 estimated_duration_min（无 Planner 前是伪信号）与
      multi_stage_reasoning（用 phase_history 替代）
    """
    score = 0
    if n_tool_calls >= 6:
        score += 2
    elif n_tool_calls >= 3:
        score += 1
    if phase_history:
        if len(set(p for p in phase_history if p)) >= 2:
            score += 2
    if produces_artifact:
        score += 2
    if uses_skill:
        score += 3
    return score


def should_plan_confirm(
    tool_calls: list[str],
    *,
    mode: str = "edit",
    uses_skill: bool = False,
    produces_artifact: bool | None = None,
    phase_history: list[str] | None = None,
) -> bool:
    """PlanCard 触发判定（GPT 第二轮冻结版）。

    - Plan/Auto 模式：不阻塞（展示由 Timeline 处理）——这里返回 False（确认类）
    - Manual/Edit：complexity_score >= 4 → 确认
    - 阶段历史跨轮累计（TaskContext.phase_history）——任务升级（READ→WRITE）弹
    """
    if mode in ("plan", "auto"):
        return False  # 展示型（Timeline），不阻塞
    if produces_artifact is None:
        produces_artifact = any(
            tool_risk(t) >= 2 for t in tool_calls  # 含写/执行/外发 → 有产物倾向
        )
    # 用户（2026-08-24）：plan 需常态出现——edit 模式任何执行类任务
    # （有产物倾向——写/执行/外发）都先弹计划卡确认；纯读（无产物）不弹
    # （直接回答）。复杂任务（>=阈值）同样弹。
    if produces_artifact:
        return True
    return (
        complexity_score(
            n_tool_calls=len(tool_calls),
            uses_skill=uses_skill,
            produces_artifact=produces_artifact,
            phase_history=phase_history,
        )
        >= COMPLEXITY_THRESHOLD
    )


def should_show_timeline(
    tool_calls: list[str],
    *,
    produces_artifact: bool | None = None,
    phase_history: list[str] | None = None,
) -> bool:
    """Auto 模式 Timeline 展示判定（GPT 第二轮 Q6：always visible 但分级）。

    复杂任务（复杂度 >= 4）→ 完整 Timeline（步骤列表 ✓⟳○）；
    简单任务（< 4）→ 不展示（靠工具行/文本流——"正在搜索…"由现有 UI 覆盖）。
    """
    if produces_artifact is None:
        produces_artifact = any(tool_risk(t) >= 2 for t in tool_calls)
    return (
        complexity_score(
            n_tool_calls=len(tool_calls),
            produces_artifact=produces_artifact,
            phase_history=phase_history,
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
