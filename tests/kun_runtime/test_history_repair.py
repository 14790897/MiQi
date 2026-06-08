"""Phase 8 supplementary tests — History repair, history hygiene, token economy, tool storm breaker, tool call repair, compactor."""

import pytest

from miqi.kun_runtime.auto_model_router import resolve_auto_model_route
from miqi.kun_runtime.compactor import ContextCompactor
from miqi.kun_runtime.context_estimator import estimate_items_tokens, estimate_tokens
from miqi.kun_runtime.history_hygiene import apply_request_history_hygiene
from miqi.kun_runtime.history_repair import heal_loaded_history_items, repair_model_history_items
from miqi.kun_runtime.token_economy import TOKEN_ECONOMY_INSTRUCTION, normalize_token_economy_config
from miqi.kun_runtime.tool_call_repair import repair_dispatch_tool_arguments
from miqi.kun_runtime.tool_storm_breaker import ToolStormBreaker


class TestHistoryRepair:
    def test_heal_orphan_tool_results_dropped(self) -> None:
        items = [
            {"id": "u1", "kind": "user_message", "text": "hello"},
            {"id": "tr1", "kind": "tool_result", "toolName": "read", "callId": "orphan", "output": "data"},
        ]
        healed, changed = heal_loaded_history_items(items)
        result_ids = [i.get("callId") for i in healed if i["kind"] == "tool_result"]
        assert "orphan" not in result_ids  # orphan dropped
        assert changed

    def test_repair_injects_stubs_for_missing_results(self) -> None:
        items = [
            {"id": "tc1", "kind": "tool_call", "toolName": "read", "callId": "call_1", "arguments": {}},
        ]
        repaired = repair_model_history_items(items)
        kinds = [i["kind"] for i in repaired]
        assert "tool_result" in kinds  # stub injected

    def test_valid_history_unchanged(self) -> None:
        items = [
            {"id": "u1", "kind": "user_message", "text": "hello"},
            {"id": "tc1", "kind": "tool_call", "toolName": "read", "callId": "call_1", "arguments": {}},
            {"id": "tr1", "kind": "tool_result", "toolName": "read", "callId": "call_1", "output": "ok"},
        ]
        healed, changed = heal_loaded_history_items(items)
        assert not changed


class TestHistoryHygiene:
    def test_oversized_tool_result_trimmed(self) -> None:
        big = "x" * 50000
        items = [
            {"id": "tr1", "kind": "tool_result", "toolName": "read", "callId": "c1", "output": big},
        ]
        result = apply_request_history_hygiene(
            items, max_lines=200, max_bytes=4096
        )
        trimmed = result[0]["output"]
        assert len(trimmed) < len(big)
        assert "cache hygiene" in trimmed

    def test_small_result_unchanged(self) -> None:
        items = [
            {"id": "tr1", "kind": "tool_result", "toolName": "read", "callId": "c1", "output": "small"},
        ]
        result = apply_request_history_hygiene(items)
        assert result[0]["output"] == "small"


class TestTokenEconomy:
    def test_defaults(self) -> None:
        cfg = normalize_token_economy_config()
        assert cfg["enabled"] is False
        assert cfg["concise_responses"] is True

    def test_override(self) -> None:
        cfg = normalize_token_economy_config({"enabled": True})
        assert cfg["enabled"] is True

    def test_instruction_is_string(self) -> None:
        assert isinstance(TOKEN_ECONOMY_INSTRUCTION, str)
        assert len(TOKEN_ECONOMY_INSTRUCTION) > 10


