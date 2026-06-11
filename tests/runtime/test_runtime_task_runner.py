"""Tests for TaskRunner (Phase 11.3)."""

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

from miqi.protocol.commands import UserMessage, AbortTurn
from miqi.runtime.task_runner import TaskRunner


@pytest.mark.asyncio
async def test_task_runner_routes_user_message_to_turn_runner(fake_services):
    """UserMessage goes through TurnRunner.run, not agent_loop.process_direct."""
    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(UserMessage(content="hello", thread_id="cli:default"))

    # TurnRunner is the new path
    fake_services.turn_runner.run.assert_awaited_once()
    # agent_loop.process_direct should NOT be called
    fake_services.agent_loop.process_direct.assert_not_awaited()

    # Phase 17: TurnStartedEvent is emitted before AgentMessageEvent.
    # Drain past non-content events until we find the final message.
    event = None
    while True:
        ev = await asyncio.wait_for(events.get(), timeout=1)
        if hasattr(ev, "content"):
            event = ev
            break
    assert event.content == "hi there"


@pytest.mark.asyncio
async def test_task_runner_handles_abort_turn(fake_services):
    """AbortTurn signals cancellation event and emits ErrorEvent (Phase 14 follow-up).

    No longer calls agent_loop.stop(). Instead sets the per-thread cancel
    event and emits an ErrorEvent warning.
    """
    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(AbortTurn(thread_id="cli:default"))

    # agent_loop.stop() is no longer called for abort
    fake_services.agent_loop.stop.assert_not_called()

    # Should emit an ErrorEvent (warning about abort)
    event = await asyncio.wait_for(events.get(), timeout=1)
    assert event.__class__.__name__ == "ErrorEvent"
    assert "aborted" in event.message.lower()


@pytest.mark.asyncio
async def test_approval_response_resolves_orchestrator(fake_services):
    """ApprovalResponse resolves the orchestrator's pending approval (Phase 18)."""
    from miqi.protocol.commands import ApprovalResponse
    from miqi.protocol.events import ApprovalResolvedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    seen: dict[str, str] = {}

    def resolve_approval(approval_id: str, decision: str) -> None:
        seen["approval_id"] = approval_id
        seen["decision"] = decision

    fake_services.orchestrator.resolve_approval = resolve_approval
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ApprovalResponse(approval_id="ap-1", decision="allow"))

    # Verify ApprovalResolvedEvent emitted
    event: object | None = None
    while True:
        ev = await asyncio.wait_for(events.get(), timeout=1)
        if isinstance(ev, ApprovalResolvedEvent):
            event = ev
            break

    assert event is not None, "Expected ApprovalResolvedEvent"
    assert event.approval_id == "ap-1"  # type: ignore[union-attr]
    assert event.decision == "allow"  # type: ignore[union-attr]
    assert seen == {"approval_id": "ap-1", "decision": "allow"}


@pytest.mark.asyncio
async def test_task_runner_unknown_submission_command_rejected(fake_services):
    """Unknown submission types emit CommandRejectedEvent (Phase 18)."""
    from miqi.protocol.events import CommandRejectedEvent

    events = asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    class BogusCommand:
        pass

    await runner.handle(BogusCommand())

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert event.recoverable is False


# ---------------------------------------------------------------------------
# Phase 18: ThreadCommand wired to ThreadRuntime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_command_create_emits_thread_created(fake_services):
    """ThreadCommand(action='new') must call ThreadRuntime.create_thread
    and emit ThreadCreatedEvent."""
    from unittest.mock import AsyncMock

    from miqi.protocol.commands import ThreadCommand
    from miqi.protocol.events import ThreadCreatedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    thread = type("Thread", (), {
        "thread_id": "thread-new",
        "title": "New thread",
        "parent_thread_id": None,
    })()

    fake_services.thread_runtime = MagicMock()
    fake_services.thread_runtime.create_thread = AsyncMock(return_value=thread)
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ThreadCommand(
        action="new",
        thread_id="ignored",
        params={"title": "New thread"},
    ))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, ThreadCreatedEvent)
    assert event.thread_id == "thread-new"
    assert event.title == "New thread"


@pytest.mark.asyncio
async def test_thread_command_unknown_action_rejected(fake_services):
    """ThreadCommand with unknown action emits CommandRejectedEvent."""
    from miqi.protocol.commands import ThreadCommand
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.thread_runtime = MagicMock()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ThreadCommand(action="explode", thread_id="t1"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert event.command_type == "ThreadCommand"


# ---------------------------------------------------------------------------
# Phase 18: ConfigUpdate wired to SessionState
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_update_mutates_session_state(fake_services):
    """ConfigUpdate must call SessionState.apply_config_update and emit
    ConfigUpdatedEvent."""
    from miqi.protocol.commands import ConfigUpdate
    from miqi.protocol.events import ConfigUpdatedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.session_state = MagicMock()
    fake_services.session_state.apply_config_update = MagicMock()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ConfigUpdate(path="agents.defaults.temperature", value=0.2))

    fake_services.session_state.apply_config_update.assert_called_once_with(
        "agents.defaults.temperature",
        0.2,
    )
    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, ConfigUpdatedEvent)
    assert event.path == "agents.defaults.temperature"
    assert event.value == 0.2


