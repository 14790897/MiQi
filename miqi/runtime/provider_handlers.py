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


def _provider_fingerprint(provider_config: Any, model: str | None = None) -> str | None:
    """Return a stable fingerprint for provider fields that affect verification."""
    if provider_config is None:
        return None
    payload = {
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
    activation_store = _provider_activation_store(config)

    providers_out = []
    for spec in PROVIDERS:
        pc = getattr(config.providers, spec.name, None)
        api_key = pc.api_key if pc else None
        hint = None
        builtin_available = spec.name in _BUILTIN_PROVIDERS
        entry = activation_store.get(spec.name, {})
        if isinstance(entry, bool):
            builtin_activated = entry  # old format: {"deepseek": true}
        else:
            builtin_activated = bool(entry.get("builtin", False))
        if builtin_activated:
            # Hide the real key from the frontend for built-in activations
            hint = "企业共享密钥"
        elif api_key and len(api_key) >= 8:
            hint = api_key[:4] + "…" + api_key[-4:]
        elif api_key:
            hint = "***"
        configured = bool(pc and (pc.api_key or pc.api_base))
        provider_model = model if model_provider == spec.name else PROVIDER_TEST_MODELS.get(spec.name)
        fingerprint = _provider_fingerprint(pc, provider_model)
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
            "builtin_available": builtin_available,
            "builtin_activated": builtin_activated,
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
        fingerprint = _provider_fingerprint(pc, test_model)
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
        fingerprint = _provider_fingerprint(pc, test_model)
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

    if update.get("api_key") and "api_base" not in update and not getattr(pc, "api_base", None):
        default_api_base = spec.default_api_base if spec else ""
        if default_api_base:
            update["api_base"] = default_api_base

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
            _provider_fingerprint(new_pc, config.agents.defaults.model),
            "Provider settings changed; test again to verify",
        )
        # When user explicitly provides an API key (including empty to clear
        # built-in activation), clear the built-in activation flag so the UI
        # defaults to "own key" next time.
        if "api_key" in update:
            activation_store = _provider_activation_store(config)
            activation_store.pop(provider_name, None)

    if model_override:
        config.agents.defaults.model = model_override

    save_config(config)
    state.config = config

    return {"result": {"saved": True, "provider_name": provider_name}}


# ---------------------------------------------------------------------------
# Built-in credential: activation code → decrypt embedded API key
# ---------------------------------------------------------------------------

# Providers that support built-in (enterprise shared) keys
_BUILTIN_PROVIDERS = {"deepseek"}

# Encrypted API key for DeepSeek internal testing.
# Token generated via Fernet with activation-code-derived key.
_BUILTIN_KEYS: dict[str, str] = {"deepseek": "gAAAAABqVvj-NrrD9IWE4hrbCvexuygd09CeYtOWuflv1ATJm-vaoBENzFakFX1tRQpX4jYshKb3pcc38wdO-faRSC4NSaZXm0C-Q4e8AdKO0u0oLyJhy0ppimff7Q7DHYRMseC31Gi0"}  # provider_name → encrypted_key

# Default activation code — the company name / internal code
_DEFAULT_ACTIVATION_CODE = "weiguanjiyuan5g"


def _get_fernet() -> Any:
    """Get Fernet instance for the built-in key encryption."""
    from cryptography.fernet import Fernet
    # Derive a Fernet key from the activation code (for MVP)
    import base64
    import hashlib
    digest = hashlib.sha256(_DEFAULT_ACTIVATION_CODE.encode()).digest()
    key = base64.urlsafe_b64encode(digest)
    return Fernet(key)


def _decrypt_builtin_key(provider_name: str) -> str | None:
    """Decrypt the built-in API key for a provider. Returns None if not configured."""
    token = _BUILTIN_KEYS.get(provider_name)
    if not token:
        return None
    try:
        fernet = _get_fernet()
        return fernet.decrypt(token.encode()).decode()
    except Exception:
        return None


async def providers_activate_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Activate a provider's built-in enterprise API key with an activation code.

    The activation code is validated, and if correct, the built-in API key is
    decrypted and stored in the provider config. The frontend never sees the
    actual key — only the activation status.
    """
    from miqi.config.loader import save_config
    from miqi.config.schema import ProviderConfig, ProvidersConfig

    provider_name = params.get("provider_name", "").strip()
    activation_code = params.get("activation_code", "").strip()

    if not provider_name:
        raise AppServerError("provider_name is required", code="INVALID_PARAMS")
    if not activation_code:
        raise AppServerError("activation_code is required", code="INVALID_PARAMS")
    if provider_name not in _BUILTIN_PROVIDERS:
        raise AppServerError(
            f"Provider '{provider_name}' does not support built-in activation",
            code="NOT_SUPPORTED",
        )

    # Validate activation code
    if activation_code != _DEFAULT_ACTIVATION_CODE:
        raise AppServerError("激活码无效", code="INVALID_CODE")

    # Decrypt the built-in key
    api_key = _decrypt_builtin_key(provider_name)
    if not api_key:
        raise AppServerError(
            "未配置内置密钥，请联系管理员",
            code="NO_BUILTIN_KEY",
        )

    state = get_bridge_state(registry)
    config = state.load_config()
    pc = getattr(config.providers, provider_name, None)
    if pc is None:
        raise AppServerError(
            f"Provider config not found: {provider_name}", code="NOT_FOUND",
        )

    # Write the decrypted key to provider config
    current_dict = pc.model_dump(by_alias=False)
    current_dict["api_key"] = api_key
    new_pc = ProviderConfig.model_validate(current_dict)
    setattr(config.providers, provider_name, new_pc)

    # Mark as built-in activated so the frontend hides the real key
    activation_store = _provider_activation_store(config)
    activation_store[provider_name] = {
        "builtin": True,
        "activatedAt": datetime.now(timezone.utc).isoformat(),
    }

    save_config(config)
    state.config = config

    logger.info(
        "providers.activate: provider={} activated via built-in key", provider_name,
    )

    return {
        "result": {
            "activated": True,
            "provider_name": provider_name,
        }
    }


def _provider_activation_store(config: Any) -> dict[str, Any]:
    """Get or create the provider activation store in desktop config."""
    desktop = getattr(config, "desktop", None)
    if not isinstance(desktop, dict):
        desktop = {}
        config.desktop = desktop
    store = desktop.get("providerActivation")
    if not isinstance(store, dict):
        store = {}
        desktop["providerActivation"] = store
    return store
