"""harness 计划卡集成测试（#646-v2 GPT 拍板 T3/T5/T8）。

用 fake turn + mock model response 序列驱动真实 turn_runner：
- T3：模型分批调工具（每轮 1-2 个）→ turn 累计判定 → 达阈值弹计划卡
- T5：auto 模式不弹（非阻塞展示由前端处理）
- T8：modify 循环——用户点修改 → 模型重规划再弹新卡 → 确认后执行
"""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.agent.user_input_resolver import set_user_input_emitter
from miqi.execution.task_policy import TaskIntentRisk


def _make_turn(execution_policy: str = "edit"):
    """真实 TurnContext（MagicMock 的 getattr 会吞 _plan_* 默认值——插桩永不执行）。"""
    from pathlib import Path

    from miqi.runtime.turn_context import TurnContext

    return TurnContext(
        turn_id="turn-t3",
        agent_metadata=MagicMock(name="main", display_name="MiQi"),
        thread_id="thread-t3",
        workspace=Path("."),
        model="mock",
        provider=MagicMock(),
        execution_policy=execution_policy,
        user_content="搜索 5 篇论文并生成报告保存到工作区",
    )


class _FakeModelResponse:
    """模拟 LLM 一轮回复（tool_calls 序列）。"""

    def __init__(self, tool_calls, has_tool_calls=True):
        self.tool_calls = tool_calls
        self.has_tool_calls = has_tool_calls
        self.usage = {}


def _tc(name: str, args: dict | None = None):
    tc = MagicMock()
    tc.name = name
    tc.id = f"call_{name}_{id(tc) % 1000}"
    tc.arguments = args or {}
    return tc


class _FakeContext:
    """最小 ContextRuntime 替身：记录 messages。"""

    def __init__(self):
        self.messages: list[dict] = []

    def build_initial_messages(self, *, turn, user_content, system_prompt, history=None):
        msgs = [{"role": "system", "content": system_prompt}]
        if history:
            msgs.extend(history)
        msgs.append({"role": "user", "content": user_content})
        return msgs

    def trim_for_model(self, messages, model):
        return messages

    def add_assistant_message(self, messages, content="", reasoning_content=None, **kwargs):
        self.messages.append({"role": "assistant", "content": content})
        return messages + [{"role": "assistant", "content": content}]

    def add_tool_result(self, *, messages, tool_call_id, name, content, arguments=None):
        return messages + [{"role": "tool", "tool_call_id": tool_call_id, "name": name, "content": content}]

    def add_user_message(self, messages, content):
        return messages + [{"role": "user", "content": content}]


class _FakeTools:
    """工具执行替身：write_file 返回成功。"""

    async def execute_many(self, turn, tool_calls):
        results = []
        for tc in tool_calls:
            ctx = MagicMock()
            ctx.tool_name = tc.name
            ctx.status = MagicMock()
            ctx.status.value = "success"
            ctx.result = "ok"
            results.append(ctx)
        return results


def _make_runner(model_responses: list, tools=None):
    """构造真实 TaskRunner + 真实 TurnRunner（fake provider/tools），model_responses 按轮消费。"""
    from miqi.runtime.task_runner import TaskRunner
    from miqi.runtime.turn_runner import TurnRunner

    events = asyncio.Queue()

    async def fake_model_call(*args, **kwargs):
        resp = model_responses.pop(0) if model_responses else _FakeModelResponse([])
        return resp

    class _Provider:
        async def call(self, *a, **kw):
            return await fake_model_call()

        async def stream_chat(self, *a, **kw):
            from miqi.providers.base import LLMResponse, LLMStreamEvent

            resp = await fake_model_call()
            # 模拟流式：单块 completed 事件
            yield LLMStreamEvent(
                kind="completed",
                response=LLMResponse(
                    content="",
                    tool_calls=resp.tool_calls,
                    finish_reason="tool_calls" if resp.has_tool_calls else "stop",
                    usage=resp.usage,
                ),
            )

        def get_default_model(self):
            return "mock"

    provider = _Provider()

    class _Emitter:
        async def emit(self, event):
            events.put_nowait(event)

    turn_runner = TurnRunner(
        provider=provider,
        tool_runtime=tools or _FakeTools(),
        context_runtime=_FakeContext(),
        event_emitter=_Emitter(),
        max_iterations=10,
        ledger_runtime=None,
    )

    services = MagicMock()
    services.provider = provider
    services.model_settings = MagicMock()
    services.model_settings.model = "mock"
    services.model_settings.temperature = 0.1
    services.workspace = MagicMock()
    services.tool_registry = MagicMock()
    services.capability_resolver = None
    services.history_runtime = None  # 跳过持久化（测试聚焦计划卡逻辑）
    services.ledger_runtime = None
    services.user_input_resolver = None
    services.turn_runner = turn_runner

    runner = TaskRunner(services=services, event_queue=events)
    return runner, events


