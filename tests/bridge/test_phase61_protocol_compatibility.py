from __future__ import annotations

import pytest


class _CaptureSend:
    def __init__(self):
        self.messages: list[dict] = []

    def send(self, data: dict) -> None:
        self.messages.append(data)


def _dispatch_legacy(_req_id: str, _method: str, _params: dict) -> None:
    pass


@pytest.mark.asyncio
async def test_protocol_catalog_includes_every_registered_method():
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    registered = set(loop.app_server._methods)
    catalog = loop.app_server.protocol_catalog()
    catalog_methods = {item["method"] for item in catalog["methods"]}

    assert registered == catalog_methods

    await loop.app_server.stop()


@pytest.mark.asyncio
async def test_plan61_typed_surface_ratio_is_recorded():
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    catalog = loop.app_server.protocol_catalog()
    typed = [
        item for item in catalog["methods"]
        if item["stability"] != "legacy"
    ]

    assert len(typed) >= 31

    await loop.app_server.stop()


@pytest.mark.asyncio
async def test_protocol_catalog_is_sorted_for_stable_diffs():
    from miqi.bridge.loop import BridgeRuntimeLoop

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()

    names = [item["method"] for item in loop.app_server.protocol_catalog()["methods"]]

    assert names == sorted(names)

    await loop.app_server.stop()
