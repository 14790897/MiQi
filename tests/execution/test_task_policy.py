"""TaskPolicy/ActionPolicy 规则测试（#646-v2 GPT 第五轮拍板）。"""
from miqi.execution.task_policy import (
    action_risk_score,
    complexity_score,
    describe_tool,
    permissions_for_tools,
    plan_card_steps,
    should_confirm_action,
    should_plan_confirm,
    tool_risk,
)


# ── Action Risk（GPT 数值表）──────────────────────────────
def test_action_risk_values():
    assert tool_risk("read_file") == 0
    assert tool_risk("write_file") == 2
    assert tool_risk("exec") == 5
    assert tool_risk("upload") == 10
    assert action_risk_score(["web_search", "upload"]) == 10


def test_should_confirm_action():
    assert should_confirm_action("upload") is True
    assert should_confirm_action("payment") is True
    assert should_confirm_action("write_file") is False
    assert should_confirm_action("exec") is False  # 5 < 10——exec 由 Approval 层管，非 ActionCard
    # delete 分级：临时文件删除放行
    assert should_confirm_action("delete_file", {"path": "/tmp/tmp123.txt"}) is False
    # 破坏性删除确认
    assert should_confirm_action("delete_file", {"path": "/workspace/report.docx"}) is False  # 单文件
    assert should_confirm_action("delete_dir", {"path": "/workspace"}) is True
    assert should_confirm_action("delete_file", {"path": "*.txt"}) is True
    assert should_confirm_action("delete_file", {"path": "/tmp/x", "recursive": True}) is True


# ── Complexity（GPT 第五轮公式：只看规模，不看工具名）─────────
def test_complexity_score():
    assert complexity_score(n_tool_calls=1) == 0
    assert complexity_score(n_tool_calls=3) == 1
    assert complexity_score(n_tool_calls=1, uses_skill=True) == 3
    assert complexity_score(n_tool_calls=1, produces_artifact=True) == 2
    assert complexity_score(n_tool_calls=3, produces_artifact=True) == 3
    assert complexity_score(n_tool_calls=3, uses_skill=True, produces_artifact=True) == 6


def test_plan_confirm_rules():
    # 搜索一篇论文：1 工具 → 不弹
    assert should_plan_confirm(["web_search"]) is False
    # 查询 20 篇论文标题：10 个搜索但纯读 → 不弹（GPT 第五轮：工具数量≠复杂度，
    # 用户不需要确认纯读查询）
    assert should_plan_confirm(["web_search"] * 10) is False
    # 20 篇总结（多阶段推理 + 有产物）→ 弹
    assert (
        should_plan_confirm(
            ["web_search"] * 10, multi_stage_reasoning=True, produces_artifact=True
        )
        is True
    )
    assert should_plan_confirm(["web_search", "write_file"]) is False  # 2 工具小任务不弹（Edit 文件自动放行一致性）
    # 大报告任务（多工具+产物+多阶段）弹
    assert (
        should_plan_confirm(
            ["web_search"] * 3 + ["write_file"],
            multi_stage_reasoning=True,
            produces_artifact=True,
        )
        is True
    )  # 1+2+2=5
    # Skill 执行 → 弹（Skill 通常伴随多工具：3 工具+skill = 1+3=4）
    assert should_plan_confirm(["web_search"] * 3, uses_skill=True) is True
    # Auto/Plan 模式不阻塞（展示型）
    assert should_plan_confirm(["write_file"], mode="auto") is False
    assert should_plan_confirm(["upload"], mode="plan") is False


# ── 用户语言（GPT：绝对不要工具名）────────────────────────
def test_user_language_steps():
    steps = plan_card_steps([("web_search", ""), ("write_file", ""), ("upload", "")])
    assert [s["name"] for s in steps] == ["搜集资料", "创建文档", "上传结果到外部平台"]
    assert describe_tool("web_fetch") == "读取网页内容"
    assert describe_tool("write_file") == "创建文档"


def test_permissions():
    perms = permissions_for_tools(["web_search", "write_file", "upload"])
    assert "network_read" in perms
    assert "workspace_write" in perms
    assert "external_upload" in perms
