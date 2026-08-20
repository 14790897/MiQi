"""临时 debug：harness 弹卡判定链路。"""
import asyncio
import sys

sys.path.insert(0, r"D:\Desktop\811\MiQi")
sys.path.insert(0, r"D:\Desktop\811\MiQi\tests")

from unittest.mock import MagicMock

from miqi.runtime.turn_runner import TurnRunner
from miqi.providers.base import LLMResponse, LLMStreamEvent
from kun_runtime.test_harness_plan_gate import (
    _FakeContext,
    _FakeModelResponse,
    _FakeTools,
    _tc,
)
from miqi.agent.user_input_resolver import (
    set_thread_session,
    set_user_input_emitter,
    resolve_user_input,
)


async def main():
    emitted = []
    set_thread_session("thread-t3", "sess-t3")

    async def fake_emitter(payload):
        emitted.append(payload)
        print("  [emitter] 收到计划卡 payload:", payload.get("title"), "steps:", [s["name"] for s in payload.get("steps", [])])

    set_user_input_emitter("sess-t3", fake_emitter)

    responses = [
        _FakeModelResponse([_tc("web_search"), _tc("web_search")]),
        _FakeModelResponse([_tc("paper_get"), _tc("paper_get"), _tc("write_file")]),
        _FakeModelResponse([], has_tool_calls=False),
    ]

    async def fake_call(*a, **kw):
        resp = responses.pop(0) if responses else _FakeModelResponse([])
        print("  [model] 轮次:", [t.name for t in resp.tool_calls], "has:", resp.has_tool_calls)
        return resp

    class P:
        async def call(self, *a, **kw):
            return await fake_call()

        async def stream_chat(self, *a, **kw):
            resp = await fake_call()
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

    events = asyncio.Queue()

    class _Emitter:
        async def emit(self, event):
            events.put_nowait(event)

    tr = TurnRunner(
        provider=P(),
        tool_runtime=_FakeTools(),
        context_runtime=_FakeContext(),
        event_emitter=_Emitter(),
        max_iterations=10,
    )
    turn = MagicMock()
    turn.turn_id = "t1"
    turn.thread_id = "thread-t3"
    turn.execution_policy = "edit"
    turn.bypass_approval = False
    turn.user_content = "x"

    async def auto_confirm():
        for _ in range(100):
            if emitted:
                break
            await asyncio.sleep(0.01)
        if emitted:
            print("  [test] 自动确认第一张卡")
            resolve_user_input(emitted[0]["input_id"], {"choice_id": "confirm"})

    confirm_task = asyncio.create_task(auto_confirm())
    r = await tr.run(turn=turn, user_content="测试", system_prompt="s", tools=[], history=[])
    await confirm_task
    print("seen:", getattr(turn, "_plan_seen_tools", None))
    print("rounds:", getattr(turn, "_plan_rounds", None))
    print("done:", getattr(turn, "_plan_confirm_done", None))
    print("emitted 数量:", len(emitted))
    print("final:", (r.final_content or "")[:40])


asyncio.run(main())
