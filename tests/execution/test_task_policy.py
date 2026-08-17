"""TaskPolicy/ActionPolicy 规则测试（#646-v2 GPT 拍板）。"""
from miqi.execution.task_policy import (
    TaskIntentRisk,
    describe_tool,
    permissions_for_tools,
    plan_card_steps,
    should_confirm_action,
    should_plan_confirm,
    task_risk_score,
    tool_risk,
)


def test_risk_levels():
    assert tool_risk("web_search") == TaskIntentRisk.READ_ONLY
    assert tool_risk("write_file") == TaskIntentRisk.MODIFY_LOCAL
    assert tool_risk("exec") == TaskIntentRisk.EXECUTE
    assert tool_risk("upload") == TaskIntentRisk.EXTERNAL_EFFECT
    assert task_risk_score(["web_search", "upload"]) == TaskIntentRisk.EXTERNAL_EFFECT


def test_plan_confirm_rules():
    # GPT 任务表：聊天/搜索/读论文不弹
    assert should_plan_confirm(["web_search", "web_fetch"]) is False
    assert should_plan_confirm(["read_file", "paper_get"]) is False
    # 生成文件/改代码/执行/上传弹
    assert should_plan_confirm(["write_file"]) is True
    assert should_plan_confirm(["exec"]) is True
    assert should_plan_confirm(["upload"]) is True
    # 复杂度（多来源总结 10 次搜索）
    assert should_plan_confirm(["web_search"] * 10) is True
    # auto 模式不弹（非阻塞展示）
    assert should_plan_confirm(["write_file"], mode="autonomous") is False


def test_action_policy():
    assert should_confirm_action("upload") is True
    assert should_confirm_action("delete_file") is True
    assert should_confirm_action("write_file") is False  # GPT：write_file → False


def test_user_language_steps():
    steps = plan_card_steps([("web_search", ""), ("write_file", ""), ("upload", "")])
    assert [s["name"] for s in steps] == ["搜索公开资料", "创建/写入文件", "上传到外部平台"]
    assert describe_tool("web_fetch") == "读取网页内容"


def test_permissions():
    perms = permissions_for_tools(["web_search", "write_file", "upload"])
    assert "network_read" in perms
    assert "workspace_write" in perms
    assert "external_upload" in perms
