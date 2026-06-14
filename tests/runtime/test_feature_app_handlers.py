"""Tests for miqi.runtime.feature_app_handlers."""

from __future__ import annotations

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.feature_app_handlers import register_feature_app_handlers


@pytest.mark.asyncio
async def test_experimental_feature_list_shape():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_feature_app_handlers(server)

    response = await server.dispatch(
        "1", "experimentalFeature/list", {}, "client-1", None,
    )
    assert "data" in response["result"]
    assert "nextCursor" in response["result"]
    assert len(response["result"]["data"]) > 0

    first = response["result"]["data"][0]
    assert "key" in first
    assert "stage" in first
    assert "enabled" in first
    assert "defaultEnabled" in first
    assert "displayName" in first
    assert "description" in first
    assert "announcement" in first


@pytest.mark.asyncio
async def test_experimental_feature_list_stable_metadata_null():
    """Stable features must return None for displayName, description, announcement."""
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_feature_app_handlers(server)

    response = await server.dispatch(
        "1", "experimentalFeature/list", {}, "client-1", None,
    )
    stable = [f for f in response["result"]["data"] if f["stage"] == "stable"]
    assert len(stable) > 0
    for row in stable:
        assert row["displayName"] is None, f"{row['key']} displayName must be None"
        assert row["description"] is None, f"{row['key']} description must be None"
        assert row["announcement"] is None, f"{row['key']} announcement must be None"


@pytest.mark.asyncio
async def test_experimental_feature_enablement_set_updates_process_state():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_feature_app_handlers(server)

    # Assert default state
    list_before = await server.dispatch(
        "1", "experimentalFeature/list", {}, "client-1", None,
    )
    desktop_next = next(
        f for f in list_before["result"]["data"] if f["key"] == "desktop.next"
    )
    assert desktop_next["enabled"] is False

    # Enable it
    set_resp = await server.dispatch(
        "2", "experimentalFeature/enablement/set",
        {"features": {"desktop.next": True}}, "client-1", None,
    )
    assert set_resp["result"]["saved"] is True
    assert set_resp["result"]["ignored"] == []

    # Verify state changed
    list_after = await server.dispatch(
        "3", "experimentalFeature/list", {}, "client-1", None,
    )
    desktop_next2 = next(
        f for f in list_after["result"]["data"] if f["key"] == "desktop.next"
    )
    assert desktop_next2["enabled"] is True


@pytest.mark.asyncio
async def test_experimental_feature_enablement_set_ignores_invalid_keys():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_feature_app_handlers(server)

    response = await server.dispatch(
        "1", "experimentalFeature/enablement/set",
        {"features": {"invalid.key": True, "runtime.session": False}},
        "client-1", None,
    )
    assert response["result"]["saved"] is True
    assert "invalid.key" in response["result"]["ignored"]


@pytest.mark.asyncio
async def test_experimental_feature_list_pagination():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_feature_app_handlers(server)

    page1 = await server.dispatch(
        "1", "experimentalFeature/list", {"limit": 3}, "client-1", None,
    )
    assert len(page1["result"]["data"]) == 3
    assert page1["result"]["nextCursor"] is not None

    page2 = await server.dispatch(
        "2", "experimentalFeature/list",
        {"limit": 3, "cursor": page1["result"]["nextCursor"]},
        "client-1", None,
    )
    assert len(page2["result"]["data"]) == 3

    keys1 = {f["key"] for f in page1["result"]["data"]}
    keys2 = {f["key"] for f in page2["result"]["data"]}
    assert keys1.isdisjoint(keys2)