def test_session_state_rejects_dunder_paths():
    """apply_config_update must reject paths with __ or _private segments."""
    import pytest as _pytest

    from miqi.runtime.session_state import SessionState

    state = SessionState(
        session_id="sess-1",
        workspace=__import__("pathlib").Path("/tmp"),
        active_thread_id="t1",
        config_snapshot=type("C", (), {"agents": type("A", (), {"defaults": type("D", (), {"temperature": 0.1})()})()})(),
    )

    # Valid path
    state.apply_config_update("agents.defaults.temperature", 0.9)
    assert state.config_snapshot.agents.defaults.temperature == 0.9

    # Dunder path
    with _pytest.raises(ValueError, match="dunder.*private"):
        state.apply_config_update("agents.__class__", "bad")

    # Private path
    with _pytest.raises(ValueError, match="dunder.*private"):
        state.apply_config_update("_private.attr", "bad")

    # Nested dunder
    with _pytest.raises(ValueError, match="dunder.*private"):
        state.apply_config_update("agents.defaults.__init__", "bad")

    # Empty path
    with _pytest.raises(ValueError, match="empty"):
        state.apply_config_update("", "bad")

    # Empty segment
    with _pytest.raises(ValueError, match="empty segment"):
        state.apply_config_update("agents..defaults", "bad")


# ---------------------------------------------------------------------------
# Phase 18 hardening: ConfigUpdate failure → CommandRejectedEvent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_config_update_empty_path_rejected(fake_services):
    """ConfigUpdate with empty path emits CommandRejectedEvent, never crashes."""
    from miqi.protocol.commands import ConfigUpdate
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.session_state = MagicMock()
    fake_services.session_state.apply_config_update = MagicMock(
        side_effect=ValueError("Config update path must not be empty"),
    )
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ConfigUpdate(path="", value=42))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert "empty" in event.reason.lower()


@pytest.mark.asyncio
async def test_config_update_missing_attribute_rejected(fake_services):
    """ConfigUpdate targeting a nonexistent attribute emits CommandRejectedEvent."""
    from miqi.protocol.commands import ConfigUpdate
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.session_state = MagicMock()
    fake_services.session_state.apply_config_update = MagicMock(
        side_effect=AttributeError("no such attribute"),
    )
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ConfigUpdate(path="nonexistent.field", value=42))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert "no such attribute" in event.reason


# ---------------------------------------------------------------------------
# Phase 18 hardening: ThreadCommand failure → CommandRejectedEvent
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_thread_command_rename_missing_title_rejected(fake_services):
    """ThreadCommand rename without title emits CommandRejectedEvent."""
    from miqi.protocol.commands import ThreadCommand
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.thread_runtime = MagicMock()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ThreadCommand(
        action="rename",
        thread_id="t1",
        params={},  # missing title
    ))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert "title" in event.reason.lower()


