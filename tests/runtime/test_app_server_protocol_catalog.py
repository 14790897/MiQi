from __future__ import annotations

import pytest

from miqi.runtime.app_server import AppServer, ClientSessionRegistry
from miqi.runtime.protocol_registry import MethodScope, MethodStability, ProtocolMethodSpec


async def _handler(request_id, params, client_id, session_id, registry):
    return {"result": {"ok": True}}


@pytest.mark.asyncio
async def test_register_method_accepts_explicit_spec():
    server = AppServer(ClientSessionRegistry())
    spec = ProtocolMethodSpec(
        method="turn/start",
        stability=MethodStability.STABLE,
        scope=MethodScope.TURN,
    )

    server.register_method("turn/start", _handler, spec=spec)

    catalog = server.protocol_catalog()
    by_method = {item["method"]: item for item in catalog["methods"]}
    assert by_method["turn/start"]["method"] == "turn/start"
    assert by_method["turn/start"]["stability"] == "stable"
    await server.stop()


@pytest.mark.asyncio
async def test_register_method_without_spec_creates_legacy_placeholder():
    server = AppServer(ClientSessionRegistry())

    server.register_method("legacy.method", _handler)

    catalog = server.protocol_catalog()
    by_method = {item["method"]: item for item in catalog["methods"]}
    assert by_method["legacy.method"]["method"] == "legacy.method"
    assert by_method["legacy.method"]["stability"] == "legacy"
    await server.stop()


@pytest.mark.asyncio
async def test_register_method_rejects_mismatched_spec_name():
    server = AppServer(ClientSessionRegistry())
    spec = ProtocolMethodSpec(
        method="turn/start",
        stability=MethodStability.STABLE,
        scope=MethodScope.TURN,
    )

    with pytest.raises(ValueError):
        server.register_method("turn/steer", _handler, spec=spec)

    await server.stop()


@pytest.mark.asyncio
async def test_protocol_catalog_method_returns_catalog():
    server = AppServer(ClientSessionRegistry())

    response = await server.dispatch(
        "req-1",
        "protocol/catalog",
        {},
        "client-1",
        None,
    )

    assert response["result"]["version"] == 1
    methods = {item["method"] for item in response["result"]["methods"]}
    assert "protocol/catalog" in methods
    await server.stop()