class TestHarnessPlanGate:
    @pytest.fixture(autouse=True)
    def _clean_emitter(self):
        from miqi.agent.user_input_resolver import (
            clear_thread_session,
            set_thread_session,
        )

        set_thread_session("thread-t3", "sess-t3")
        set_thread_session("thread-t5", "sess-t5")
        set_thread_session("thread-t8", "sess-t8")
        yield
        clear_thread_session("thread-t3")
        clear_thread_session("thread-t5")
        clear_thread_session("thread-t8")

    async def test_t5_auto_mode_no_plan_card(self):
        """T5：auto 模式不弹计划卡（非阻塞展示）。"""
        emitted_events = []

        async def fake_emitter(payload):
            emitted_events.append(payload)

        set_user_input_emitter("sess-t5", fake_emitter)
        responses = [
            _FakeModelResponse([_tc("write_file"), _tc("write_file")]),
            _FakeModelResponse([], has_tool_calls=False),
        ]
        runner, events = _make_runner(responses)
        await runner._handle_user_message(
            MagicMock(content="测试", thread_id="thread-t5", mode="auto", media=[])
        )
        assert emitted_events == [], "auto 模式不应弹计划卡"

    async def test_auto_timeline_shown_no_plan_card(self):
        """必测 2（GPT Q8）：Auto 模式——无 PlanCard（确认类）+ Timeline 出现。

        复杂任务（web_search+write_file：阶段跨类型+artifact=4）→
        auto 模式发 display=timeline 事件（非阻塞），不发确认卡。
        """
        from miqi.agent.user_input_resolver import set_thread_session

        set_thread_session("thread-a1", "sess-a1")
        emitted = []

        async def fake_emitter(payload):
            emitted.append(payload)

        set_user_input_emitter("sess-a1", fake_emitter)
        responses = [
            _FakeModelResponse([_tc("web_search"), _tc("write_file")]),
            _FakeModelResponse([], has_tool_calls=False),
        ]
        runner, events = _make_runner(responses)
        await runner._handle_user_message(
            MagicMock(content="搜索并生成报告", thread_id="thread-a1", mode="auto", media=[])
        )
        # Timeline 事件出现（display=timeline，无确认卡语义）
        timelines = [e for e in emitted if e.get("display") == "timeline"]
        assert len(timelines) >= 1, f"auto 模式应发 Timeline 事件: {emitted}"
        assert timelines[0]["title"] == "AI 正在执行任务"
        # 无阻塞确认卡（无 input_id 关联的 gate 等待——display 非空即区分）
        assert all(e.get("display") == "timeline" for e in emitted), "auto 模式不得发确认卡"

    async def test_mutation_gate_blocks_write_before_confirm(self):
        """必测 1（GPT Q8）：PlanCard 未确认时，write/upload 不得执行。

        场景：搜索+写文件任务 → 弹卡 → 用户【取消】→ write_file 从未执行
        （execute_many 只收到 READ 工具或为空）。
        """
        from miqi.agent.user_input_resolver import (
            resolve_user_input,
            set_thread_session,
        )

        original_resolve = resolve_user_input
        emitted = []

        async def fake_emitter(payload):
            emitted.append(payload)

        set_user_input_emitter("sess-m1", fake_emitter)
        set_thread_session("thread-m1", "sess-m1")

        executed_tools: list[str] = []

        class RecordingTools(_FakeTools):
            async def execute_many(self, turn, tool_calls):
                executed_tools.extend(tc.name for tc in tool_calls)
                return await super().execute_many(turn, tool_calls)

        responses = [
            _FakeModelResponse([_tc("web_search"), _tc("write_file")]),
            _FakeModelResponse([], has_tool_calls=False),
        ]

        async def cancel_flow():
            # 等弹卡 → 用户取消
            for _ in range(100):
                if emitted:
                    break
                await asyncio.sleep(0.01)
            if emitted:
                original_resolve(emitted[0]["input_id"], {"choice_id": "cancel"})

        runner, events = _make_runner(responses, tools=RecordingTools())
        flow = asyncio.create_task(cancel_flow())
        await runner._handle_user_message(
            MagicMock(content="搜索并写文件", thread_id="thread-m1", mode="edit", media=[])
        )
        await flow
        assert len(emitted) >= 1, "弹卡"
        # 未确认：write_file 不得执行（READ 可执行）
        assert "write_file" not in executed_tools, f"write_file 在未确认时执行了: {executed_tools}"

    async def test_confirm_freezes_plan_and_initializes_todo(self):
        """v3.3 Step 3：确认后冻结 PlanSnapshot + TodoState 初始化。

        用户确认 → turn._run_ctx 存在；plan_snapshot.steps 与 todo 一致
        （plan-kind、QUEUED、稳定 ID）。
        """
        from miqi.agent.user_input_resolver import (
            resolve_user_input,
            set_thread_session,
        )

        original_resolve = resolve_user_input
        emitted = []

        async def fake_emitter(payload):
            emitted.append(payload)

        set_user_input_emitter("sess-s3", fake_emitter)
        set_thread_session("thread-s3", "sess-s3")

        executed_tools: list[str] = []
        seen_turns: list = []

        class RecordingTools(_FakeTools):
            async def execute_many(self, turn, tool_calls):
                seen_turns.append(turn)
                executed_tools.extend(tc.name for tc in tool_calls)
                return await super().execute_many(turn, tool_calls)

        responses = [
            _FakeModelResponse([_tc("web_search"), _tc("write_file")]),
            _FakeModelResponse([], has_tool_calls=False),
        ]

        async def confirm_flow():
            for _ in range(100):
                if emitted:
                    break
                await asyncio.sleep(0.01)
            if emitted:
                original_resolve(emitted[0]["input_id"], {"choice_id": "confirm"})

        runner, events = _make_runner(responses, tools=RecordingTools())
        flow = asyncio.create_task(confirm_flow())
        await runner._handle_user_message(
            MagicMock(content="搜索并写文件", thread_id="thread-s3", mode="edit", media=[])
        )
        await flow

        # 确认后：_run_ctx 冻结（PlanSnapshot + TodoState 初始化）
        assert seen_turns and getattr(seen_turns[0], "_run_ctx", None) is not None, \
            "确认后 turn._run_ctx 应冻结（PlanSnapshot + TodoState）"
        ctx = seen_turns[0]._run_ctx
        assert ctx.plan_snapshot is not None and ctx.plan_snapshot.steps
        assert all(t.status == "queued" and t.kind == "plan" for t in ctx.todo_state.items)
        assert len(ctx.todo_state.items) == len(ctx.plan_snapshot.steps)
        assert ctx.todo_state.revision == 1
        # 确认后 write_file 执行了（mutation gate 放行）
        assert "write_file" in executed_tools, f"确认后 write_file 应执行: {executed_tools}"
        assert "web_search" in executed_tools
