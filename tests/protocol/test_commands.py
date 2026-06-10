"""Tests for miqi.protocol.commands."""


def test_imports():
    from miqi.protocol.commands import (  # noqa: F401
        UserMessage,
        ApprovalResponse,
        AbortTurn,
    )
