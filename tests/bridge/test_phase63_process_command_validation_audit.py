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
async def test_command_process_specs_match_typed_request_models():
    from miqi.bridge.loop import BridgeRuntimeLoop
    from miqi.runtime.process_request_models import COMMAND_PROCESS_METHOD_PARAM_MODELS

    loop = BridgeRuntimeLoop(
        send_func=_CaptureSend().send,
        dispatch_legacy_func=_dispatch_legacy,
    )
    await loop._init_app_server()
    catalog = loop.app_server.protocol_catalog()
    by_method = {item["method"]: item for item in catalog["methods"]}

    from miqi.runtime.protocol_model_schema import params_schema_from_model

    failures: list[str] = []
    for method, model in sorted(COMMAND_PROCESS_METHOD_PARAM_MODELS.items()):
        expected = params_schema_from_model(model)
        actual = by_method[method]["paramsSchema"]
        if actual != expected:
            failures.append(f"{method}: catalog paramsSchema does not match typed model")

    assert failures == [], "\n".join(failures)

    await loop.app_server.stop()