class TestToolStormBreaker:
    def test_initial_no_suppression(self) -> None:
        breaker = ToolStormBreaker(window_size=4, threshold=3)
        result = breaker.inspect("read", {"path": "a.txt"})
        assert not result["suppress"]

    def test_same_call_thrice_suppresses(self) -> None:
        breaker = ToolStormBreaker(window_size=4, threshold=2)
        breaker.inspect("read", {"path": "same.txt"})  # 1st
        breaker.inspect("read", {"path": "same.txt"})  # 2nd
        result = breaker.inspect("read", {"path": "same.txt"})  # 3rd
        assert result["suppress"]
        assert "identical arguments" in result["reason"]

    def test_different_args_no_suppression(self) -> None:
        breaker = ToolStormBreaker(window_size=4, threshold=2)
        breaker.inspect("read", {"path": "a.txt"})
        result = breaker.inspect("read", {"path": "b.txt"})
        assert not result["suppress"]

    def test_exempt_tool(self) -> None:
        breaker = ToolStormBreaker(threshold=2)
        for _ in range(5):
            result = breaker.inspect("ask_user", {})
            assert not result["suppress"]

    def test_reset_clears(self) -> None:
        breaker = ToolStormBreaker(threshold=2)
        breaker.inspect("read", {"path": "x"})
        breaker.inspect("read", {"path": "x"})
        breaker.reset()
        result = breaker.inspect("read", {"path": "x"})
        assert not result["suppress"]


class TestToolCallRepair:
    def test_flatten_wrapper(self) -> None:
        result = repair_dispatch_tool_arguments({
            "arguments": {"path": "a.txt"},
        })
        assert result["arguments"] == {"path": "a.txt"}
        assert len(result["notes"]) >= 1

    def test_no_repair_needed(self) -> None:
        result = repair_dispatch_tool_arguments({"path": "a.txt"})
        assert result["arguments"] == {"path": "a.txt"}

    def test_parse_json_string(self) -> None:
        result = repair_dispatch_tool_arguments({
            "arguments": '{"path": "a.txt"}',
        })
        assert result["arguments"] == {"path": "a.txt"}

    def test_truncate_too_long_string(self) -> None:
        result = repair_dispatch_tool_arguments({
            "path": "a" * 100000,
        }, max_string_bytes=100)
        assert len(str(result["arguments"]["path"])) < 100000


class TestContextCompactor:
    def test_small_history_no_compaction(self) -> None:
        compactor = ContextCompactor(soft_threshold=10000, hard_threshold=20000)
        items = [{"id": "u1", "kind": "user_message", "text": "hi"}]
        assert compactor.plan_compaction(items) is None

    def test_large_history_triggers_plan(self) -> None:
        compactor = ContextCompactor(soft_threshold=5, hard_threshold=20)
        items = [{"id": f"m{i}", "kind": "user_message", "text": "x" * 100} for i in range(5)]
        plan = compactor.plan_compaction(items)
        assert plan is not None

    def test_compact_produces_summary(self) -> None:
        compactor = ContextCompactor(soft_threshold=5, hard_threshold=200)
        items = [{"id": f"m{i}", "kind": "user_message", "text": f"msg {i}"} for i in range(10)]
        result = compactor.compact("th1", "t1", items, keep_recent=2)
        assert result["replacedTokens"] > 0
        assert len(result["next"]) < len(items)

    def test_should_compact(self) -> None:
        compactor = ContextCompactor(soft_threshold=5, hard_threshold=200)
        small = [{"id": "u1", "kind": "user_message", "text": "hi"}]
        assert not compactor.should_compact(small)


class TestContextEstimator:
    def test_estimate_tokens(self) -> None:
        assert estimate_tokens("hello world") > 0
        assert estimate_tokens("") == 0

    def test_estimate_items(self) -> None:
        items = [
            {"kind": "user_message", "text": "hello"},
            {"kind": "assistant_text", "text": "response"},
        ]
        assert estimate_items_tokens(items) > 0


class TestAutoModelRouter:
    @pytest.mark.asyncio
    async def test_first_non_auto_wins(self) -> None:
        result = await resolve_auto_model_route(
            ["auto", "deepseek-chat", "claude-sonnet"],
            default_model="fallback",
        )
        assert result["model"] == "deepseek-chat"

    @pytest.mark.asyncio
    async def test_all_auto_falls_back(self) -> None:
        result = await resolve_auto_model_route(
            ["auto", "auto"],
            default_model="fallback",
        )
        assert result["model"] == "fallback"

    @pytest.mark.asyncio
    async def test_skips_none(self) -> None:
        result = await resolve_auto_model_route(
            [None, "", "deepseek-chat"],
            default_model="fallback",
        )
        assert result["model"] == "deepseek-chat"
