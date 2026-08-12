"""Issue #646 — ask_user_confirm_card: tool contract, tool-host interception,
storm-breaker exemption, never-parallel classification, contracts, and the
user-input gate timeout."""

from __future__ import annotations

import asyncio
import json

import pytest

from miqi.agent.tools.ask_user_confirm import (
    DEFAULT_CHOICES,
    AskUserConfirmCardTool,
)
from miqi.agent.user_input_resolver import make_resolver
from miqi.agent.tools.registry import ToolRegistry, _NEVER_PARALLEL_TOOLS
from miqi.kun_runtime.contracts import TurnStatus, UserInputItem, UserInputRequestedEvent
from miqi.kun_runtime.tool_host import (
    ASK_USER_CONFIRM_TOOL,
    MiQiToolHost,
    ToolCallLike,
    ToolHostContext,
)
from miqi.kun_runtime.tool_storm_breaker import STORM_EXEMPT_TOOLS, ToolStormBreaker
from miqi.kun_runtime.user_input_gate import UserInputGate


# ═══════════════════════════════════════════════════════════════════════════════
# Tool contract
# ═══════════════════════════════════════════════════════════════════════════════


class TestToolContract:
    def test_name_and_schema(self):
        tool = AskUserConfirmCardTool()
        assert tool.name == "ask_user_confirm_card"
        schema = tool.to_schema()["function"]
        params = schema["parameters"]["properties"]
        assert set(schema["parameters"]["required"]) == {"title", "message"}
        for key in ("title", "message", "steps", "choices", "allow_remember_choice", "timeout_seconds"):
            assert key in params
        # 默认超时 120s
        assert params["timeout_seconds"]["default"] == 120
        # 中文描述：模型必须能理解这是 AI 主动发起的人机握手
        assert "确认" in schema["description"]

    def test_fallback_execute_returns_error(self):
        """No user-input channel wired → must NOT fabricate a decision."""
        tool = AskUserConfirmCardTool()
        result = asyncio.run(tool.execute(title="确认", message="可以吗"))
        assert result.startswith("Error")
        assert "不要假设用户已同意" in result


class TestNormalizeArgs:
    def test_defaults(self):
        payload = AskUserConfirmCardTool.normalize_args({"title": "确认执行方案？", "message": "4 个步骤"})
        assert payload["title"] == "确认执行方案？"
        assert payload["message"] == "4 个步骤"
        assert payload["choices"] == DEFAULT_CHOICES
        assert payload["timeout_seconds"] == 120
        assert payload["allow_remember_choice"] is False
        assert payload["steps"] == []

    def test_choices_structured(self):
        payload = AskUserConfirmCardTool.normalize_args({
            "title": "上传？",
            "message": "确认上传到 Qraft",
            "choices": [{"id": "confirm", "label": "确认上传"}, {"id": "cancel", "label": "取消"}],
            "timeout_seconds": 30,
            "allow_remember_choice": True,
        })
        assert payload["choices"] == [{"id": "confirm", "label": "确认上传"}, {"id": "cancel", "label": "取消"}]
        assert payload["timeout_seconds"] == 30
        assert payload["allow_remember_choice"] is True

    def test_bad_choices_fallback_to_default(self):
        payload = AskUserConfirmCardTool.normalize_args({"title": "t", "message": "m", "choices": []})
        assert payload["choices"] == DEFAULT_CHOICES

    def test_steps_get_ids(self):
        payload = AskUserConfirmCardTool.normalize_args({
            "title": "t", "message": "m",
            "steps": [{"title": "搜索论文"}, {"id": "query_price", "title": "查价格"}],
        })
        assert payload["steps"] == [
            {"id": "step_0", "title": "搜索论文"},
            {"id": "query_price", "title": "查价格"},
        ]


class TestBuildResult:
    def test_submitted_confirm(self):
        out = AskUserConfirmCardTool.build_result({
            "status": "submitted",
            "answers": {"choice_id": "confirm", "choice_label": "确认执行"},
        })
        data = json.loads(out)
        assert data["status"] == "confirmed"
        assert data["choice_id"] == "confirm"
        assert data["choice_label"] == "确认执行"

    def test_cancelled(self):
        out = AskUserConfirmCardTool.build_result({"status": "cancelled"})
        data = json.loads(out)
        assert data["status"] == "cancelled"
        assert data["choice_id"] == ""


# ═══════════════════════════════════════════════════════════════════════════════
# Tool-host interception
# ═══════════════════════════════════════════════════════════════════════════════


