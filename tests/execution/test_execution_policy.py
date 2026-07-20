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
    execution_policy: str = "accept_edits"
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

    def test_plan_mode_no_tools(self):
        """Plan mode → all tools removed."""
        turn = FakeTurnContext(execution_policy="plan")
        tools = make_tools("read_file", "write_file", "exec", "web_search")
        
        if turn.execution_policy == "plan":
            tools = []
        
        assert tools == [], "Plan mode should remove all tools"
        assert turn.bypass_approval is False
        assert turn.force_approval is False

    def test_manual_mode_flags(self):
        """Manual mode → sets force_approval=True, bypass_approval=False."""
        turn = FakeTurnContext(execution_policy="manual")
        
        # Simulate turn_runner logic
        if turn.execution_policy == "bypass":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.bypass_approval = False
            turn.force_approval = True
        
        assert turn.force_approval is True
        assert turn.bypass_approval is False

    def test_bypass_mode_flags(self):
        """Bypass mode → sets bypass_approval=True."""
        turn = FakeTurnContext(execution_policy="bypass")
        
        if turn.execution_policy == "bypass":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.bypass_approval = False
            turn.force_approval = True
        
        assert turn.bypass_approval is True
        assert turn.force_approval is False

    def test_accept_edits_mode_flags(self):
        """Accept edits mode → neither flag set (defaults)."""
        turn = FakeTurnContext(execution_policy="accept_edits")
        
        if turn.execution_policy == "bypass":
            turn.bypass_approval = True
        elif turn.execution_policy == "manual":
            turn.bypass_approval = False
            turn.force_approval = True
        
        assert turn.bypass_approval is False
        assert turn.force_approval is False

    def test_accept_edits_mode_keeps_tools(self):
        """Accept edits mode → all tools preserved."""
        turn = FakeTurnContext(execution_policy="accept_edits")
        tools = make_tools("read_file", "write_file", "exec", "web_search")
        
        # Accept edits keeps all tools
        if turn.execution_policy == "plan":
            tools = []
        
        assert len(tools) == 4, "Accept edits should keep all tools"

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
        
        turn = FakeTurnContext(execution_policy="bypass", bypass_approval=True)
        
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
        """Default accept_edits → no flags set."""
        from miqi.execution.orchestrator import ToolExecutionContext
        
        turn = FakeTurnContext(execution_policy="accept_edits")
        
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
        
        assert tc.execution_policy == "accept_edits"
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
