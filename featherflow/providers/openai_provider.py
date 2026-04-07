"""OpenAI-compatible provider — covers OpenAI, DeepSeek, Moonshot, Zhipu, DashScope,
MiniMax, Groq, SiliconFlow, VolcEngine, AiHubMix, OpenRouter, vLLM, Ollama, and any
other endpoint that speaks the OpenAI chat-completions API.
"""

from __future__ import annotations

import asyncio
import json
import os
import random
from typing import Any
from urllib.parse import urlparse, urlunparse

import json_repair
from loguru import logger
from openai import AsyncOpenAI

from featherflow.providers.base import LLMProvider, LLMResponse, ToolCallRequest
from featherflow.providers.registry import find_by_model, find_by_name, find_gateway

# Standard OpenAI chat-completion message keys; extras (e.g. reasoning_content) are
# stripped for providers that reject unknown fields.
_ALLOWED_MSG_KEYS = frozenset({"role", "content", "tool_calls", "tool_call_id", "name"})


class OpenAIProvider(LLMProvider):
    """
    Provider for any OpenAI-compatible endpoint.

    Routing is driven entirely by registry metadata (providers/registry.py).
    No litellm dependency — uses openai.AsyncOpenAI directly.
    """

    def __init__(
        self,
        api_key: str | None = None,
        api_base: str | None = None,
        default_model: str = "gpt-4o",
        extra_headers: dict[str, str] | None = None,
        provider_name: str | None = None,
    ):
        self._selected_spec = find_by_name(provider_name) if provider_name else None
        self._gateway = find_gateway(provider_name, api_key, api_base)

        api_base = self._normalize_api_base(api_base)

        # Resolve effective api_base: user value → spec default
        effective_base = api_base or self._default_api_base()

        super().__init__(api_key, effective_base)
        self.default_model = default_model
        self.extra_headers = extra_headers or {}

        if api_key:
            self._setup_env(api_key, api_base)

        self._client = AsyncOpenAI(
            api_key=api_key or "no-key",
            base_url=effective_base or None,
            default_headers=self.extra_headers,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _default_api_base(self) -> str | None:
        """Return the spec's default api_base, if any."""
        spec = self._gateway or self._selected_spec
        return spec.default_api_base if spec and spec.default_api_base else None

    def _normalize_api_base(self, api_base: str | None) -> str | None:
        """Normalize provider-specific base URLs."""
        if not api_base:
            return api_base

        api_base = api_base.strip()
        spec = self._gateway or self._selected_spec

        if spec and spec.name in {"ollama_local", "ollama_cloud"}:
            # openai SDK needs /v1 suffix; litellm used the bare host.
            # Strip /api suffix and ensure /v1.
            for suffix in ("/api/", "/api"):
                if api_base.endswith(suffix):
                    api_base = api_base[: -len(suffix)]
                    break
            if not api_base.rstrip("/").endswith("/v1"):
                api_base = api_base.rstrip("/") + "/v1"
            return api_base

        if spec and spec.default_api_base:
            api_base = self._fill_default_base_path(api_base, spec.default_api_base)

        return api_base

    @staticmethod
    def _fill_default_base_path(api_base: str, default_api_base: str) -> str:
        """Fill missing path portion from the spec default.

        Example: user provides 'https://api.moonshot.cn', default is
        'https://api.moonshot.ai/v1' → fills to 'https://api.moonshot.cn/v1'.
        """
        parsed_api = urlparse(api_base)
        parsed_default = urlparse(default_api_base)

        if not parsed_api.scheme or not parsed_api.netloc:
            return api_base
        if parsed_api.path not in {"", "/"}:
            return api_base

        default_path = parsed_default.path.rstrip("/")
        if not default_path:
            return api_base

        return urlunparse(parsed_api._replace(path=default_path))

    def _setup_env(self, api_key: str, api_base: str | None) -> None:
        """Set the primary API-key environment variable if the spec defines one."""
        spec = self._gateway or self._selected_spec
        if not spec or not spec.env_key:
            return
        if self._gateway:
            os.environ[spec.env_key] = api_key
        else:
            os.environ.setdefault(spec.env_key, api_key)

    def _resolve_model(self, model: str) -> str:
        """Strip provider prefix so the downstream API receives the bare model name.

        Rules:
        - Gateway with strip_model_prefix=True (e.g. AiHubMix): keep only the
          last segment ('anthropic/claude-3' → 'claude-3').
        - Gateway without strip (e.g. OpenRouter): strip the gateway's own prefix
          only ('openrouter/anthropic/claude-3' → 'anthropic/claude-3').
        - Standard/local provider: strip model_prefix/ if present
          ('deepseek/deepseek-chat' → 'deepseek-chat').
        """
        if self._gateway:
            if self._gateway.strip_model_prefix:
                return model.split("/")[-1]
            prefix = self._gateway.model_prefix
            if prefix and model.startswith(f"{prefix}/"):
                return model[len(prefix) + 1:]
            return model

        spec = self._selected_spec or find_by_model(model)
        if spec:
            for candidate in (spec.model_prefix, spec.name):
                if candidate and model.startswith(f"{candidate}/"):
                    return model[len(candidate) + 1:]

        return model

    def _apply_model_overrides(self, model: str, kwargs: dict[str, Any]) -> None:
        """Apply per-model parameter overrides from the registry (e.g. kimi-k2.5 temperature)."""
        model_lower = model.lower()
        spec = self._selected_spec or find_by_model(model)
        if spec:
            for pattern, overrides in spec.model_overrides:
                if pattern in model_lower:
                    kwargs.update(overrides)
                    return

    def _sanitize_messages(
        self,
        messages: list[dict[str, Any]],
        *,
        keep_reasoning: bool = False,
    ) -> list[dict[str, Any]]:
        """Strip non-standard keys; optionally keep reasoning_content for DeepSeek R1."""
        allowed = _ALLOWED_MSG_KEYS | {"reasoning_content"} if keep_reasoning else _ALLOWED_MSG_KEYS
        sanitized = []
        for msg in messages:
            clean = {k: v for k, v in msg.items() if k in allowed}
            if clean.get("role") == "assistant" and "content" not in clean:
                clean["content"] = None
            sanitized.append(clean)
        return sanitized

    def _is_transient_network_error(self, error: Exception) -> bool:
        """Return True for retryable transient errors."""
        msg = str(error).lower()
        signals = (
            "apiconnectionerror",
            "connection reset",
            "connection aborted",
            "temporary failure",
            "timed out",
            "timeout",
            "502",
            "503",
            "504",
            "bad gateway",
            "service unavailable",
        )
        return any(s in msg for s in signals)

    # ------------------------------------------------------------------
    # Main interface
    # ------------------------------------------------------------------

    async def chat(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]] | None = None,
        model: str | None = None,
        max_tokens: int = 4096,
        temperature: float = 0.7,
    ) -> LLMResponse:
        original_model = model or self.default_model
        resolved = self._resolve_model(original_model)
        max_tokens = max(1, max_tokens)

        spec = self._selected_spec or find_by_model(original_model)
        keep_reasoning = bool(spec and spec.supports_reasoning_history)

        kwargs: dict[str, Any] = {
            "model": resolved,
            "messages": self._sanitize_messages(
                self._sanitize_empty_content(messages),
                keep_reasoning=keep_reasoning,
            ),
            "max_tokens": max_tokens,
            "temperature": temperature,
        }

        self._apply_model_overrides(resolved, kwargs)

        if tools:
            kwargs["tools"] = tools
            kwargs["tool_choice"] = "auto"

        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            try:
                response = await self._client.chat.completions.create(**kwargs)
                return self._parse_response(response)
            except Exception as e:
                if attempt < max_attempts and self._is_transient_network_error(e):
                    delay = min(30, (2 ** (attempt - 1)) * (0.5 + random.random() * 0.5))
                    await asyncio.sleep(delay)
                    continue
                return LLMResponse(
                    content=f"Error calling LLM: {e}",
                    finish_reason="error",
                )

        return LLMResponse(content="Error calling LLM: retries exhausted", finish_reason="error")

    def _parse_response(self, response: Any) -> LLMResponse:
        """Parse an OpenAI-compatible response object into LLMResponse."""
        if not response.choices:
            return LLMResponse(content=None, finish_reason="stop")
        choice = response.choices[0]
        message = choice.message

        tool_calls: list[ToolCallRequest] = []
        if hasattr(message, "tool_calls") and message.tool_calls:
            for tc in message.tool_calls:
                args = tc.function.arguments
                if isinstance(args, str):
                    repaired = json_repair.loads(args)
                    try:
                        original = json.loads(args)
                    except (json.JSONDecodeError, ValueError):
                        logger.warning(
                            "json_repair fixed malformed tool args for '{}': {}",
                            tc.function.name,
                            args[:200],
                        )
                        original = None
                    args = repaired if original is None else original

                if not isinstance(args, dict):
                    args = {}

                tool_calls.append(ToolCallRequest(
                    id=tc.id,
                    name=tc.function.name,
                    arguments=args,
                ))

        if not tool_calls and isinstance(message.content, str):
            fallback = self._parse_tool_call_from_content(message.content)
            if fallback:
                tool_calls.append(fallback)

        usage: dict[str, int] = {}
        if hasattr(response, "usage") and response.usage:
            usage = {
                "prompt_tokens": response.usage.prompt_tokens,
                "completion_tokens": response.usage.completion_tokens,
                "total_tokens": response.usage.total_tokens,
            }

        reasoning_content = getattr(message, "reasoning_content", None) or None

        return LLMResponse(
            content=message.content,
            tool_calls=tool_calls,
            finish_reason=choice.finish_reason or "stop",
            usage=usage,
            reasoning_content=reasoning_content,
        )

    def _parse_tool_call_from_content(self, content: str) -> ToolCallRequest | None:
        """Best-effort parser for models that emit tool calls as plain JSON."""
        decoder = json.JSONDecoder()
        for idx, char in enumerate(content):
            if char != "{":
                continue
            try:
                obj, _ = decoder.raw_decode(content[idx:])
            except Exception:
                continue
            if not isinstance(obj, dict):
                continue

            # Format A: {"name": "...", "arguments": {...}}
            name = obj.get("name")
            arguments = obj.get("arguments")
            if isinstance(name, str) and isinstance(arguments, dict):
                return ToolCallRequest(id="tool_call_fallback_1", name=name, arguments=arguments)

            # Format B: {"function": {"name": "...", "arguments": {...}}}
            function = obj.get("function")
            if isinstance(function, dict):
                func_name = function.get("name")
                func_args = function.get("arguments")
                if isinstance(func_name, str):
                    if isinstance(func_args, str):
                        try:
                            func_args = json.loads(func_args)
                        except Exception:
                            func_args = {"raw": func_args}
                    if isinstance(func_args, dict):
                        return ToolCallRequest(
                            id="tool_call_fallback_1", name=func_name, arguments=func_args
                        )

        return None

    def get_default_model(self) -> str:
        return self.default_model