def _ctx(await_user_input=None) -> ToolHostContext:
    return ToolHostContext(
        thread_id="thr_1",
        turn_id="turn_1",
        workspace="/tmp/ws",
        await_user_input=await_user_input,
    )


class TestToolHostInterception:
    def test_routes_through_await_user_input(self):
        registry = ToolRegistry()
        registry.register(AskUserConfirmCardTool())

        async def fake_gate(payload):
            assert payload["title"] == "确认执行方案？"
            assert payload["steps"][0]["id"] == "search_papers"
            return {"status": "submitted", "answers": {"choice_id": "confirm", "choice_label": "确认执行"}}

        host = MiQiToolHost(registry)
        call = ToolCallLike(call_id="call_1", tool_name=ASK_USER_CONFIRM_TOOL, arguments={
            "title": "确认执行方案？",
            "message": "4 个步骤",
            "steps": [{"id": "search_papers", "title": "搜索论文"}],
        })
        result = asyncio.run(host.execute(call, _ctx(await_user_input=fake_gate)))
        item = result.item
        assert item["status"] == "completed"
        assert item["isError"] is False
        data = json.loads(item["output"])
        assert data["status"] == "confirmed"
        assert data["choice_id"] == "confirm"

    def test_cancelled_choice(self):
        registry = ToolRegistry()
        registry.register(AskUserConfirmCardTool())

        async def fake_gate(payload):
            return {"status": "cancelled", "reason": "timeout"}

        host = MiQiToolHost(registry)
        call = ToolCallLike(call_id="call_2", tool_name=ASK_USER_CONFIRM_TOOL, arguments={
            "title": "上传？", "message": "确认上传",
        })
        result = asyncio.run(host.execute(call, _ctx(await_user_input=fake_gate)))
        data = json.loads(result.item["output"])
        assert data["status"] == "cancelled"
        assert data["reason"] == "timeout"

    def test_no_channel_falls_back_to_tool_error(self):
        """No await_user_input wired → tool's own execute() returns error."""
        registry = ToolRegistry()
        registry.register(AskUserConfirmCardTool())
        host = MiQiToolHost(registry)
        call = ToolCallLike(call_id="call_3", tool_name=ASK_USER_CONFIRM_TOOL, arguments={
            "title": "t", "message": "m",
        })
        result = asyncio.run(host.execute(call, _ctx(await_user_input=None)))
        assert result.item["isError"] is True
        assert "Error" in result.item["output"]


# ═══════════════════════════════════════════════════════════════════════════════
# Storm breaker / parallel classification / contracts
# ═══════════════════════════════════════════════════════════════════════════════


class TestGuards:
    def test_storm_breaker_exempt(self):
        assert ASK_USER_CONFIRM_TOOL in STORM_EXEMPT_TOOLS
        breaker = ToolStormBreaker()
        for _ in range(5):
            verdict = breaker.inspect(ASK_USER_CONFIRM_TOOL, {"title": "t"})
            assert verdict["suppress"] is False

    def test_never_parallel(self):
        assert ASK_USER_CONFIRM_TOOL in _NEVER_PARALLEL_TOOLS

    def test_contracts_extensions(self):
        assert TurnStatus.waiting_for_user == "waiting_for_user"
        item = UserInputItem(
            kind="user_input", role="system", inputId="ui_1", prompt="p", id="item_1",
            status="pending", threadId="thr", turnId="turn", createdAt="2026-08-11T00:00:00Z",
            title="确认执行方案？", steps=[{"id": "s1", "title": "搜索论文"}],
            choices=[{"id": "confirm", "label": "确认执行"}], timeout_seconds=120,
            allow_remember_choice=True,
        )
        assert item.title == "确认执行方案？"
        assert item.steps[0]["id"] == "s1"
        assert item.timeout_seconds == 120
        assert item.allow_remember_choice is True
        ev = UserInputRequestedEvent(
            kind="user_input_requested", inputId="ui_1", title="t", timeoutSeconds=120,
            seq=1, timestamp="2026-08-11T00:00:00Z", threadId="thr",
        )
        assert ev.timeoutSeconds == 120


