"""Gemini provider — uses Google's OpenAI-compatible endpoint.

Google exposes an OpenAI-compatible API at:
  https://generativelanguage.googleapis.com/v1beta/openai/

This means we can reuse OpenAIProvider almost exactly; the only differences are
the base URL and stripping the 'gemini/' prefix from model names.
"""

from __future__ import annotations

from featherflow.providers.openai_provider import OpenAIProvider

GEMINI_API_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"


class GeminiProvider(OpenAIProvider):
    """
    Provider for Google Gemini models via the OpenAI-compatible endpoint.

    Accepts the same interface as OpenAIProvider; Google API keys go directly
    as the Bearer token in the Authorization header.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gemini-2.5-pro",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        # Always use Google's OpenAI-compatible endpoint unless user explicitly overrides
        effective_base = api_base or GEMINI_API_BASE

        super().__init__(
            api_key=api_key,
            api_base=effective_base,
            default_model=default_model,
            extra_headers=extra_headers,
            provider_name=provider_name or "gemini",
        )

    def _resolve_model(self, model: str) -> str:
        """Strip 'gemini/' prefix so the Google API receives the bare model name."""
        if model.startswith("gemini/"):
            return model[len("gemini/"):]
        return model

    def get_default_model(self) -> str:
        return self.default_model