@pytest.mark.asyncio
async def test_thread_command_archive_unknown_thread_rejected(fake_services):
    """ThreadCommand archive on nonexistent thread emits CommandRejectedEvent."""
    from unittest.mock import AsyncMock

    from miqi.protocol.commands import ThreadCommand
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.thread_runtime = MagicMock()
    fake_services.thread_runtime.archive_thread = AsyncMock(
        side_effect=KeyError("thread not found"),
    )
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ThreadCommand(action="archive", thread_id="no-such"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert "thread not found" in event.reason


@pytest.mark.asyncio
async def test_thread_command_fork_unknown_parent_rejected(fake_services):
    """ThreadCommand fork on nonexistent parent emits CommandRejectedEvent."""
    from unittest.mock import AsyncMock

    from miqi.protocol.commands import ThreadCommand
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.thread_runtime = MagicMock()
    fake_services.thread_runtime.fork_thread = AsyncMock(
        side_effect=KeyError("parent thread not found"),
    )
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(ThreadCommand(action="fork", thread_id="no-such"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert "parent thread not found" in event.reason


# ---------------------------------------------------------------------------
# Phase 19: CompactCommand verification
# ---------------------------------------------------------------------------


def test_compact_command_is_submission():
    """CompactCommand exists, has correct type, and is part of Submission."""
    from miqi.protocol.commands import CompactCommand, Submission

    cmd = CompactCommand(thread_id="thread-1")
    assert cmd.type == "compact"
    assert cmd.reason == "manual"


# ---------------------------------------------------------------------------
# Phase 19: CompactCommand wired to ContextRuntime
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_compact_command_emits_context_compacted(fake_services):
    """CompactCommand must call context_runtime.compact_thread and emit
    ContextCompactedEvent (Phase 19)."""
    from unittest.mock import AsyncMock

    from miqi.protocol.commands import CompactCommand
    from miqi.protocol.events import ContextCompactedEvent
    from miqi.runtime.context_runtime import CompactionResult
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.context_runtime.compact_thread = AsyncMock(return_value=CompactionResult(
        thread_id="thread-1",
        messages_before=10,
        messages_after=3,
        tokens_saved=100,
        replacement_messages=[],
    ))
    fake_services.history_runtime = MagicMock()
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(CompactCommand(thread_id="thread-1"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, ContextCompactedEvent)
    assert event.messages_before == 10
    assert event.messages_after == 3
    assert event.tokens_saved == 100
    # Phase 19 follow-up: turn_id must be the compact turn id, not thread_id
    assert event.turn_id != "thread-1"
    assert event.turn_id.startswith("compact-")


@pytest.mark.asyncio
async def test_compact_command_no_runtime_emits_rejected(fake_services):
    """CompactCommand without context_runtime or history_runtime emits
    CommandRejectedEvent."""
    from miqi.protocol.commands import CompactCommand
    from miqi.protocol.events import CommandRejectedEvent
    from miqi.runtime.task_runner import TaskRunner

    events = asyncio.Queue()
    fake_services.context_runtime = None
    fake_services.history_runtime = None
    runner = TaskRunner(services=fake_services, event_queue=events)

    await runner.handle(CompactCommand(thread_id="thread-1"))

    event = await asyncio.wait_for(events.get(), timeout=1)
    assert isinstance(event, CommandRejectedEvent)
    assert event.command_type == "CompactCommand"


@pytest.mark.asyncio
async def test_task_runner_sanitizes_processing_errors(fake_services):
    """Exception messages from turn runner are sanitized, not leaked."""
    import asyncio as _asyncio

    # TurnRunner.run raises with sensitive details
    fake_services.turn_runner.run.side_effect = RuntimeError(
        "secret API key leaked in stack trace"
    )

    events = _asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    from miqi.protocol.commands import UserMessage
    await runner.handle(UserMessage(content="test", thread_id="cli:default"))

    # Phase 17: TurnStartedEvent arrives first, then ErrorEvent.
    # Drain past non-ErrorEvent events.
    event = None
    while True:
        ev = await _asyncio.wait_for(events.get(), timeout=1)
        if ev.__class__.__name__ == "ErrorEvent":
            event = ev
            break
    assert "secret API key" not in event.message
    assert "An internal error occurred" in event.message


# ---------------------------------------------------------------------------
# Phase 13: TaskRunner main path uses CapabilityResolver + PermissionProfile
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_task_runner_attaches_capabilities_and_permission_profile(fake_services):
    """The main UserMessage path must resolve capabilities via CapabilityResolver
    and attach a PermissionProfile to the TurnContext before calling TurnRunner."""
    import asyncio as _asyncio
    from unittest.mock import MagicMock

    from miqi.runtime.capabilities import CapabilityResolver
    from miqi.runtime.task_runner import TaskRunner

    # Create a proper CapabilityResolver
    tool_reg = MagicMock()
    tool_reg.get_definitions.return_value = [
        {"type": "function", "function": {"name": "read_file", "parameters": {}}},
        {"type": "function", "function": {"name": "exec", "parameters": {}}},
    ]
    fake_services.tool_registry = tool_reg

    capability_resolver = CapabilityResolver(
        tool_registry=tool_reg,
        plugin_manager=None,
    )
    fake_services.capability_resolver = capability_resolver

    # Track what turn and tools TurnRunner receives
    captured_turn = None
    captured_tools = None

    async def _capture(**kwargs):
        nonlocal captured_turn, captured_tools
        captured_turn = kwargs.get("turn")
        captured_tools = kwargs.get("tools")
        run_result = MagicMock()
        run_result.final_content = "ok"
        return run_result

    fake_services.turn_runner.run.side_effect = _capture

    events = _asyncio.Queue()
    runner = TaskRunner(services=fake_services, event_queue=events)

    from miqi.protocol.commands import UserMessage
    await runner.handle(UserMessage(content="hello", thread_id="cli:default"))

    # TurnContext should have capabilities attached
    assert captured_turn is not None, "TurnRunner was not called"
    assert captured_turn.capabilities is not None, "turn.capabilities was not set"
    assert len(captured_turn.capabilities.tool_definitions) > 0, (
        "capabilities.tool_definitions should have tools"
    )

    # Tools passed to TurnRunner should come from capability resolver
    assert captured_tools is not None, "tools argument was not passed"
    assert len(captured_tools) > 0, "tools should come from capabilities"
    assert captured_tools == captured_turn.capabilities.tool_definitions

    # TurnContext should have permission_profile
    assert captured_turn.permission_profile is not None, (
        "turn.permission_profile was not set"
    )
    from miqi.runtime.permission_profile import PermissionProfile
    assert isinstance(captured_turn.permission_profile, PermissionProfile)
    assert captured_turn.permission_profile.workspace == fake_services.workspace

    # Phase 17: verify AgentMessageEvent was queued (after TurnStartedEvent)
    event = None
    while True:
        ev = await _asyncio.wait_for(events.get(), timeout=1)
        if hasattr(ev, "content"):
            event = ev
            break
    assert event.content == "ok"
