"""Provider handlers for AppServer dispatch.

Phase 35.2: Migrates providers.list, providers.test, and providers.update
from bridge legacy handlers to AppServer async handlers. provider.test
uses the persistent event loop instead of asyncio.run().

Phase 35 hardening: Uses get_bridge_state(registry) for DI instead of
importing miqi.bridge.server directly.
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError, get_bridge_state


async def providers_list_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """List all configured providers with API key hints.

    Returns provider metadata: name, display_name, env_key, provider_type,
    configured status, api_key hint, default model, etc.
    """
    from miqi.providers.registry import PROVIDERS

    state = get_bridge_state(registry)
    config = state.load_config()
    model = config.agents.defaults.model
    model_provider = config.get_provider_name(model)

    providers_out = []
    for spec in PROVIDERS:
        pc = getattr(config.providers, spec.name, None)
        api_key = pc.api_key if pc else None
        hint = None
        if api_key and len(api_key) >= 8:
            hint = api_key[:4] + "…" + api_key[-4:]
        elif api_key:
            hint = "***"
        providers_out.append({
            "name": spec.name,
            "display_name": spec.display_name or spec.name.title(),
            "env_key": spec.env_key,
            "provider_type": spec.provider_type,
            "is_gateway": spec.is_gateway,
            "is_local": spec.is_local,
            "default_api_base": spec.default_api_base,
            "configured": bool(pc and (pc.api_key or pc.api_base)),
            "api_key_hint": hint,
            "api_base": pc.api_base if pc else None,
            "configured_model": model if model_provider == spec.name else None,
        })

    return {"result": {"providers": providers_out}}


async def providers_test_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Test a provider by making a chat API call.

    Uses the persistent event loop (no asyncio.run()).
    Sanitizes error messages before returning to the frontend.
    """
    provider_name = params.get("provider_name", "")
    api_key = params.get("api_key") or ""
    api_base = params.get("api_base") or None

    if not provider_name:
        raise AppServerError("provider_name is required", code="INVALID_PARAMS")

    # If no API key provided, read from current saved config
    if not api_key:
        config = get_bridge_state(registry).load_config()
        pc = getattr(config.providers, provider_name, None)
        if pc is not None:
            api_key = pc.api_key or ""
            if not api_base:
                api_base = pc.api_base

    if not api_key:
        raise AppServerError(
            "No API key configured — enter one in Edit or save a provider first",
            code="INVALID_PARAMS",
        )

    from miqi.providers.registry import find_by_name

    spec = find_by_name(provider_name)
    if spec is None:
        raise AppServerError(
            f"Unknown provider: {provider_name}",
            code="NOT_FOUND",
        )

    if spec.provider_type == "anthropic":
        from miqi.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(
            api_key=api_key, api_base=api_base, provider_name=provider_name,
        )
    elif spec.provider_type == "gemini":
        from miqi.providers.gemini_provider import GeminiProvider
        provider = GeminiProvider(
            api_key=api_key, api_base=api_base, provider_name=provider_name,
        )
    else:
        from miqi.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider(
            api_key=api_key, api_base=api_base, provider_name=provider_name,
        )

    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": "Hello, respond with just 'ok'."}],
            model=provider.get_default_model(),
            max_tokens=16,
            temperature=0.0,
        )
        ok = response.content is not None and len(response.content) > 0
        return {"result": {"ok": ok, "model": provider.get_default_model()}}
    except Exception as exc:
        # Sanitize: log full details server-side, return sanitized message
        logger.warning(
            "providers.test: provider={} error: {}", provider_name, exc,
        )
        raise AppServerError(
            "Provider test failed — check API key and network",
            code="PROVIDER_ERROR",
        ) from exc


async def providers_update_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Update a single provider's api_key / api_base / extra_headers / model."""
    from miqi.config.loader import save_config
    from miqi.config.schema import ProviderConfig, ProvidersConfig

    provider_name = params.get("provider_name", "").strip()
    if not provider_name:
        raise AppServerError("provider_name is required", code="INVALID_PARAMS")

    valid_names = set(ProvidersConfig.model_fields.keys())
    if provider_name not in valid_names:
        raise AppServerError(
            f"Unknown provider: {provider_name}", code="INVALID_PARAMS",
        )

    state = get_bridge_state(registry)
    config = state.load_config()
    pc = getattr(config.providers, provider_name, None)
    if pc is None:
        raise AppServerError(
            f"Provider config not found: {provider_name}", code="NOT_FOUND",
        )

    update: dict[str, Any] = {}
    if "api_key" in params:
        update["api_key"] = str(params["api_key"])
    if "api_base" in params:
        v = params["api_base"]
        update["api_base"] = str(v) if v else None
    if "extra_headers" in params:
        v = params["extra_headers"]
        update["extra_headers"] = dict(v) if v else None

    model_override: str | None = None
    if "model" in params and params["model"]:
        model_override = str(params["model"]).strip()

    if not update and not model_override:
        raise AppServerError("No fields to update", code="INVALID_PARAMS")

    if update:
        current_dict = pc.model_dump(by_alias=False)
        current_dict.update(update)
        new_pc = ProviderConfig.model_validate(current_dict)
        setattr(config.providers, provider_name, new_pc)

    if model_override:
        config.agents.defaults.model = model_override

    save_config(config)
    state.config = config

    return {"result": {"saved": True, "provider_name": provider_name}}
