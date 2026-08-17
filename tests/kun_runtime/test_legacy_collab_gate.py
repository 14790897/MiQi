"""Collaboration gate on the legacy orchestrator path (issue #646 design v2).

The KUN tool_host gate covers the KUN runtime; the legacy desktop path
(orchestrator) needs the same harness-forced confirm card so the card appears
even when the model never calls ask_user_confirm_card (issue's 备选方案:
"由前端规则自动在某些工具执行前弹窗，不经过 AI 决策").
"""
import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.execution.hook_runtime import HookRuntime
from miqi.execution.orchestrator import ToolOrchestrator, ToolExecutionContext
from miqi.execution.permission_engine import PermissionDecision, PermissionVerdict


def make_ctx(tool_name: str = "write_file", autonomy_mode: str | None = "manual"):
    ctx = ToolExecutionContext(
        tool_name=tool_name,
        tool_call_id="call_001",
        arguments={"path": "/tmp/x.txt", "content": "hi"},
        turn_id="turn_001",
        thread_id="thread_abc",
        agent_type="main",
    )
    if autonomy_mode:
        ctx.autonomy_mode = autonomy_mode  # dataclass 动态注入
    return ctx


def make_orch():
    pe = MagicMock()
    pe.check = AsyncMock(
        return_value=PermissionDecision(verdict=PermissionVerdict.ALLOW, reason="ok")
    )
    se = MagicMock()
    se.select = AsyncMock()
    # 工具 mock：让通过 gate 的工具真正"执行成功"——断言必须基于
    # 显式结果（SUCCESS/结果内容），而不是依赖 sandbox 失败的副作用。
    tr = MagicMock()
    tr.get.return_value = MagicMock()
    tr.get.return_value.execute = AsyncMock(return_value="ok: /tmp/x.txt written")
    ev = MagicMock()
    ev.emit = AsyncMock()
    return ToolOrchestrator(
        permission_engine=pe,
        sandbox_engine=se,
        hook_runtime=HookRuntime(),
        tool_registry=tr,
        event_emitter=ev,
    )


def user_click(choice_id: str, choice_label: str):
    """模拟真实桌面：弹卡后用户异步点击（晚于请求注册）。"""
    from miqi.agent import user_input_resolver

    async def do_resolve(payload):
        await asyncio.sleep(0.05)  # 让 gate.request 先注册 pending
        ok = user_input_resolver.resolve_user_input(
            payload["input_id"],
            {"choice_id": choice_id, "choice_label": choice_label},
        )
        assert ok, f"resolve {payload['input_id']} failed"

    async def emit(payload):
        asyncio.create_task(do_resolve(payload))

    return emit


class TestLegacyCollabGate:
    async def test_no_channel_degrades_to_allow(self):
        """无 user-input 通道 → gate 放行（不弹卡不阻塞）。"""
        from miqi.agent import user_input_resolver

        user_input_resolver.set_user_input_emitter(None)
        ctx = await make_orch().execute(make_ctx())
        assert ctx.status.value != "denied_by_user"

    async def test_with_channel_confirm_allows(self):
        """有通道 + 用户确认 → 继续执行（不拒绝）。"""
        from miqi.agent import user_input_resolver

        user_input_resolver.set_user_input_emitter(user_click("confirm", "确认执行"))
        ctx = await make_orch().execute(make_ctx())
        assert ctx.status.value != "denied_by_user"

    async def test_with_channel_cancel_denies(self):
        """有通道 + 用户取消 → DENIED_BY_USER。"""
        from miqi.agent import user_input_resolver

        user_input_resolver.set_user_input_emitter(user_click("cancel", "取消"))
        ctx = await make_orch().execute(make_ctx())
        assert ctx.status.value == "denied_by_user"

    async def test_read_tool_skips_gate_even_with_channel(self):
        """读类工具（web_search）有通道也不弹卡。"""
        from miqi.agent import user_input_resolver

        called = []

        async def emit(payload):
            called.append(payload)

        user_input_resolver.set_user_input_emitter(emit)
        await make_orch().execute(make_ctx(tool_name="web_search"))
        assert called == []

    async def test_external_confirm_denies_when_cancelled(self):
        """外部请求类工具（upload_workflow）任何模式必确认，取消→拒绝。"""
        from miqi.agent import user_input_resolver

        user_input_resolver.set_user_input_emitter(user_click("cancel", "取消"))
        ctx = await make_orch().execute(make_ctx(tool_name="upload_workflow"))
        assert ctx.status.value == "denied_by_user"


class TestRealPathAutonomyMapping:
    """P0-1 (审阅): 真实构造路径——execution_policy → autonomy_mode 映射。

    不动态注入 ctx.autonomy_mode；从 turn.execution_policy 经
    autonomy_mode_from_policy 映射（与 ToolRuntime.execute_one 一致）。
    """

    def test_policy_mapping(self):
        from miqi.execution.collab_policy import autonomy_mode_from_policy

        assert autonomy_mode_from_policy("plan") == "plan"
        assert autonomy_mode_from_policy("ask") == "manual"
        assert autonomy_mode_from_policy("manual") == "manual"
        assert autonomy_mode_from_policy("edit") == "supervised"
        assert autonomy_mode_from_policy("auto") == "autonomous"
        assert autonomy_mode_from_policy(None) == "supervised"
        assert autonomy_mode_from_policy("bogus") == "supervised"

    async def test_plan_mode_denies_write(self):
        """plan 模式 + write_file → DENY（P1-3：gate 拦截，不执行不弹卡）。"""
        ctx = await make_orch().execute(
            make_ctx(tool_name="write_file", autonomy_mode="plan")
        )
        assert ctx.status.value == "denied_by_policy"
        assert "plan" in (ctx.result or "")

    async def test_plan_mode_denies_exec(self):
        ctx = await make_orch().execute(
            make_ctx(tool_name="exec", autonomy_mode="plan")
        )
        assert ctx.status.value == "denied_by_policy"

    async def test_autonomous_skips_write_confirm(self):
        """auto 模式 + write_file → 矩阵为 AUTO（不弹卡直接执行）。

        mock 工具成功返回 → 直接断言 SUCCESS（显式结果，不依赖副作用）。
        """
        ctx = await make_orch().execute(
            make_ctx(tool_name="write_file", autonomy_mode="autonomous")
        )
        assert ctx.status.value == "success"
        assert "written" in (ctx.result or "")


