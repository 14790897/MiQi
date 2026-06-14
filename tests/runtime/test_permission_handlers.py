"""Tests for permission handlers — Phase 35.2.

Validates permissions.get, permissions.update,
permissions.permanent.add, and permissions.permanent.remove
migrated from bridge legacy to AppServer async handlers.
"""

import pytest

from miqi.runtime.app_server import ClientSessionRegistry


# ── permissions.get ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_permissions_get_returns_structure():
    """permissions.get should return known structure with expected keys."""
    from miqi.runtime.permission_handlers import permissions_get_handler

    registry = ClientSessionRegistry()
    result = await permissions_get_handler("req-1", {}, "client-1", None, registry)

    data = result["result"]
    assert "filesystem" in data
    assert "network" in data
    assert "exec_approval" in data
    assert "permanent_allowlist" in data
    assert "deny_patterns" in data
    assert isinstance(data["permanent_allowlist"], list)
    assert isinstance(data["deny_patterns"], list)


# ── permissions.update ────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_permissions_update_returns_saved():
    """permissions.update should return saved: True even without orchestrator."""
    from miqi.runtime.permission_handlers import permissions_update_handler

    registry = ClientSessionRegistry()
    result = await permissions_update_handler(
        "req-1",
        {"config": {"permanent_allowlist": ["npm test"], "deny_patterns": ["rm -rf"]}},
        "client-1", None, registry,
    )
    assert result["result"]["saved"] is True


# ── permissions.permanent.add ─────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_permissions_permanent_add_returns_added():
    """permissions.permanent.add should return added: True when pattern given."""
    from miqi.runtime.permission_handlers import permissions_permanent_add_handler

    registry = ClientSessionRegistry()
    result = await permissions_permanent_add_handler(
        "req-1", {"pattern": "git push"}, "client-1", None, registry,
    )
    assert result["result"]["added"] is True


@pytest.mark.asyncio
async def test_permissions_permanent_add_empty_pattern():
    """permissions.permanent.add with empty pattern returns added: False."""
    from miqi.runtime.permission_handlers import permissions_permanent_add_handler

    registry = ClientSessionRegistry()
    result = await permissions_permanent_add_handler(
        "req-1", {"pattern": ""}, "client-1", None, registry,
    )
    assert result["result"]["added"] is False


# ── permissions.permanent.remove ──────────────────────────────────────────────


@pytest.mark.asyncio
async def test_permissions_permanent_remove_returns_removed():
    """permissions.permanent.remove should return removed: True when pattern given."""
    from miqi.runtime.permission_handlers import permissions_permanent_remove_handler

    registry = ClientSessionRegistry()
    result = await permissions_permanent_remove_handler(
        "req-1", {"pattern": "git push"}, "client-1", None, registry,
    )
    assert result["result"]["removed"] is True


@pytest.mark.asyncio
async def test_permissions_permanent_remove_empty_pattern():
    """permissions.permanent.remove with empty pattern returns removed: False."""
    from miqi.runtime.permission_handlers import permissions_permanent_remove_handler

    registry = ClientSessionRegistry()
    result = await permissions_permanent_remove_handler(
        "req-1", {"pattern": ""}, "client-1", None, registry,
    )
    assert result["result"]["removed"] is False
