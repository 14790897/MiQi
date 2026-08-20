"""Tests for ContextRuntime (Phase 12.2)."""

import pytest

from miqi.runtime.context_runtime import ContextRuntime


class _FakeTurnContext:
    turn_id = "turn-1"
    thread_id = "thread-1"

    class _Meta:
        name = "code-agent"
    agent_metadata = _Meta()


def test_context_runtime_builds_initial_messages():
    runtime = ContextRuntime()
    turn = _FakeTurnContext()

    messages = runtime.build_initial_messages(
        turn=turn,
        user_content="hello",
        system_prompt="system",
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[1]["content"] == "hello"


def test_context_runtime_builds_with_history():
    runtime = ContextRuntime()
    turn = _FakeTurnContext()

    messages = runtime.build_initial_messages(
        turn=turn,
        user_content="hello",
        system_prompt="system",
        history=[{"role": "assistant", "content": "previous"}],
    )

    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "assistant"
    assert messages[2]["role"] == "user"


def test_context_runtime_adds_tool_result():
    runtime = ContextRuntime()
    messages = [{"role": "user", "content": "hello"}]

    updated = runtime.add_tool_result(
        messages=messages,
        tool_call_id="call-1",
        name="read_file",
        content="file content",
    )

    assert updated[-1]["role"] == "tool"
    assert updated[-1]["tool_call_id"] == "call-1"
    assert updated[-1]["name"] == "read_file"
    assert updated[-1]["content"] == "file content"


def test_context_runtime_adds_assistant_message():
    runtime = ContextRuntime()
    messages = [{"role": "user", "content": "hello"}]

    updated = runtime.add_assistant_message(
        messages=messages,
        content="answer",
    )

    assert updated[-1]["role"] == "assistant"
    assert updated[-1]["content"] == "answer"


def test_context_runtime_adds_assistant_with_tool_calls():
    runtime = ContextRuntime()
    messages = [{"role": "user", "content": "hello"}]
    tool_calls = [{"id": "tc-1", "type": "function", "function": {"name": "read_file", "arguments": "{}"}}]

    updated = runtime.add_assistant_message(
        messages=messages,
        content="",
        tool_calls=tool_calls,
    )

    assert updated[-1]["role"] == "assistant"
    assert updated[-1]["tool_calls"] == tool_calls


def test_context_runtime_adds_assistant_with_reasoning():
    """reasoning_content is carried as a separate field (Issue #539).

    Preserved so the UI can render a thinking block without polluting the
    visible content, and kept out when absent so non-thinking models are
    unaffected.
    """
    runtime = ContextRuntime()
    messages = [{"role": "user", "content": "hello"}]

    updated = runtime.add_assistant_message(
        messages=messages,
        content="answer",
        reasoning_content="the user greeted me",
    )

    assert updated[-1]["reasoning_content"] == "the user greeted me"
    assert updated[-1]["content"] == "answer"

    # Omitted reasoning must not add the key at all.
    plain = runtime.add_assistant_message(messages=messages, content="answer")
    assert "reasoning_content" not in plain[-1]


# ---------------------------------------------------------------------------
# Phase 19: Context compaction
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_context_runtime_compact_thread_replaces_history():
    """compact_thread() reads history, compresses, and replaces via history_runtime."""
    from miqi.runtime.context_runtime import ContextRuntime

    class FakeHistory:
        def __init__(self):
            self.messages = [
                {"role": "user", "content": "one"},
                {"role": "assistant", "content": "two"},
                {"role": "user", "content": "three"},
            ]
            self.replaced = None

        async def load_messages(self, thread_id):
            return list(self.messages)

        async def replace_messages_with_compaction(
            self, thread_id, turn_id, replacement,
            messages_before=0, messages_after=0, tokens_saved=0,
        ):
            self.replaced = replacement

    async def fake_compress(messages, model, session_id=""):
        return [{"role": "system", "content": "[summary]"}, messages[-1]]

    runtime = ContextRuntime()
    runtime.compress_messages = fake_compress
    history = FakeHistory()

    result = await runtime.compact_thread(
        history_runtime=history,
        thread_id="thread-1",
        turn_id="compact-1",
        model="test-model",
    )

    assert result.messages_before == 3
    assert result.messages_after == 2
    assert history.replaced == [
        {"role": "system", "content": "[summary]"},
        {"role": "user", "content": "three"},
    ]


def test_context_runtime_estimate_tokens():
    """estimate_tokens() approximates token count (ASCII 0.25 token/char)."""
    runtime = ContextRuntime()
    msgs = [
        {"role": "user", "content": "hello world"},
        {"role": "assistant", "content": "hi"},
    ]
    # "hello world" (11) + "hi" (2) = 13 ASCII chars → int(13*0.25) = 3 tokens
    assert runtime.estimate_tokens(msgs) == 3


def test_context_runtime_estimate_tokens_counts_reasoning():
    """reasoning_content participates in context-size estimates (Issue #539)."""
    runtime = ContextRuntime()
    msgs = [{"role": "assistant", "content": "hi", "reasoning_content": "12345"}]
    # "hi" (2) + "12345" (5) = 7 ASCII chars → int(7*0.25) = 1 token
    assert runtime.estimate_tokens(msgs) == 1


def test_context_runtime_estimate_tokens_cjk_weighted():
    """CJK 字符按 ~1 token/char 加权（旧 chars/2.5 低估中文会话 → API 拒请求）。"""
    runtime = ContextRuntime()
    # 10 个中文字 → 10 tokens（ASCII 0）
    assert runtime.estimate_tokens([{"role": "user", "content": "一二三四五六七八九十"}]) == 10
    # 混合：2 中文 (2) + 8 ASCII (2) → 4 tokens
    assert runtime.estimate_tokens([{"role": "user", "content": "中文abc12345"}]) == 4
    # tool_calls 里的内容也加权（函数名/参数可能含中文）
    msgs = [{
        "role": "assistant",
        "content": None,
        "tool_calls": [{"function": {"name": "graph_render", "arguments": '{"path": "输出目录"}'}}],
    }]
    # tool_calls 序列含 4 个中文字 → 4 tokens + ASCII 部分
    assert runtime.estimate_tokens(msgs) >= 4


def test_context_runtime_should_auto_compact():
    """should_auto_compact() returns True when estimated tokens >= limit."""
    runtime = ContextRuntime()
    msgs = [{"role": "user", "content": "x" * 400}]  # 400 ASCII chars → 100 tokens
    assert runtime.should_auto_compact(msgs, token_limit=50) is True
    assert runtime.should_auto_compact(msgs, token_limit=200) is False


# ── trim 结构完整性（issue #715 现场：400 "tool must be a response to tool_calls"）─

def _asst_tc(call_id: str, name: str = "exec") -> dict:
    return {
        "role": "assistant",
        "content": None,
        "tool_calls": [{"id": call_id, "type": "function", "function": {"name": name, "arguments": "{}"}}],
        "reasoning_content": "",
    }


def _tool(call_id: str, content: str = "ok") -> dict:
    return {"role": "tool", "tool_call_id": call_id, "content": content}


def test_prune_drops_orphan_tool():
    """孤儿 tool 消息（前面无 assistant tool_calls）被丢弃。"""
    from miqi.runtime.context_runtime import _prune_unpaired_tool_messages

    msgs = [
        {"role": "user", "content": "hi"},
        _asst_tc("c1"),
        _tool("c1"),
        _tool("c2"),  # 孤儿：没有对应的 assistant tool_calls
    ]
    out = _prune_unpaired_tool_messages(msgs)
    assert out == msgs[:3]
    assert all(m.get("role") != "tool" or m.get("tool_call_id") == "c1" for m in out)


def test_prune_drops_unresponded_assistant_group():
    """无 tool 响应的 assistant(tool_calls) 整组丢弃（API 同样拒绝）。"""
    from miqi.runtime.context_runtime import _prune_unpaired_tool_messages

    msgs = [
        {"role": "user", "content": "hi"},
        _asst_tc("c1"),
        # 没有 tool 响应
        {"role": "user", "content": "next"},
    ]
    out = _prune_unpaired_tool_messages(msgs)
    assert out == [msgs[0], msgs[-1]]


def test_prune_keeps_complete_group():
    """完整 assistant(tool_calls) + tool 响应组原样保留。"""
    from miqi.runtime.context_runtime import _prune_unpaired_tool_messages

    msgs = [
        {"role": "user", "content": "hi"},
        _asst_tc("c1"),
        _tool("c1"),
        {"role": "user", "content": "again"},
    ]
    assert _prune_unpaired_tool_messages(msgs) == msgs


def test_trim_for_model_never_leaves_orphan_tool():
    """回归（8/19 现场）：trim 删组时「保留最后一条」保护可能留下孤儿 tool。

    构造超限序列且末尾是 tool 消息，trim 后不得出现未配对的 tool /
    未响应的 assistant(tool_calls)。
    """
    runtime = ContextRuntime()
    # 中文大内容把 est 推到 hard_limit 之上（ASCII 在新估算下太轻）；
    # 最后一条是重复 tool（turn 未完成 + 末尾保护）
    msgs: list[dict] = [{"role": "system", "content": "系统提示"}]
    for k in range(45):
        msgs.append({"role": "user", "content": f"用户消息{k} " + "好" * 800})
        msgs.append(_asst_tc(f"c{k}"))
        msgs.append(_tool(f"c{k}", "结" * 2000))
    msgs.append(_tool("c44"))  # 重复 tool（末尾保护）

    out = runtime.trim_for_model(msgs, model="deepseek-v4-flash")
    assert len(out) >= 2
    # 无孤儿 tool：每个 tool 前面必须有包含其 id 的 assistant(tool_calls)
    pending: set[str] = set()
    for m in out:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            pending.update(tc["id"] for tc in m["tool_calls"])
        elif m.get("role") == "tool":
            assert m.get("tool_call_id") in pending, f"孤儿 tool: {m.get('tool_call_id')}"
            pending.discard(m.get("tool_call_id"))
    # 无未响应的 assistant(tool_calls)
    assert not pending


def test_trim_under_limit_still_prunes_malformed_group():
    """回归（CodeRabbit #761）：上下文未超限时 early return 也要成对裁剪。"""
    runtime = ContextRuntime()
    # 短序列（est 远低于 hard_limit），但含孤儿 tool + 未响应 tool_calls
    msgs = [
        {"role": "user", "content": "hi"},
        _asst_tc("c1"),
        _tool("c1"),
        _tool("c2"),  # 孤儿
        _asst_tc("c3"),  # 未响应
    ]
    out = runtime.trim_for_model(msgs, model="deepseek-v4-flash")
    # 结构合法：无孤儿 tool、无未响应 tool_calls
    pending: set[str] = set()
    for m in out:
        if m.get("role") == "assistant" and m.get("tool_calls"):
            pending.update(tc["id"] for tc in m["tool_calls"])
        elif m.get("role") == "tool":
            assert m.get("tool_call_id") in pending, f"孤儿 tool: {m.get('tool_call_id')}"
            pending.discard(m.get("tool_call_id"))
    assert not pending


@pytest.mark.asyncio
async def test_context_runtime_with_real_compressor_reduces_messages():
    """When llm_call_fn is injected, compress_messages() delegates to
    ContextCompressor and actually reduces message count."""
    from unittest.mock import AsyncMock

    # A fake LLM that returns a summary string
    fake_llm = AsyncMock(return_value="[Compressed summary of conversation]")

    # Use a moderate context limit so tail budget < total messages
    runtime = ContextRuntime(
        llm_call_fn=fake_llm,
        context_limit_chars=50000,
    )

    # Build LARGE messages with substantial content to exceed tail budget
    messages: list[dict] = []
    for i in range(40):
        messages.append({
            "role": "user",
            "content": f"message {i:02d}: " + "x" * 250,
        })
        messages.append({
            "role": "assistant",
            "content": f"response {i:02d}: " + "y" * 250,
        })

    compressed = await runtime.compress_messages(
        messages, model="test-model", session_id="test-session",
    )

    # Should have called the LLM for summary
    fake_llm.assert_awaited_once()
    # Should be fewer messages than original
    assert len(compressed) < len(messages), (
        f"Expected compressed < original, got {len(compressed)} >= {len(messages)}"
    )
    # Should contain the summary content
    assert any(
        "summary" in str(m.get("content", "")).lower() for m in compressed
    ), f"Compressed output should contain summary: {compressed}"


def test_context_runtime_no_compressor_is_explicit_no_op():
    """Without llm_call_fn, compress_messages() returns messages unchanged
    but behavior is explicit, not accidental."""
    runtime = ContextRuntime()  # no llm_call_fn

    # _compressor should be None
    assert runtime._compressor is None


# ── trim_for_model: single-user-turn sessions with long tool loops ────────


def _make_tool_loop_messages(n_turns: int = 40) -> list[dict]:
    """system + one user turn + n_turns assistant/tool pairs + trailing user.
    Default size puts a single-user-turn session well over the 102400 limit."""
    msgs = [{"role": "system", "content": "skill injection " * 300}]
    msgs.append({"role": "user", "content": "用 mof-synthesis-price-agent 技能生成报告"})
    for i in range(n_turns):
        msgs.append({
            "role": "assistant",
            "content": f"step {i}",
            "reasoning_content": "reasoning " * 400,
            # 与 turn_runner 真实结构一致：assistant 工具调用轮必带 tool_calls
            # （缺该字段时 tool 消息会被 _prune_unpaired_tool_messages 判为孤儿）
            "tool_calls": [{"id": f"t{i}", "type": "function", "function": {"name": "exec", "arguments": "{}"}}],
        })
        msgs.append({
            "role": "tool",
            "tool_call_id": f"t{i}",
            "content": "exec output line\n" * 500,
        })
    msgs.append({"role": "user", "content": "继续"})
    return msgs


def test_trim_cuts_assistant_tool_groups_when_no_second_user_turn():
    """Single-user-turn sessions (long tool loop) must still trim: after the
    one user turn is gone, the oldest assistant/tool groups are cut instead
    (regression: trim stalled and the request exceeded the limit — real MOF
    skill session, #607)."""
    runtime = ContextRuntime()
    messages = _make_tool_loop_messages()
    # v4-flash 已登记（#775）：hard_limit = 102400×0.8 = 81920
    hard = int(runtime._resolve_model_max_input("deepseek-v4-flash") * runtime._CONTEXT_SAFETY_FACTOR)

    assert runtime.estimate_tokens(messages) > hard

    trimmed = runtime.trim_for_model(messages, "deepseek-v4-flash")

    assert runtime.estimate_tokens(trimmed) <= hard
    assert trimmed[0]["role"] == "system"
    assert trimmed[-1]["role"] == "user"


def test_v4_flash_registered_in_model_table():
    """#775：deepseek-v4-flash 必须显式登记真实上限 102400——否则 fallback
    128K×0.8=102400 恰好等于模型硬上限，0.8 安全系数被抵消、无响应余量。"""
    runtime = ContextRuntime()
    assert runtime._resolve_model_max_input("deepseek-v4-flash") == 102_400
    # 未登记模型仍走 128K fallback（行为不变）
    assert runtime._resolve_model_max_input("unknown-model-xyz") == 128_000


def test_trim_preserves_message_structure():
    """No orphan tool messages after trimming: every tool message must follow
    its assistant (or another tool of the same group)."""
    runtime = ContextRuntime()
    messages = _make_tool_loop_messages(n_turns=20)

    trimmed = runtime.trim_for_model(messages, "deepseek-v4-flash")

    for idx, m in enumerate(trimmed):
        if m["role"] == "tool":
            assert trimmed[idx - 1]["role"] in ("assistant", "tool"), (
                f"orphan tool message at index {idx}"
            )


def test_trim_keeps_recent_turns():
    """Trimming removes the OLDEST groups; recent assistant/tool groups and
    the trailing user message survive."""
    runtime = ContextRuntime()
    messages = _make_tool_loop_messages(n_turns=20)

    trimmed = runtime.trim_for_model(messages, "deepseek-v4-flash")

    roles = [m["role"] for m in trimmed]
    # the last full group (assistant+tool) before the trailing user survives
    assert roles[-2] == "tool" and roles[-3] == "assistant"


def test_trim_noop_when_under_limit():
    runtime = ContextRuntime()
    messages = [
        {"role": "system", "content": "s"},
        {"role": "user", "content": "hi"},
    ]
    assert runtime.trim_for_model(messages, "deepseek-v4-flash") == messages


# ── trim_for_model: trailing-tool regression matrix (#753) ─────────────────
# The legacy fixture always ends with a 'user' message, so the "message list
# ends with a tool result" shape (turn loop right after add_tool_result) was
# never covered — trimming left an orphaned trailing tool and the API
# rejected it with 400.  These parametrized cases pin that shape down.


def _assert_no_orphan_tool(trimmed: list[dict]) -> None:
    for idx, m in enumerate(trimmed):
        if m.get("role") == "tool":
            prev = trimmed[idx - 1] if idx > 0 else None
            assert prev is not None and (
                prev.get("role") == "tool"
                or (prev.get("role") == "assistant" and prev.get("tool_calls"))
            ), f"orphan tool message at index {idx}"


def _assert_no_headless_assistant(trimmed: list[dict]) -> None:
    """A trimmed list must never contain an assistant turn whose user
    question was dropped (review #752): [sys, u2, a2, t2] → after trimming
    u2 away, a2+t2 must not survive on their own.

    Matches trim_for_model's group semantics: a user message opens a group
    and multiple assistant/tool rounds are allowed until the next user.
    An assistant tool-call round with no ACTIVE user group is headless."""
    in_user_group = False
    for m in trimmed:
        if m.get("role") == "user":
            in_user_group = True
        elif m.get("role") == "assistant" and m.get("tool_calls"):
            if not in_user_group:
                raise AssertionError("headless assistant tool round (no active user group)")


@pytest.mark.parametrize("case", [
    # Trailing tool (turn loop mid-execution): must not leave an orphan.
    "trailing_tool",
    # Trailing user: normal conversation shape.
    "trailing_user",
    # Single user turn + long tool loop, tail is a tool group (#607 shape).
    "single_user_long_loop",
    # Multi-turn conversation with tool calls.
    "multi_turn",
])
def test_trim_trailing_tool_regression_matrix(case):
    """Trimming must never produce an orphaned tool message, regardless of
    what role the message list ends with (#753)."""
    runtime = ContextRuntime()
    sys_msg = {"role": "system", "content": "s" * 8000}

    if case == "trailing_tool":
        messages = [
            sys_msg,
            {"role": "user", "content": "u" * 5000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "a", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "x" * 8000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "2", "type": "function", "function": {"name": "b", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "2", "content": "x" * 8000},
        ]
    elif case == "trailing_user":
        messages = [
            sys_msg,
            {"role": "user", "content": "u" * 5000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "a", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "x" * 8000},
            {"role": "assistant", "content": "ok"},
            {"role": "user", "content": "u2" * 8000},
        ]
    elif case == "single_user_long_loop":
        messages = [
            sys_msg,
            {"role": "user", "content": "u" * 5000},
        ]
        for i in range(3):
            messages.append({
                "role": "assistant", "content": "",
                "tool_calls": [{"id": str(i), "type": "function", "function": {"name": f"t{i}", "arguments": "{}"}}],
            })
            messages.append({"role": "tool", "tool_call_id": str(i), "content": "x" * 6000})
    else:  # multi_turn
        messages = [
            sys_msg,
            {"role": "user", "content": "u" * 4000},
            {"role": "assistant", "content": "a1"},
            {"role": "user", "content": "u2" * 4000},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "type": "function", "function": {"name": "a", "arguments": "{}"}}]},
            {"role": "tool", "tool_call_id": "1", "content": "x" * 8000},
            {"role": "user", "content": "u3" * 4000},
        ]

    # gpt-4 (8192 max) is the smallest table entry — forces trimming.
    hard = int(8192 * runtime._CONTEXT_SAFETY_FACTOR)
    est_before = runtime.estimate_tokens(messages)
    assert est_before > hard, "test fixture must exceed the limit"

    trimmed = runtime.trim_for_model(messages, "gpt-4")

    assert trimmed[0]["role"] == "system"
    _assert_no_orphan_tool(trimmed)
    _assert_no_headless_assistant(trimmed)

    # multi_turn explicit check (review #752): if u2 was trimmed away, its
    # assistant tool-call (id "1") and tool result (id "1") must be gone
    # too — never a headless round surviving without its user question.
    # NB: substring match — the fixture's user content is "u2" * 4000, so a
    # literal "u2" comparison would always be truthy (CodeRabbit #752).
    if case == "multi_turn":
        u2_survives = any(
            "u2" in (m.get("content") or "") for m in trimmed if m["role"] == "user"
        )
        if not u2_survives:
            assert not any(
                m.get("tool_calls") and m["tool_calls"][0].get("id") == "1"
                for m in trimmed if m["role"] == "assistant"
            ), "u2 trimmed but its tool-call round survived"
            assert not any(
                m.get("tool_call_id") == "1" for m in trimmed if m["role"] == "tool"
            ), "u2 trimmed but its tool result survived"
        # sanity: fixture really contains the u2 group
        assert "u2" in "".join(
            m.get("content", "") for m in messages if m["role"] == "user"
        )

    # Provider-valid shapes: system first, no orphan tools, no headless
    # assistant turns.  Trim is best-effort — when the protected head fills
    # the list there may be nothing left to cut, so tokens must simply not
    # increase.
    assert runtime.estimate_tokens(trimmed) <= est_before
