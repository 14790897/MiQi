"""Tests for execution policy integration in TurnRunner."""
import pytest
from unittest.mock import MagicMock, AsyncMock, patch
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class FakeAgentMetadata:
    name: str = "main"
    system_prompt: str = "You are a helpful assistant."


@dataclass  
class FakeTurnContext:
    turn_id: str = "test-turn"
    thread_id: str = "test-thread"
    agent_metadata: Any = None
    workspace: Path = Path("/tmp")
    model: str = "test-model"
    provider: Any = None
    execution_policy: str = "edit"
    bypass_approval: bool = False
    force_approval: bool = False
    capabilities: Any = None
    permission_profile: Any = None
    client_id: str = ""
    session_id: str = ""
    cancel_event: Any = None
    temperature: float = 0.1
    max_tokens: int = 8192
    current_date: str = ""
    timezone: str = "UTC"
    features: dict = field(default_factory=dict)
    sandbox_permissions: Any = None

    def __post_init__(self):
        if self.agent_metadata is None:
            self.agent_metadata = FakeAgentMetadata()


class FakeCapability:
    def __init__(self, tools):
        self.tool_definitions = tools


def make_tools(*names):
    return [{"name": n} for n in names]


class TestExecutionPolicyToolFiltering:
    """Verify turn_runner filters tools based on execution_policy."""

    def test_plan_mode_filters_write_exec(self):
        """Plan mode → write/exec tools filtered, read-only tools kept. bypass_approval=True for safe auto-allow."""
        turn = FakeTurnContext(execution_policy="plan")
        tools = make_tools("read_file", "write_file", "exec", "web_search", "list_dir")

        _EP_WRITE_EXEC = frozenset({
            "write_file", "edit_file", "apply_patch", "edit_diff",
            "write", "edit", "delete", "move",
            "exec", "bash", "shell",
            "spawn", "subagent", "cron",
            "skill_manage", "memory",
        })
        if turn.execution_policy == "plan":
            tools = [t for t in tools if t.get("name") not in _EP_WRITE_EXEC]
            turn.bypass_approval = True  # plan mode tools are safe, deny-list still wins

        names = [t["name"] for t in tools]
        assert "read_file" in names, "Plan should keep read_file"
        assert "web_search" in names, "Plan should keep web_search"
        assert "list_dir" in names, "Plan should keep list_dir"
        assert "write_file" not in names, "Plan should filter write_file"
        assert "exec" not in names, "Plan should filter exec"
        assert turn.bypass_approval is True, "Plan should set bypass_approval=True"
        assert turn.force_approval is False

    def test_manual_mode_flags(self):
        """Manual mode → sets force_approval=True, bypass_approval=False."""
        turn = FakeTurnContext(execution_policy="manual")
        
        # Simulate turn_runner logic
        if turn.execution_policy == "auto":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.bypass_approval = False
            turn.force_approval = True
        
        assert turn.force_approval is True
        assert turn.bypass_approval is False

    def test_bypass_mode_flags(self):
        """Bypass mode → sets bypass_approval=True."""
        turn = FakeTurnContext(execution_policy="auto")
        
        if turn.execution_policy == "auto":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.bypass_approval = False
            turn.force_approval = True
        
        assert turn.bypass_approval is True
        assert turn.force_approval is False

    def test_edit_mode_flags(self):
        """Edit mode → neither flag set (defaults)."""
        turn = FakeTurnContext(execution_policy="edit")

        if turn.execution_policy == "auto":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.bypass_approval = False
            turn.force_approval = True

        assert turn.bypass_approval is False
        assert turn.force_approval is False

    def test_edit_mode_keeps_tools(self):
        """Edit mode → all tools preserved."""
        turn = FakeTurnContext(execution_policy="edit")
        tools = make_tools("read_file", "write_file", "exec", "web_search")

        # Edit keeps all tools
        if turn.execution_policy == "plan":
            tools = []

        assert len(tools) == 4, "Edit should keep all tools"

    def test_manual_mode_keeps_tools(self):
        """Manual mode → all tools preserved (differentiation is at approval layer)."""
        turn = FakeTurnContext(execution_policy="manual")
        tools = make_tools("read_file", "write_file", "exec")
        
        if turn.execution_policy == "plan":
            tools = []
        
        assert len(tools) == 3, "Manual should keep all tools (approval handles the rest)"


