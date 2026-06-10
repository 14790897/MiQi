"""Tests for miqi.protocol.events."""


def test_imports():
    """Verify all event types are importable."""
    from miqi.protocol.events import (  # noqa: F401
        EventSeverity,
        AgentStatus,
    )
