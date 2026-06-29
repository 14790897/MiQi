"""Tests for CLI one-shot via RuntimeSession (Phase 11.4)."""

import pytest


@pytest.mark.asyncio
async def test_cli_one_shot_uses_runtime_session(fake_config, fake_provider):
    """CLI one-shot returns result from RuntimeSession."""
    from miqi.cli.agent_cmd import _run_agent_once_via_runtime

    result = await _run_agent_once_via_runtime(
        fake_config,
        fake_provider,
        "hello",
        "cli:default",
    )

    assert result == "done"