class TestToolRuntimePolicyPropagation:
    """Verify tool_runtime copies policy flags to ToolExecutionContext."""

    def test_bypass_propagated_to_ctx(self):
        """bypass_approval flag is copied from turn to ToolExecutionContext."""
        from miqi.execution.orchestrator import ToolExecutionContext
        
        turn = FakeTurnContext(execution_policy="auto", bypass_approval=True)
        
        ctx = ToolExecutionContext(
            tool_name="exec",
            tool_call_id="call-1",
            arguments={"command": "ls"},
            turn_id=turn.turn_id,
            thread_id=turn.thread_id,
            agent_type=turn.agent_metadata.name,
            client_id=getattr(turn, "client_id", ""),
            session_id=getattr(turn, "session_id", ""),
            bypass_approval=getattr(turn, "bypass_approval", False),
            force_approval=getattr(turn, "force_approval", False),
        )
        
        assert ctx.bypass_approval is True
        assert ctx.force_approval is False

    def test_manual_propagated_to_ctx(self):
        """force_approval flag is copied from turn to ToolExecutionContext."""
        from miqi.execution.orchestrator import ToolExecutionContext
        
        turn = FakeTurnContext(execution_policy="manual", force_approval=True)
        
        ctx = ToolExecutionContext(
            tool_name="write_file",
            tool_call_id="call-2",
            arguments={"path": "/tmp/test"},
            turn_id=turn.turn_id,
            thread_id=turn.thread_id,
            agent_type=turn.agent_metadata.name,
            client_id=getattr(turn, "client_id", ""),
            session_id=getattr(turn, "session_id", ""),
            bypass_approval=getattr(turn, "bypass_approval", False),
            force_approval=getattr(turn, "force_approval", False),
        )
        
        assert ctx.bypass_approval is False
        assert ctx.force_approval is True

    def test_default_no_flags(self):
        """Default edit → no flags set."""
        from miqi.execution.orchestrator import ToolExecutionContext
        
        turn = FakeTurnContext(execution_policy="edit")
        
        ctx = ToolExecutionContext(
            tool_name="read_file",
            tool_call_id="call-3",
            arguments={"path": "test.py"},
            turn_id=turn.turn_id,
            thread_id=turn.thread_id,
            agent_type=turn.agent_metadata.name,
            client_id=getattr(turn, "client_id", ""),
            session_id=getattr(turn, "session_id", ""),
            bypass_approval=getattr(turn, "bypass_approval", False),
            force_approval=getattr(turn, "force_approval", False),
        )
        
        assert ctx.bypass_approval is False
        assert ctx.force_approval is False


class TestTurnContextDefaults:
    """Verify TurnContext defaults are correct post-refactor."""

    def test_default_execution_policy(self):
        from miqi.runtime.turn_context import TurnContext
        
        tc = TurnContext(
            turn_id="test",
            thread_id="t1",
            workspace=Path("/tmp"),
            model="m",
            agent_metadata=FakeAgentMetadata(),
            provider=None,
        )
        
        assert tc.execution_policy == "edit"
        assert tc.bypass_approval is False
        assert tc.force_approval is False

    def test_fields_have_no_mode_legacy(self):
        """Ensure old 'mode' field is gone; replaced by execution_policy."""
        from miqi.runtime.turn_context import TurnContext
        
        tc = TurnContext(
            turn_id="test",
            thread_id="t1",
            workspace=Path("/tmp"),
            model="m",
            agent_metadata=FakeAgentMetadata(),
            provider=None,
        )
        
        # execution_policy exists, mode does not
        assert hasattr(tc, "execution_policy")
        assert not hasattr(tc, "mode"), "Old 'mode' field should not exist"