class TestUserInputGateTimeout:
    def test_timeout_resolves_cancelled(self):
        async def scenario():
            gate = UserInputGate()
            task = asyncio.create_task(
                gate.request("thr", "turn", "item", "prompt", timeout=0.05)
            )
            result = await task
            return result

        result = asyncio.run(scenario())
        assert result["status"] == "cancelled"

    def test_resolve_submitted(self):
        async def scenario():
            gate = UserInputGate()
            task = asyncio.create_task(
                gate.request("thr", "turn", "item", "prompt", timeout=5)
            )
            await asyncio.sleep(0.01)
            gate.resolve("user_input_" + list(gate._pending)[0].split("_", 2)[-1], {"choice_id": "confirm"})
            return await task

        result = asyncio.run(scenario())
        assert result["status"] == "submitted"
        assert result["answers"]["choice_id"] == "confirm"


class TestUserInputHistory:
    def test_record_and_query(self):
        from miqi.agent.user_input_history import add_user_input_history, clear_history, get_user_input_history

        clear_history()
        add_user_input_history(
            title="确认执行方案？", status="submitted",
            choice_id="confirm", choice_label="确认执行",
            thread_id="thr", turn_id="turn",
        )
        add_user_input_history(
            title="是否上传？", status="cancelled", reason="timeout",
        )
        history = get_user_input_history()
        assert len(history) == 2
        assert history[0]["title"] == "是否上传？"  # most recent first
        assert history[0]["reason"] == "timeout"
        assert history[1]["choice_label"] == "确认执行"
        clear_history()


class TestRememberChoice:
    def test_same_card_reuses_choice_without_pending(self):
        from miqi.kun_runtime.loop import _remember_key

        payload = {"title": "确认执行方案？", "choices": [{"id": "confirm", "label": "确认执行"}]}
        key = _remember_key(payload)
        gate = UserInputGate()
        assert gate.remembered_choice("thr", key) is None
        gate.remember("thr", key, {"choice_id": "confirm", "choice_label": "确认执行"})
        assert gate.remembered_choice("thr", key)["choice_id"] == "confirm"
        # 不同 title → 不同 key
        other = _remember_key({"title": "是否上传？", "choices": [{"id": "confirm", "label": "确认上传"}]})
        assert other != key
        assert gate.remembered_choice("thr", other) is None
        # 跨 thread 不共享
        assert gate.remembered_choice("thr2", key) is None


class TestLegacyResolverPath:
    """Legacy desktop path: tool resolver → shared gate → emit → resolve."""

    def test_tool_blocks_then_resolves(self):
        from miqi.agent.user_input_resolver import (
            resolve_user_input,
            set_user_input_emitter,
        )
        from miqi.agent.tools.ask_user_confirm import AskUserConfirmCardTool

        emitted = {}

        async def emitter(payload):
            emitted["payload"] = payload

        set_user_input_emitter(emitter)
        try:
            tool = AskUserConfirmCardTool(resolver=make_resolver())
            args = {"title": "确认执行方案？", "message": "4 个步骤", "timeout_seconds": 5}

            async def scenario():
                task = asyncio.create_task(tool.execute(**args))
                # 等卡片事件发出
                for _ in range(50):
                    if "payload" in emitted:
                        break
                    await asyncio.sleep(0.02)
                assert "payload" in emitted, "user_input_requested 未发出"
                input_id = emitted["payload"]["input_id"]
                assert emitted["payload"]["title"] == "确认执行方案？"
                ok = resolve_user_input(input_id, {"choice_id": "confirm", "choice_label": "确认执行"})
                assert ok
                result = await task
                return result

            result = asyncio.run(scenario())
        finally:
            set_user_input_emitter(None)

        import json as _json

        data = _json.loads(result)
        assert data["status"] == "confirmed"
        assert data["choice_id"] == "confirm"

    def test_tool_cancelled_when_no_channel(self):
        """Resolver exists but no emitter wired → safe cancelled, never a fake confirm."""
        import json as _json

        from miqi.agent.user_input_resolver import set_user_input_emitter
        from miqi.agent.tools.ask_user_confirm import AskUserConfirmCardTool

        set_user_input_emitter(None)
        tool = AskUserConfirmCardTool(resolver=make_resolver())
        result = asyncio.run(tool.execute(title="t", message="m"))
        data = _json.loads(result)
        assert data["status"] == "cancelled"
        assert "user-input channel" in data["reason"]

    def test_no_resolver_fallback_error(self):
        """No resolver at all → structured error, never fabricate a decision."""
        tool = AskUserConfirmCardTool()
        result = asyncio.run(tool.execute(title="t", message="m"))
        assert result.startswith("Error")
        assert "不要假设用户已同意" in result
