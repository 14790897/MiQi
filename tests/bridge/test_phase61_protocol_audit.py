from __future__ import annotations

import pytest


PLAN61_TYPED_METHODS = {
    "initialize",
    "turn/start",
    "turn/interrupt",
    "turn/steer",
    "thread/compact/start",
    "thread/inject_items",
    "thread/shellCommand",
    "command/exec",
    "command/exec/write",
    "command/exec/resize",
    "command/exec/terminate",
    "process/spawn",
    "process/writeStdin",
    "process/resizePty",
    "process/kill",
    "fs/readFile",
    "fs/writeFile",
    "fs/createDirectory",
    "fs/getMetadata",
    "fs/readDirectory",
    "fs/remove",
    "fs/copy",
    "fs/watch",
    "fs/unwatch",
    "fuzzyFileSearch",
    "fuzzyFileSearch/sessionStart",
    "fuzzyFileSearch/sessionUpdate",
    "fuzzyFileSearch/sessionStop",
    "replay.turns",
    "replay.timeline",
    "replay.messages",
}


class _CaptureSend:
    def __init__(self):
        self.messages: list[dict] = []

    def send(self, data: dict) -> None:
        self.messages.append(data)


def _dispatch_legacy(_req_id: str, _method: str, _params: dict) -> None:
    pass


@pytest.mark.asyncio
async def test_phase61_typed_methods_have_explicit_non_legacy_specs():
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()
    catalog = loop.app_server.protocol_catalog()
    by_method = {item["method"]: item for item in catalog["methods"]}

    missing = sorted(PLAN61_TYPED_METHODS - set(by_method))
    assert missing == []

    legacy = sorted(
        method
        for method in PLAN61_TYPED_METHODS
        if by_method[method]["stability"] == "legacy"
    )
    assert legacy == []

    await loop.app_server.stop()


@pytest.mark.asyncio
async def test_phase61_protocol_catalog_has_no_duplicate_methods():
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()
    catalog = loop.app_server.protocol_catalog()
    names = [item["method"] for item in catalog["methods"]]

    assert len(names) == len(set(names))

    await loop.app_server.stop()


@pytest.mark.asyncio
async def test_phase61_protocol_catalog_registered_on_bridge_loop():
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    assert "protocol/catalog" in loop.app_server._methods

    await loop.app_server.stop()