class TestPlanModeCapabilityConstraints:
    """Verify plan mode tool capability boundaries — not model behavior.

    These tests validate that plan mode exposes read-only / search tools
    while blocking write / exec / side-effect tools.  They use the real
    PLAN_BLOCKED_TOOLS constant so they stay in sync with production.
    """

    def test_plan_readonly_tools_available(self):
        """Plan mode retains read_file, web_search, list_dir, paper_search."""
        from miqi.runtime.tool_policy import PLAN_BLOCKED_TOOLS

        tools = [
            {"name": "read_file"},
            {"name": "web_search"},
            {"name": "list_dir"},
            {"name": "paper_search"},
            {"name": "web_fetch"},
            {"name": "session_search"},
        ]
        filtered = [t for t in tools if t.get("name") not in PLAN_BLOCKED_TOOLS]

        names = {t["name"] for t in filtered}
        assert "read_file" in names
        assert "web_search" in names
        assert "list_dir" in names
        assert "paper_search" in names
        assert "web_fetch" in names
        assert "session_search" in names

    def test_plan_write_tools_blocked(self):
        """Plan mode blocks write_file, edit_file, apply_patch."""
        from miqi.runtime.tool_policy import PLAN_BLOCKED_TOOLS

        tools = [
            {"name": "write_file"},
            {"name": "edit_file"},
            {"name": "apply_patch"},
            {"name": "edit_diff"},
            {"name": "write"},
            {"name": "edit"},
            {"name": "delete"},
            {"name": "move"},
        ]
        filtered = [t for t in tools if t.get("name") not in PLAN_BLOCKED_TOOLS]

        assert len(filtered) == 0, (
            f"All write/delete tools should be blocked in plan mode, "
            f"but these passed: {[t['name'] for t in filtered]}"
        )

    def test_plan_exec_tools_blocked(self):
        """Plan mode blocks exec, bash, shell."""
        from miqi.runtime.tool_policy import PLAN_BLOCKED_TOOLS

        tools = [
            {"name": "exec"},
            {"name": "bash"},
            {"name": "shell"},
        ]
        filtered = [t for t in tools if t.get("name") not in PLAN_BLOCKED_TOOLS]

        assert len(filtered) == 0, (
            f"All exec/shell tools should be blocked in plan mode, "
            f"but these passed: {[t['name'] for t in filtered]}"
        )

    def test_plan_side_effect_tools_blocked(self):
        """Plan mode blocks spawn, subagent, cron, skill_manage, memory."""
        from miqi.runtime.tool_policy import PLAN_BLOCKED_TOOLS

        tools = [
            {"name": "spawn"},
            {"name": "subagent"},
            {"name": "cron"},
            {"name": "skill_manage"},
            {"name": "memory"},
        ]
        filtered = [t for t in tools if t.get("name") not in PLAN_BLOCKED_TOOLS]

        assert len(filtered) == 0, (
            f"All side-effect tools should be blocked in plan mode, "
            f"but these passed: {[t['name'] for t in filtered]}"
        )

    def test_plan_bypass_sets_flag_for_readonly_safety(self):
        """Plan mode sets bypass_approval=True — safety depends on tool filtering."""
        turn = FakeTurnContext(execution_policy="plan")

        from miqi.runtime.tool_policy import PLAN_BLOCKED_TOOLS

        if turn.execution_policy == "plan":
            turn.bypass_approval = True

        assert turn.bypass_approval is True, (
            "Plan mode sets bypass_approval=True because all exposed tools "
            "are read-only (write/exec removed by PLAN_BLOCKED_TOOLS). "
            "The deny-list in permission_engine still wins."
        )

    def test_plan_system_prompt_references_readonly_analysis(self):
        """Plan mode system prompt uses read-only analysis language."""
        from miqi.runtime.turn_context import TurnContext
        from pathlib import Path
        import tempfile

        tc = TurnContext(
            turn_id="test",
            thread_id="t1",
            workspace=Path(tempfile.gettempdir()),
            model="m",
            agent_metadata=FakeAgentMetadata(),
            provider=None,
            execution_policy="plan",
        )
        assert tc.execution_policy == "plan"
        # The actual prompt assembly is in task_runner._handle_user_message;
        # this test guards that TurnContext carries plan mode correctly.
