"""Shared provider factory — creates the appropriate LLM provider from config.

Used by CLI, TUI, and any other entry point that needs a provider.
"""

from __future__ import annotations

from typing import Any


def make_provider(config: Any) -> Any:
    """Create the appropriate LLM provider from config.

    Args:
        config: Config object with agents.defaults.model, providers, etc.

    Returns:
        An LLMProvider instance.

    Raises:
        ValueError: If no API key is configured and the provider is not local.
    """
    from miqi.providers.custom_provider import CustomProvider
    from miqi.providers.registry import find_by_name

    model = config.agents.defaults.model
    provider_name = config.get_provider_name(model)
    p = config.get_provider(model)

    # Custom: direct OpenAI-compatible endpoint
    if provider_name == "custom":
        return CustomProvider(
            api_key=p.api_key if p else "no-key",
            api_base=config.get_api_base(model) or "http://localhost:8000/v1",
            default_model=model,
        )

    spec = find_by_name(provider_name)
    if not model.startswith("bedrock/") and not (p and p.api_key) and not (spec and spec.is_local):
        raise ValueError(
            "No API key configured. "
            "Set one in your config file under the providers section."
        )

    provider_type = spec.provider_type if spec else "openai"

    common_kwargs = dict(
        api_key=p.api_key if p else None,
        api_base=config.get_api_base(model),
        default_model=model,
        extra_headers=p.extra_headers if p else None,
        provider_name=provider_name,
    )

    if provider_type == "anthropic":
        from miqi.providers.anthropic_provider import AnthropicProvider
        return AnthropicProvider(**common_kwargs)

    if provider_type == "gemini":
        from miqi.providers.gemini_provider import GeminiProvider
        return GeminiProvider(**common_kwargs)

    from miqi.providers.openai_provider import OpenAIProvider
    return OpenAIProvider(**common_kwargs)
