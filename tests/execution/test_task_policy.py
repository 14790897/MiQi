"""TaskPolicy 冻结版测试（GPT 第二轮评审拍板，2026-08-18）。

新公式：
- 工具数量阶梯：1~2:+0 / 3~5:+1 / >5:+2
- 阶段跨类型（phase_history unique >= 2）：+2
- 产生 artifact：+2
- Skill：+3
- 阈值 4（删除了 estimated_duration_min / multi_stage_reasoning）
"""

from miqi.execution.task_policy import (
    complexity_score,
    is_mutation_tool,
    phase_for_tool,
    should_confirm_action,
    should_plan_confirm,
    tool_risk,
)


def test_phase_classification():
    # READ
    assert phase_for_tool("web_search") == "READ"
    assert phase_for_tool("read_file") == "READ"
    # WRITE
    assert phase_for_tool("write_file") == "WRITE"
    # EXEC
    assert phase_for_tool("exec") == "EXEC"
    # EXTERNAL
    assert phase_for_tool("upload") == "EXTERNAL"
    assert phase_for_tool("payment") == "EXTERNAL"
    # 未知工具 → None（不计阶段）
    assert phase_for_tool("unknown_tool") is None


def test_mutation_gate():
    # READ 工具非 mutation（Plan 确认前允许执行）
    assert is_mutation_tool("web_search") is False
    assert is_mutation_tool("read_file") is False
    # WRITE/EXEC/EXTERNAL 是 mutation（Plan 确认前禁止）
    assert is_mutation_tool("write_file") is True
    assert is_mutation_tool("exec") is True
    assert is_mutation_tool("upload") is True
    assert is_mutation_tool("delete_dir") is True


def test_complexity_score_steps():
    # 工具数量阶梯：1~2:+0 / 3~5:+1 / >5:+2
    assert complexity_score(n_tool_calls=1) == 0
    assert complexity_score(n_tool_calls=2) == 0
    assert complexity_score(n_tool_calls=3) == 1
    assert complexity_score(n_tool_calls=5) == 1
    assert complexity_score(n_tool_calls=6) == 2
    # 阶段跨类型 +2（READ→WRITE 任务升级）
    assert complexity_score(n_tool_calls=3, phase_history=["READ", "READ", "WRITE"]) == 3
    # 单阶段不触发
    assert complexity_score(n_tool_calls=3, phase_history=["READ", "READ", "READ"]) == 1
    # artifact +2 / skill +3
    assert complexity_score(n_tool_calls=1, produces_artifact=True) == 2
    assert complexity_score(n_tool_calls=1, uses_skill=True) == 3
    assert complexity_score(n_tool_calls=3, uses_skill=True, produces_artifact=True) == 6


def test_plan_confirm_rules():
    # 纯读查询：10 个搜索 → 数量 +2、无阶段无 artifact = 2 < 4 → 不弹
    assert should_plan_confirm(["web_search"] * 10) is False
    # 单写文件：artifact 2 → 弹（用户：plan 常态——执行类任务都先确认计划）
    assert should_plan_confirm(["write_file"]) is True
    # 搜索+写文件：阶段跨类型 +2 + artifact +2 = 4 → 弹（任务升级）
    assert (
        should_plan_confirm(["web_search", "write_file"], phase_history=["READ", "WRITE"])
        is True
    )
    # 大报告任务：6 工具 + 阶段 + artifact = 6 → 弹
    assert (
        should_plan_confirm(
            ["web_search"] * 5 + ["write_file"],
            phase_history=["READ"] * 5 + ["WRITE"],
        )
        is True
    )
    # Skill 任务（3 工具 + skill = 4）→ 弹
    assert should_plan_confirm(["web_search"] * 3, uses_skill=True) is True
    # auto/plan 模式不阻塞
    assert should_plan_confirm(["web_search", "write_file"], mode="auto") is False
    assert should_plan_confirm(["web_search", "write_file"], mode="plan") is False


def test_action_confirm_rules():
    # 读/写不触发 ActionCard（由 PlanCard/审批层处理）
    assert should_confirm_action("write_file") is False
    # 上传/支付 → 确认
    assert should_confirm_action("upload") is True
    assert should_confirm_action("payment") is True
    # 删除分级：单文件删除（非破坏性）→ 放行
    assert should_confirm_action("delete_file", {"path": "tmp.txt"}) is False
    # 目录删除 → 确认
    assert should_confirm_action("delete_dir") is True
    # 通配/递归删除 → 确认
    assert should_confirm_action("delete_file", {"path": "logs/*.tmp"}) is True
    assert should_confirm_action("delete_file", {"path": "data", "recursive": True}) is True


def test_tool_risk_table():
    assert tool_risk("web_search") == 0
    assert tool_risk("write_file") == 2
    assert tool_risk("exec") == 5
    assert tool_risk("upload") == 10
