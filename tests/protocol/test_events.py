"""Tests for miqi.protocol.events."""


def test_event_severity_values():
    from miqi.protocol.events import EventSeverity

    assert EventSeverity.INFO.value == "info"
    assert EventSeverity.WARNING.value == "warning"
    assert EventSeverity.ERROR.value == "error"


def test_event_severity_serialization():
    import json
    from miqi.protocol.events import EventSeverity

    assert json.dumps(EventSeverity.INFO) == '"info"'


def test_agent_status_values():
    from miqi.protocol.events import AgentStatus

    assert AgentStatus.IDLE.value == "idle"
    assert AgentStatus.THINKING.value == "thinking"
    assert AgentStatus.EXECUTING.value == "executing"
    assert AgentStatus.WAITING_APPROVAL.value == "waiting_approval"
    assert AgentStatus.COMPLETED.value == "completed"
    assert AgentStatus.ERROR.value == "error"
    assert AgentStatus.ABORTED.value == "aborted"
