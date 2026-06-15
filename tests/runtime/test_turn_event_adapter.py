"""Tests for projecting MiQi runtime events into Codex turn/item events."""

from __future__ import annotations


def test_adapter_projects_turn_started_and_user_message_item():
    from miqi.protocol.events import TurnStartedEvent
    from miqi.runtime.turn_event_adapter import CodexTurnEventAdapter

    adapter = CodexTurnEventAdapter(
        thread_id="thread-1",
        turn_id="turn-1",
        input_items=[{"type": "text", "text": "hello"}],
        client_user_message_id="client-msg-1",
    )

    events = adapter.project(TurnStartedEvent(
        turn_id="turn-1",
        thread_id="thread-1",
        agent_name="main",
    ))

    assert [e["event"] for e in events] == [
        "turn/started",
        "item/started",
        "item/completed",
    ]
    assert events[0]["data"]["turn"]["status"] == "inProgress"
    assert events[1]["data"]["item"]["type"] == "userMessage"
    assert events[1]["data"]["item"]["clientId"] == "client-msg-1"


def test_adapter_projects_agent_delta_and_completion():
    from miqi.protocol.events import AgentMessageDeltaEvent, AgentMessageEvent
    from miqi.runtime.turn_event_adapter import CodexTurnEventAdapter

    adapter = CodexTurnEventAdapter(
        thread_id="thread-1",
        turn_id="turn-1",
        input_items=[{"type": "text", "text": "hello"}],
        client_user_message_id=None,
    )

    delta_events = adapter.project(AgentMessageDeltaEvent(
        turn_id="turn-1",
        delta="hel",
        index=0,
    ))
    done_events = adapter.project(AgentMessageEvent(
        turn_id="turn-1",
        content="hello",
    ))

    assert [e["event"] for e in delta_events] == [
        "item/started",
        "item/agentMessage/delta",
    ]
    assert delta_events[0]["data"]["item"]["type"] == "agentMessage"
    assert delta_events[1]["data"]["itemId"] == "turn-1:agent"
    assert done_events[-1]["event"] == "item/completed"
    assert done_events[-1]["data"]["item"]["text"] == "hello"


def test_adapter_projects_exec_command_lifecycle():
    from miqi.protocol.events import (
        ExecCommandBeginEvent,
        ExecCommandEndEvent,
        ExecCommandOutputDeltaEvent,
    )
    from miqi.runtime.turn_event_adapter import CodexTurnEventAdapter

    adapter = CodexTurnEventAdapter(
        thread_id="thread-1",
        turn_id="turn-1",
        input_items=[{"type": "text", "text": "run"}],
        client_user_message_id=None,
    )

    begin = adapter.project(ExecCommandBeginEvent(
        turn_id="turn-1",
        tool_call_id="exec-1",
        command="echo hello",
        cwd="/tmp",
        sandbox_type="none",
    ))
    delta = adapter.project(ExecCommandOutputDeltaEvent(
        turn_id="turn-1",
        tool_call_id="exec-1",
        stream="stdout",
        delta="hello\n",
    ))
    end = adapter.project(ExecCommandEndEvent(
        turn_id="turn-1",
        tool_call_id="exec-1",
        exit_code=0,
        duration_ms=12,
        output_size=6,
    ))

    assert begin[0]["event"] == "item/started"
    assert begin[0]["data"]["item"]["type"] == "commandExecution"
    assert delta[0]["event"] == "item/commandExecution/outputDelta"
    assert delta[0]["data"]["stream"] == "stdout"
    assert end[0]["event"] == "item/completed"
    assert end[0]["data"]["item"]["status"] == "completed"
    assert end[0]["data"]["item"]["aggregatedOutput"] == "hello\n"


def test_adapter_projects_turn_complete_after_agent_item():
    from miqi.protocol.events import TurnCompleteEvent
    from miqi.runtime.turn_event_adapter import CodexTurnEventAdapter

    adapter = CodexTurnEventAdapter(
        thread_id="thread-1",
        turn_id="turn-1",
        input_items=[{"type": "text", "text": "hello"}],
        client_user_message_id=None,
    )

    events = adapter.project(TurnCompleteEvent(
        turn_id="turn-1",
        thread_id="thread-1",
        outcome="success",
        token_usage={"total_tokens": 10},
    ))

    assert events[-2]["event"] == "thread/tokenUsage/updated"
    assert events[-1]["event"] == "turn/completed"
    assert events[-1]["data"]["turn"]["status"] == "completed"
