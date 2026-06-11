"""Tests for exec lifecycle events (Phase 21)."""

import pytest

from miqi.agent.tools.shell import ExecTool
from miqi.protocol.events import ExecCommandBeginEvent, ExecCommandEndEvent


class _EventCollector:
    """Collects emitted events for assertion."""

    def __init__(self):
        self.events: list = []

    async def emit(self, event):
        self.events.append(event)


@pytest.mark.asyncio
async def test_exec_tool_emits_begin_and_end(tmp_path):
    """ExecTool must emit ExecCommandBeginEvent before execution and
    ExecCommandEndEvent after execution when _event_emitter is passed."""
    emitter = _EventCollector()
    tool = ExecTool(timeout=5, working_dir=str(tmp_path))

    output = await tool.execute(
        "python -c \"print('hello')\"",
        _event_emitter=emitter,
        _turn_id="turn-1",
        _tool_call_id="tc-1",
    )

    assert "hello" in output, f"Expected 'hello' in output: {output!r}"

    begin_events = [e for e in emitter.events if isinstance(e, ExecCommandBeginEvent)]
    end_events = [e for e in emitter.events if isinstance(e, ExecCommandEndEvent)]

    assert len(begin_events) == 1, f"Should emit 1 begin event: {emitter.events}"
    assert len(end_events) == 1, f"Should emit 1 end event: {emitter.events}"

    assert begin_events[0].turn_id == "turn-1"
    assert begin_events[0].tool_call_id == "tc-1"
    assert "python" in begin_events[0].command

    assert end_events[0].turn_id == "turn-1"
    assert end_events[0].tool_call_id == "tc-1"
    assert end_events[0].output_size > 0
