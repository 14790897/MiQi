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
PROVIDER_TEST_MODELS = {
    "anthropic": "claude-opus-4-5",
    "openai": "gpt-4.1",
    "deepseek": "deepseek-v4-flash",
    "gemini": "gemini-2.5-pro",
    "moonshot": "kimi-k2.5",
    "dashscope": "qwen-max",
    "zhipu": "glm-4",
    "minimax": "MiniMax-M2.7",
    "aihubmix": "claude-opus-4.1",
    "siliconflow": "deepseek-ai/DeepSeek-V3",
    "vllm": "meta-llama/Llama-3.1-8B-Instruct",
    "ollama_local": "llama3.2",
    "ollama_cloud": "gpt-oss:20b-cloud",
    "openrouter": "anthropic/claude-opus-4-5",
    "custom": "default",
}


def _provider_fingerprint(
    provider_config: Any,
    model: str | None = None,
    builtin_state: dict[str, Any] | None = None,
    credential_source: str | None = None,
) -> str | None:
    """Return a stable fingerprint for provider fields that affect verification."""
    if provider_config is None:
        return None
    if credential_source == "builtin" and isinstance(builtin_state, dict) and builtin_state.get("enabled"):
        payload = {
            "credential_source": "builtin",
            "builtin_provider": builtin_state.get("provider") or "",
            "builtin_bundle": builtin_state.get("bundleId") or "",
            "model": model or "",
        }
    else:
        payload = {
            "credential_source": credential_source or "user",
            "api_key": getattr(provider_config, "api_key", "") or "",
            "api_base": getattr(provider_config, "api_base", None) or "",
            "extra_headers": getattr(provider_config, "extra_headers", None) or {},
            "model": model or "",
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


BUILTIN_MODEL_KEY = "builtinModel"
PROVIDER_CREDENTIALS_KEY = "providerCredentials"


def _builtin_model_store(config: Any) -> dict[str, Any]:
    """Get/create the desktop['builtinModel'] state block. Never stores the key."""
    desktop = getattr(config, "desktop", None)
    if not isinstance(desktop, dict):
        desktop = {}
        config.desktop = desktop
    store = desktop.get(BUILTIN_MODEL_KEY)
    if not isinstance(store, dict):
        store = {}
        desktop[BUILTIN_MODEL_KEY] = store
    return store


def _provider_credentials_store(config: Any) -> dict[str, Any]:
    desktop = getattr(config, "desktop", None)
    if not isinstance(desktop, dict):
        desktop = {}
        config.desktop = desktop
    store = desktop.get(PROVIDER_CREDENTIALS_KEY)
    if not isinstance(store, dict):
        store = {}
        desktop[PROVIDER_CREDENTIALS_KEY] = store
    active = store.get("active")
    if not isinstance(active, dict):
        active = {}
        store["active"] = active
    return store


def _active_credential_for_provider(config: Any, provider_name: str) -> str | None:
    desktop = getattr(config, "desktop", None)
    if not isinstance(desktop, dict):
        return None
    store = desktop.get(PROVIDER_CREDENTIALS_KEY)
    if not isinstance(store, dict):
        return None
    active = store.get("active")
    if not isinstance(active, dict):
        return None
    source = active.get(provider_name)
    return source if source in {"user", "builtin"} else None


def _set_active_credential(config: Any, provider_name: str, source: str) -> None:
    if source not in {"user", "builtin"}:
        return
    store = _provider_credentials_store(config)
    store["active"][provider_name] = source


def _effective_credential_source(
    config: Any,
    provider_name: str,
    *,
    configured: bool,
    builtin_unlocked: bool,
) -> str:
    active = _active_credential_for_provider(config, provider_name)
    if active == "builtin" and builtin_unlocked:
        return "builtin"
    if active == "user" and configured:
        return "user"
    if configured:
        return "user"
    if builtin_unlocked:
        return "builtin"
    return "missing"


def _builtin_state_for_provider(config: Any, provider_name: str) -> dict[str, Any] | None:
    desktop = getattr(config, "desktop", None)
    if not isinstance(desktop, dict):
        return None
    state = desktop.get(BUILTIN_MODEL_KEY)
    if not isinstance(state, dict):
        return None
    if not state.get("enabled"):
        return None
    providers = state.get("providers")
    if isinstance(providers, list):
        for item in providers:
            if isinstance(item, dict) and item.get("provider") == provider_name:
                provider_state = dict(item)
                provider_state["bundleId"] = state.get("bundleId")
                provider_state["licenseId"] = state.get("licenseId")
                provider_state["enabled"] = True
                return provider_state
            if item == provider_name:
                return state
    if state.get("provider") == provider_name:
        return state
    return None


def _is_provider_configured(config: Any, spec: Any, pc: Any) -> bool:
    if pc is None:
        return False
    return bool(pc.api_key or pc.api_base)


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
        configured = _is_provider_configured(config, spec, pc)
        builtin_state = _builtin_state_for_provider(config, spec.name)
        builtin_unlocked = bool(builtin_state)
        usable = configured or builtin_unlocked
        credential_source = _effective_credential_source(
            config,
            spec.name,
            configured=configured,
            builtin_unlocked=builtin_unlocked,
        )
        provider_model = model if model_provider == spec.name else PROVIDER_TEST_MODELS.get(spec.name)
        fingerprint = _provider_fingerprint(
            pc,
            provider_model,
            builtin_state,
            credential_source if credential_source != "missing" else None,
        )
        record = verification_store.get(spec.name)
        record_matches = (
            usable
            and fingerprint
            and isinstance(record, dict)
            and record.get("fingerprint") == fingerprint
        )
        if not usable:
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
            "builtin_unlocked": builtin_unlocked,
            "credential_source": credential_source,
            "active_credential": credential_source,
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
    requested_model = str(params.get("model") or "").strip()

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
    test_model = (
        requested_model
        or PROVIDER_TEST_MODELS.get(provider_name)
        or "gpt-4o"
    )
    explicit_api_key = bool(api_key)
    saved_api_base = (pc.api_base if pc is not None else None) or spec.default_api_base or None
    explicit_api_base = bool(api_base) and api_base != saved_api_base
    should_persist_result = not explicit_api_key and not explicit_api_base

    # If no API key provided, read from current saved config
    if not api_key:
        api_key = config.get_api_key(f"{provider_name}/{test_model}") or ""
        if not api_base:
            api_base = config.get_api_base(f"{provider_name}/{test_model}")

    if not api_key:
        raise AppServerError(
            "No API key configured — enter one in Edit or save a provider first",
            code="INVALID_PARAMS",
        )

    if spec.provider_type == "anthropic":
        from miqi.providers.anthropic_provider import AnthropicProvider
        provider = AnthropicProvider(
            api_key=api_key,
            api_base=api_base,
            provider_name=provider_name,
            default_model=test_model,
        )
    elif spec.provider_type == "gemini":
        from miqi.providers.gemini_provider import GeminiProvider
        provider = GeminiProvider(
            api_key=api_key,
            api_base=api_base,
            provider_name=provider_name,
            default_model=test_model,
        )
    else:
        from miqi.providers.openai_provider import OpenAIProvider
        provider = OpenAIProvider(
            api_key=api_key,
            api_base=api_base,
            provider_name=provider_name,
            default_model=test_model,
        )

    try:
        response = await provider.chat(
            messages=[{"role": "user", "content": "Hello, respond with just 'ok'."}],
            model=test_model,
            max_tokens=16,
            temperature=0.0,
        )
        finish_reason = getattr(response, "finish_reason", "stop")
        error_kind = getattr(response, "error_kind", None)
        ok = finish_reason != "error" and not error_kind
        if not ok:
            raise RuntimeError(response.content or "Provider returned an error response")
        builtin_state = _builtin_state_for_provider(config, provider_name)
        credential_source = _effective_credential_source(
            config,
            provider_name,
            configured=_is_provider_configured(config, spec, pc),
            builtin_unlocked=bool(builtin_state),
        )
        fingerprint = _provider_fingerprint(pc, test_model, builtin_state, credential_source)
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
        return {"result": {"ok": ok, "model": test_model}}
    except Exception as exc:
        builtin_state = _builtin_state_for_provider(config, provider_name)
        credential_source = _effective_credential_source(
            config,
            provider_name,
            configured=_is_provider_configured(config, spec, pc),
            builtin_unlocked=bool(builtin_state),
        )
        fingerprint = _provider_fingerprint(pc, test_model, builtin_state, credential_source)
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
    from miqi.providers.registry import find_by_name

    provider_name = params.get("provider_name", "").strip()
    if not provider_name:
        raise AppServerError("provider_name is required", code="INVALID_PARAMS")

    valid_names = set(ProvidersConfig.model_fields.keys())
    if provider_name not in valid_names:
        raise AppServerError(
            f"Unknown provider: {provider_name}", code="INVALID_PARAMS",
        )
    spec = find_by_name(provider_name)

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
        update["api_base"] = str(v) if v else (spec.default_api_base if spec else None)
    if "extra_headers" in params:
        v = params["extra_headers"]
        update["extra_headers"] = dict(v) if v else None

    model_override: str | None = None
    if "model" in params and params["model"]:
        model_override = str(params["model"]).strip()
    credential_source = str(params.get("credential_source") or "").strip()
    if credential_source and credential_source not in {"user", "builtin"}:
        raise AppServerError("credential_source must be user or builtin", code="INVALID_PARAMS")

    if update.get("api_key") and "api_base" not in update and not getattr(pc, "api_base", None):
        default_api_base = spec.default_api_base if spec else ""
        if default_api_base:
            update["api_base"] = default_api_base

    if not update and not model_override and not credential_source:
        raise AppServerError("No fields to update", code="INVALID_PARAMS")

    new_pc = pc
    if update:
        current_dict = pc.model_dump(by_alias=False)
        current_dict.update(update)
        new_pc = ProviderConfig.model_validate(current_dict)
        setattr(config.providers, provider_name, new_pc)
        if "api_key" in update and update["api_key"]:
            credential_source = credential_source or "user"
        _set_provider_verification(
            config,
            provider_name,
            "unverified",
            _provider_fingerprint(new_pc, config.agents.defaults.model, None, "user"),
            "Provider settings changed; test again to verify",
        )

    if credential_source == "builtin" and not _builtin_state_for_provider(config, provider_name):
        raise AppServerError("Built-in credential is not unlocked", code="INVALID_PARAMS")
    if credential_source == "user" and not _is_provider_configured(config, spec, new_pc):
        raise AppServerError("User credential is not configured", code="INVALID_PARAMS")
    if credential_source:
        _set_active_credential(config, provider_name, credential_source)

    if model_override:
        config.agents.defaults.model = model_override

    save_config(config)
    state.config = config

    return {"result": {"saved": True, "provider_name": provider_name}}


async def builtin_model_unlock_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Unlock and enable the bundled internal model credential."""
    from miqi.config.loader import save_config
    from miqi.providers.builtin_credentials import BUILTIN_KEY_PROVIDER

    activation_code = str(params.get("activation_code") or "").strip()
    if not activation_code:
        raise AppServerError("activation_code is required", code="INVALID_PARAMS")

    metadata = BUILTIN_KEY_PROVIDER.unlock(activation_code)
    if not metadata:
        raise AppServerError("Invalid unlock code", code="INVALID_CODE")

    state = get_bridge_state(registry)
    config = state.load_config()
    store = _builtin_model_store(config)
    store.clear()
    store["enabled"] = True
    store["bundleId"] = metadata.get("bundleId")
    store["licenseId"] = metadata.get("licenseId")
    store["label"] = metadata.get("label") or ""
    store["providers"] = metadata.get("providers") or []
    sealed = BUILTIN_KEY_PROVIDER.sealed_credentials()
    if sealed:
        store["sealedCredential"] = sealed

    provider_names = [
        item.get("provider")
        for item in store["providers"]
        if isinstance(item, dict) and item.get("provider")
    ]
    user_key_present = any(
        bool(getattr(getattr(config.providers, name, None), "api_key", ""))
        for name in provider_names
    )
    for name in provider_names:
        _set_active_credential(config, name, "builtin")
    activated_model = False
    default_model = ""
    for item in store["providers"]:
        if isinstance(item, dict):
            default_model = str(item.get("defaultModel") or item.get("default_model") or "").strip()
            if default_model:
                break
    if default_model:
        config.agents.defaults.model = default_model
        activated_model = True
    save_config(config)
    state.config = config

    return {
        "result": {
            "providers": store["providers"],
            "bundleId": store["bundleId"],
            "licenseId": store["licenseId"],
            "label": store["label"],
            "userKeyPresent": user_key_present,
            "activatedModel": activated_model,
            "model": config.agents.defaults.model,
        }
    }
