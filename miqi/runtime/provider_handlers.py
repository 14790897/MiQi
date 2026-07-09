"""Provider handlers for AppServer dispatch.

Phase 35.2: Migrates providers.list, providers.test, and providers.update
from bridge legacy handlers to AppServer async handlers. provider.test
uses the persistent event loop instead of asyncio.run().

Phase 35 hardening: Uses get_bridge_state(registry) for DI instead of
importing miqi.bridge.server directly.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any

from loguru import logger

from miqi.runtime.app_server import AppServerError, get_bridge_state


VERIFICATION_KEY = "providerVerification"
VERIFICATION_STATUSES = {"success", "failed", "unverified"}


def _provider_fingerprint(provider_config: Any) -> str | None:
    """Return a stable fingerprint for provider fields that affect verification."""
    if provider_config is None:
        return None
    payload = {
        "api_key": getattr(provider_config, "api_key", "") or "",
        "api_base": getattr(provider_config, "api_base", None) or "",
        "extra_headers": getattr(provider_config, "extra_headers", None) or {},
    }
    if not any(payload.values()):
        return None
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _provider_verification_store(config: Any) -> dict[str, Any]:
    desktop = getattr(config, "desktop", None)
    if not isinstance(desktop, dict):
        desktop = {}
        config.desktop = desktop
    store = desktop.get(VERIFICATION_KEY)
    if not isinstance(store, dict):
        store = {}
        desktop[VERIFICATION_KEY] = store
    return store


def _set_provider_verification(
    config: Any,
    provider_name: str,
    status: str,
    fingerprint: str | None,
    message: str = "",
) -> None:
    if status not in VERIFICATION_STATUSES:
        status = "unverified"
    store = _provider_verification_store(config)
    store[provider_name] = {
        "status": status,
        "fingerprint": fingerprint or "",
        "checkedAt": datetime.now(timezone.utc).isoformat(),
        "message": message,
    }


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
    verification_store = _provider_verification_store(config)

    providers_out = []
    for spec in PROVIDERS:
        pc = getattr(config.providers, spec.name, None)
        api_key = pc.api_key if pc else None
        hint = None
        if api_key and len(api_key) >= 8:
            hint = api_key[:4] + "…" + api_key[-4:]
        elif api_key:
            hint = "***"
        configured = bool(pc and (pc.api_key or pc.api_base))
        fingerprint = _provider_fingerprint(pc)
        record = verification_store.get(spec.name)
        record_matches = (
            configured
            and fingerprint
            and isinstance(record, dict)
            and record.get("fingerprint") == fingerprint
        )
        if not configured:
            verification_status = "missing"
        elif record_matches and record.get("status") in {"success", "failed"}:
            verification_status = str(record.get("status"))
        else:
            verification_status = "unverified"

        providers_out.append({
            "name": spec.name,
            "display_name": spec.display_name or spec.name.title(),
            "env_key": spec.env_key,
            "provider_type": spec.provider_type,
            "is_gateway": spec.is_gateway,
            "is_local": spec.is_local,
            "default_api_base": spec.default_api_base,
            "configured": configured,
            "api_key_hint": hint,
            "api_base": pc.api_base if pc else None,
            "configured_model": model if model_provider == spec.name else None,
            "verification_status": verification_status,
            "verified_at": record.get("checkedAt") if record_matches else None,
            "verification_message": record.get("message") if record_matches else None,
        })

    return {
        "result": {
            "providers": providers_out,
            "active_model": model,
            "active_provider": model_provider,
        }
    }


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

    from miqi.providers.registry import find_by_name

    spec = find_by_name(provider_name)
    if spec is None:
        raise AppServerError(
            f"Unknown provider: {provider_name}",
            code="NOT_FOUND",
        )

    state = get_bridge_state(registry)
    config = state.load_config()
    pc = getattr(config.providers, provider_name, None)
    explicit_api_key = bool(api_key)
    explicit_api_base = (
        bool(api_base)
        and pc is not None
        and api_base != (pc.api_base or None)
    )
    should_persist_result = not explicit_api_key and not explicit_api_base

    # If no API key provided, read from current saved config
    if not api_key:
        if pc is not None:
            api_key = pc.api_key or ""
            if not api_base:
                api_base = pc.api_base

    if not api_key:
        raise AppServerError(
            "No API key configured — enter one in Edit or save a provider first",
            code="INVALID_PARAMS",
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
        fingerprint = _provider_fingerprint(pc)
        if ok and should_persist_result and fingerprint:
            from miqi.config.loader import save_config
            _set_provider_verification(
                config,
                provider_name,
                "success",
                fingerprint,
                "Connection test succeeded",
            )
            save_config(config)
            state.config = config
        return {"result": {"ok": ok, "model": provider.get_default_model()}}
    except Exception as exc:
        fingerprint = _provider_fingerprint(pc)
        if should_persist_result and fingerprint:
            from miqi.config.loader import save_config
            _set_provider_verification(
                config,
                provider_name,
                "failed",
                fingerprint,
                "Provider test failed",
            )
            save_config(config)
            state.config = config
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
        _set_provider_verification(
            config,
            provider_name,
            "unverified",
            _provider_fingerprint(new_pc),
            "Provider settings changed; test again to verify",
        )

    if model_override:
        config.agents.defaults.model = model_override

    save_config(config)
    state.config = config

    return {"result": {"saved": True, "provider_name": provider_name}}
