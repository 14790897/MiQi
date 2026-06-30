"""Tests for miqi.runtime.permission_profile_app_handlers."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.permission_profile_app_handlers import (
    register_permission_profile_app_handlers,
)


@pytest.mark.asyncio
async def test_permission_profile_list_shape():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_permission_profile_app_handlers(server)

    response = await server.dispatch(
        "1", "permissionProfile/list", {}, "client-1", None,
    )
    assert "data" in response["result"]
    assert "nextCursor" in response["result"]
    assert len(response["result"]["data"]) == 3

    first = response["result"]["data"][0]
    assert "id" in first
    assert "description" in first
    assert "source" in first


@pytest.mark.asyncio
async def test_permission_profile_list_pagination():
    registry = ClientSessionRegistry()
    server = AppServer(registry)
    register_permission_profile_app_handlers(server)

    page1 = await server.dispatch(
        "1", "permissionProfile/list", {"limit": 2}, "client-1", None,
    )
    assert len(page1["result"]["data"]) == 2
    assert page1["result"]["nextCursor"] is not None

    page2 = await server.dispatch(
        "2", "permissionProfile/list",
        {"limit": 2, "cursor": page1["result"]["nextCursor"]},
        "client-1", None,
    )
    assert len(page2["result"]["data"]) == 1

    ids1 = {p["id"] for p in page1["result"]["data"]}
    ids2 = {p["id"] for p in page2["result"]["data"]}
    assert ids1.isdisjoint(ids2)


@pytest.mark.asyncio
async def test_permission_profile_list_rejects_cwd_outside_workspace(tmp_path):
    from miqi.runtime.permission_profile_app_handlers import (
        register_permission_profile_app_handlers,
    )

    workspace = tmp_path / "workspace"
    workspace.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()

    registry = ClientSessionRegistry()
    state = MagicMock()
    cfg = MagicMock()
    cfg.workspace_path = workspace
    state.load_config.return_value = cfg
    registry.bridge_context["state"] = state
    server = AppServer(registry)
    register_permission_profile_app_handlers(server)

    response = await server.dispatch(
        "1", "permissionProfile/list",
        {"cwd": str(outside)}, "client-1", None,
    )
    assert response.get("code") == "INVALID_PARAMS"
    assert "outside workspace" in response.get("error", "")
