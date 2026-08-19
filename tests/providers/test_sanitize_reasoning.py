"""测试 OpenAIProvider._sanitize_messages 的 reasoning_content 补位逻辑。

背景：DeepSeek thinking 模式要求 assistant 消息（含工具调用轮）必须携带
reasoning_content 键——缺键或 null 会 400（"must be passed back"），空字符串
可接受（实测 2026-08-18）。模型某些轮次不输出 reasoning 时，turn_runner 组装
的消息会缺该键，导致工具调用后下一轮请求失败。
"""

from __future__ import annotations

from miqi.providers.openai_provider import OpenAIProvider


def make_provider() -> OpenAIProvider:
    return OpenAIProvider(api_key="test-key", default_model="deepseek-v4-flash", provider_name="deepseek")


def test_keep_reasoning_fills_empty_for_tool_call_assistant():
    """keep_reasoning=True：assistant 工具调用消息缺 reasoning_content → 补空串。"""
    provider = make_provider()
    messages = [
        {"role": "user", "content": "渲染图"},
        {
            "role": "assistant",
            "content": None,
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "graph_render", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": '{"ok": true}'},
    ]
    out = provider._sanitize_messages(messages, keep_reasoning=True)
    asst = out[1]
    assert asst["reasoning_content"] == ""
    assert asst["tool_calls"]  # tool_calls 保留
    # tool 消息不受影响
    assert "reasoning_content" not in out[2]


def test_keep_reasoning_preserves_existing_reasoning():
    """已有 reasoning_content 的 assistant 消息保留原值。"""
    provider = make_provider()
    messages = [
        {
            "role": "assistant",
            "content": "先用工具",
            "reasoning_content": "思考中……",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "exec", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    out = provider._sanitize_messages(messages, keep_reasoning=True)
    assert out[0]["reasoning_content"] == "思考中……"


def test_keep_reasoning_fills_plain_assistant():
    """keep_reasoning=True：纯文本 assistant 消息缺键也补空串（API 同样要求）。"""
    provider = make_provider()
    out = provider._sanitize_messages(
        [{"role": "assistant", "content": "你好"}],
        keep_reasoning=True,
    )
    assert out[0]["reasoning_content"] == ""


def test_keep_reasoning_false_strips_reasoning():
    """keep_reasoning=False：reasoning_content 被剥离，且不补键。"""
    provider = make_provider()
    messages = [
        {
            "role": "assistant",
            "content": None,
            "reasoning_content": "不该出现",
            "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "exec", "arguments": "{}"}}],
        },
        {"role": "tool", "tool_call_id": "c1", "content": "ok"},
    ]
    out = provider._sanitize_messages(messages, keep_reasoning=False)
    assert "reasoning_content" not in out[0]
    assert out[0]["content"] is None  # 原有 content=None 补位保留
    assert out[0]["tool_calls"]


def test_user_and_tool_messages_untouched():
    """user / tool 消息不受补位逻辑影响。"""
    provider = make_provider()
    messages = [
        {"role": "user", "content": "你好"},
        {"role": "tool", "tool_call_id": "c1", "content": "结果"},
    ]
    out = provider._sanitize_messages(messages, keep_reasoning=True)
    assert all("reasoning_content" not in m for m in out)