class TestConcurrentEmitterIsolation:
    """P1-4 (审阅): emitter 按 session 隔离——并发会话互不覆盖。"""

    async def test_two_sessions_isolated(self):
        from miqi.agent import user_input_resolver

        seen_a, seen_b = [], []

        async def emit_a(payload):
            seen_a.append(payload)

        async def emit_b(payload):
            seen_b.append(payload)

        user_input_resolver.set_user_input_emitter(emit_a, session_key="sess-a")
        user_input_resolver.set_user_input_emitter(emit_b, session_key="sess-b")

        # 每个会话的 resolver 取到自己的 emitter（互不串流）
        assert user_input_resolver.user_input_emitter("sess-a") is emit_a
        assert user_input_resolver.user_input_emitter("sess-b") is emit_b
        assert user_input_resolver.has_user_input_channel("sess-a")
        assert user_input_resolver.has_user_input_channel("sess-b")

        # 清理：只清 A，B 仍在
        user_input_resolver.set_user_input_emitter(None, session_key="sess-a")
        assert not user_input_resolver.has_user_input_channel("sess-a")
        assert user_input_resolver.has_user_input_channel("sess-b")

        user_input_resolver.set_user_input_emitter(None, session_key="sess-b")


class TestApprovalResolvedSkipsGate:
    """#684-1 (审阅): 已过审批弹窗的调用不再弹 collab 卡（exec 双确认修复）。"""

    async def test_approved_exec_skips_gate(self):
        """审批通过（approval_resolved=True）→ exec 不弹 collab 卡直接执行。"""
        from miqi.agent import user_input_resolver

        called = []

        async def emit(payload):
            called.append(payload)

        user_input_resolver.set_user_input_emitter(emit)
        ctx = make_ctx(tool_name="exec", autonomy_mode="supervised")
        ctx.approval_resolved = True
        ctx = await make_orch().execute(ctx)
        # 无弹卡（called 空）= gate 跳过 ✓；status 不关心（mock sandbox 细节）
        assert called == []

    async def test_unapproved_exec_still_confirms(self):
        """未审批 → exec 在 supervised 模式仍弹 collab 卡。"""
        from miqi.agent import user_input_resolver

        user_input_resolver.set_user_input_emitter(user_click("confirm", "确认执行"))
        ctx = await make_orch().execute(make_ctx(tool_name="exec"))
        assert ctx.status.value == "success"


class TestToolRuntimeRealPath:
    """P0-1 (审阅): 真实构造路径——ToolRuntime.execute_one 从 turn.execution_policy
    透传 autonomy_mode → gate 按模式生效（不手动注入 ctx）。"""

    def _make_runtime(self):
        from miqi.execution.permission_engine import (
            PermissionDecision,
            PermissionVerdict,
        )
        from miqi.execution.orchestrator import ToolOrchestrator
        from miqi.runtime.tool_runtime import ToolRuntime

        pe = MagicMock()
        pe.check = AsyncMock(
            return_value=PermissionDecision(verdict=PermissionVerdict.ALLOW, reason="ok")
        )
        se = MagicMock()
        se.select = AsyncMock(
            return_value=MagicMock(
                sandbox_type="none",
                filesystem_policy=MagicMock(),
                network_policy="allow_all",
            )
        )
        tr = MagicMock()
        tr.get.return_value = MagicMock()
        tr.get.return_value.execute = AsyncMock(return_value="ok: done")
        orch = ToolOrchestrator(
            permission_engine=pe,
            sandbox_engine=se,
            hook_runtime=HookRuntime(),
            tool_registry=tr,
            event_emitter=MagicMock(),
        )
        return ToolRuntime(orchestrator=orch), orch

    async def test_plan_policy_denies_exec_via_real_path(self):
        """turn.execution_policy='plan' → execute_one → exec 被 DENY（不经弹卡）。"""
        runtime, _ = self._make_runtime()
        turn = MagicMock()
        turn.execution_policy = "plan"
        turn.bypass_approval = True
        tool_call = MagicMock()
        tool_call.name = "exec"
        tool_call.id = "call_1"
        tool_call.arguments = {"command": "rm -rf /tmp/x"}
        ctx = await runtime.execute_one(turn, tool_call)
        assert ctx.status.value == "denied_by_policy"

    async def test_auto_policy_skips_gate_via_real_path(self):
        """turn.execution_policy='auto' → execute_one → write_file 直执行（无弹卡）。"""
        runtime, _ = self._make_runtime()
        turn = MagicMock()
        turn.execution_policy = "auto"
        turn.bypass_approval = True
        tool_call = MagicMock()
        tool_call.name = "write_file"
        tool_call.id = "call_2"
        tool_call.arguments = {"path": "/tmp/x.txt", "content": "hi"}
        ctx = await runtime.execute_one(turn, tool_call)
        assert ctx.status.value == "success"
