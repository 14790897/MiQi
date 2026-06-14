"""Tests for provider handlers — Phase 35.2.

Validates providers.list, providers.test, and providers.update
migrated from bridge legacy to AppServer async handlers.
"""

import pytest


# ── providers.list ────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_providers_list_returns_providers():
    """providers.list should return a list of provider entries with expected shape."""
    from miqi.runtime.provider_handlers import providers_list_handler
    from miqi.runtime.app_server import ClientSessionRegistry

    registry = ClientSessionRegistry()
    result = await providers_list_handler("req-1", {}, "client-1", None, registry)

    providers = result["result"]["providers"]
    assert isinstance(providers, list)
    assert len(providers) > 0, "Expected at least one provider"

    # Verify shape of each entry
    for p in providers:
        assert "name" in p
        assert "display_name" in p
        assert "env_key" in p
        assert "provider_type" in p
        assert "configured" in p
        assert "api_key_hint" in p


@pytest.mark.asyncio
async def test_providers_list_api_key_hint_redacted():
    """Providers list must not leak full API keys."""
    from miqi.runtime.provider_handlers import providers_list_handler
    from miqi.runtime.app_server import ClientSessionRegistry

    registry = ClientSessionRegistry()
    result = await providers_list_handler("req-1", {}, "client-1", None, registry)

    for p in result["result"]["providers"]:
        hint = p.get("api_key_hint") or ""
        # If there is a hint, it should be redacted (no long raw key)
        if hint and hint not in ("***", "None", None):
            assert "…" in hint or len(hint) < 16, (
                f"api_key_hint for {p['name']} looks like a full key: {hint}"
            )


# ── providers.test ───────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_providers_test_missing_provider_name():
    """providers.test should reject empty provider_name."""
    from miqi.runtime.provider_handlers import providers_test_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="provider_name is required"):
        await providers_test_handler("req-1", {}, "client-1", None, registry)


@pytest.mark.asyncio
async def test_providers_test_unknown_provider():
    """providers.test should reject unknown provider names."""
    from miqi.runtime.provider_handlers import providers_test_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="Unknown provider"):
        await providers_test_handler(
            "req-1",
            {"provider_name": "nonexistent-xyz-123", "api_key": "sk-test-key"},
            "client-1", None, registry,
        )


@pytest.mark.asyncio
async def test_providers_test_no_api_key():
    """providers.test should reject missing API key (when not in config)."""
    from miqi.runtime.provider_handlers import providers_test_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="No API key configured"):
        await providers_test_handler(
            "req-1",
            {"provider_name": "anthropic"},
            "client-1", None, registry,
        )


# ── providers.update ──────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_providers_update_missing_provider_name():
    """providers.update should reject empty provider_name."""
    from miqi.runtime.provider_handlers import providers_update_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="provider_name is required"):
        await providers_update_handler("req-1", {}, "client-1", None, registry)


@pytest.mark.asyncio
async def test_providers_update_unknown_provider():
    """providers.update should reject unknown provider names."""
    from miqi.runtime.provider_handlers import providers_update_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="Unknown provider"):
        await providers_update_handler(
            "req-1",
            {"provider_name": "nonexistent-xyz-123"},
            "client-1", None, registry,
        )


@pytest.mark.asyncio
async def test_providers_update_no_fields():
    """providers.update should reject request with no update fields."""
    from miqi.runtime.provider_handlers import providers_update_handler
    from miqi.runtime.app_server import AppServerError, ClientSessionRegistry

    registry = ClientSessionRegistry()
    with pytest.raises(AppServerError, match="No fields to update"):
        await providers_update_handler(
            "req-1",
            {"provider_name": "openai"},
            "client-1", None, registry,
        )
