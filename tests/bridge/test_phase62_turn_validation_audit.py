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
async def test_turn_protocol_specs_match_typed_request_models():
    from miqi.bridge.loop import BridgeRuntimeLoop
    from miqi.runtime.turn_request_models import (
        TURN_METHOD_PARAM_MODELS,
        required_fields_for_model,
    )

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()
    catalog = loop.app_server.protocol_catalog()
    by_method = {item["method"]: item for item in catalog["methods"]}

    failures: list[str] = []
    for method, model in sorted(TURN_METHOD_PARAM_MODELS.items()):
        expected = required_fields_for_model(model)
        actual = sorted(by_method[method]["paramsSchema"].get("required", []))
        if actual != expected:
            failures.append(f"{method}: catalog={actual}, model={expected}")

    assert failures == [], "\n".join(failures)

    await loop.app_server.stop()
