from __future__ import annotations

import asyncio
import random
import re
from collections.abc import Awaitable, Callable
from enum import Enum
from typing import TypeVar

T = TypeVar("T")


class ErrorKind(str, Enum):
    TRANSIENT = "transient"
    RATE_LIMIT = "rate_limit"
    AUTH = "auth"
    CONTEXT_LENGTH = "context_length"
    INVALID_REQUEST = "invalid_request"
    FATAL = "fatal"


_RETRYABLE = {ErrorKind.TRANSIENT, ErrorKind.RATE_LIMIT}


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def _status_code(exc: BaseException) -> int | None:
    """Read status_code from exception or its response, then scan message for 3-digit code."""
    # Direct attribute
    code = getattr(exc, "status_code", None)
    if isinstance(code, int):
        return code

    # Wrapped response attribute
    response = getattr(exc, "response", None)
    if response is not None:
        code = getattr(response, "status_code", None)
        if isinstance(code, int):
            return code
        code = getattr(response, "status", None)
        if isinstance(code, int):
            return code

    # Fallback: scan message for a 3-digit HTTP code
    message = str(exc).lower()
    matches = re.findall(r"\b(\d{3})\b", message)
    for m in matches:
        code = int(m)
        if 400 <= code < 600:
            return code
    return None


def _header_value(exc: BaseException, name: str) -> str | None:
    """Return a header value from the exception or its response, case-insensitively."""
    exc_headers = getattr(exc, "headers", None)
    if exc_headers is not None:
        if hasattr(exc_headers, "get"):
            try:
                value = exc_headers.get(name)
                if value is not None:
                    return str(value)
            except Exception:
                pass
        if isinstance(exc_headers, dict):
            key_lower = name.lower()
            for k, v in exc_headers.items():
                if k.lower() == key_lower:
                    return str(v)

    response = getattr(exc, "response", None)
    if response is not None:
        response_headers = getattr(response, "headers", None)
        if response_headers is not None:
            if hasattr(response_headers, "get"):
                try:
                    value = response_headers.get(name)
                    if value is not None:
                        return str(value)
                except Exception:
                    pass
            if isinstance(response_headers, dict):
                key_lower = name.lower()
                for k, v in response_headers.items():
                    if k.lower() == key_lower:
                        return str(v)
    return None


def _classify_by_message(exc: BaseException) -> ErrorKind | None:
    """Classify by substrings for generic exceptions without SDK type/status code."""
    message = str(exc).lower()

    if "rate limit" in message or "too many requests" in message:
        return ErrorKind.RATE_LIMIT
    if "invalid api key" in message or "unauthorized" in message or "forbidden" in message:
        return ErrorKind.AUTH
    if _is_context_length_error(exc):
        return ErrorKind.CONTEXT_LENGTH
    if "not found" in message or "bad request" in message or "invalid request" in message:
        return ErrorKind.INVALID_REQUEST

    return None


def _is_context_length_error(exc: BaseException) -> bool:
    """Detect context-length / token-limit errors from message text."""
    message = str(exc).lower()
    signals = (
        "context length",
        "context_length",
        "token limit",
        "too many tokens",
        "context window",
        "max_tokens",
        "maximum context",
    )
    return any(s in message for s in signals)


def _classify_by_status_code(exc: BaseException) -> ErrorKind | None:
    """Classify a retry error by HTTP status code."""
    code = _status_code(exc)
    if code is None:
        return None

    if code == 429:
        return ErrorKind.RATE_LIMIT
    if code in (401, 403):
        return ErrorKind.AUTH
    if code in (408, 409) or 500 <= code < 600:
        return ErrorKind.TRANSIENT
    if code in (400, 404):
        if _is_context_length_error(exc):
            return ErrorKind.CONTEXT_LENGTH
        return ErrorKind.INVALID_REQUEST
    if code == 413:
        if _is_context_length_error(exc):
            return ErrorKind.CONTEXT_LENGTH
        return ErrorKind.INVALID_REQUEST
    return None


def _classify_transient_by_message(exc: BaseException) -> bool:
    """Match the union of transient signal keywords from the previous provider paths."""
    message = str(exc).lower()
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
        "overloaded",
    )
    return any(s in message for s in signals)


def classify_error(exc: BaseException) -> ErrorKind:
    """Classify an exception using SDK types (defensively imported) plus a string-match fallback."""
    # Defensive SDK type mapping.
    try:
        import openai

        api_connection_error = getattr(openai, "APIConnectionError", ())
        api_timeout_error = getattr(openai, "APITimeoutError", ())
        timeout_error = getattr(openai, "Timeout", ())
        rate_limit_error = getattr(openai, "RateLimitError", ())
        authentication_error = getattr(openai, "AuthenticationError", ())
        permission_denied_error = getattr(openai, "PermissionDeniedError", ())
        not_found_error = getattr(openai, "NotFoundError", ())
        bad_request_error = getattr(openai, "BadRequestError", ())
        conflict_error = getattr(openai, "ConflictError", ())
        internal_server_error = getattr(openai, "InternalServerError", ())
        api_status_error = getattr(openai, "APIStatusError", ())

        if isinstance(exc, api_connection_error):
            if getattr(exc, "status_code", None) == 429:
                return ErrorKind.RATE_LIMIT
            return ErrorKind.TRANSIENT
        if isinstance(exc, (api_timeout_error, timeout_error)):
            return ErrorKind.TRANSIENT
        if isinstance(exc, rate_limit_error):
            return ErrorKind.RATE_LIMIT
        if isinstance(exc, (authentication_error, permission_denied_error)):
            return ErrorKind.AUTH
        if isinstance(exc, not_found_error):
            if _is_context_length_error(exc):
                return ErrorKind.CONTEXT_LENGTH
            return ErrorKind.INVALID_REQUEST
        if isinstance(exc, bad_request_error):
            if _is_context_length_error(exc):
                return ErrorKind.CONTEXT_LENGTH
            by_code = _classify_by_status_code(exc)
            if by_code is not None:
                return by_code
            return ErrorKind.INVALID_REQUEST
        if isinstance(exc, conflict_error):
            return ErrorKind.TRANSIENT
        if isinstance(exc, internal_server_error):
            return ErrorKind.TRANSIENT
        if isinstance(exc, api_status_error):
            by_code = _classify_by_status_code(exc)
            if by_code is not None:
                return by_code
    except ImportError:
        pass

    try:
        import anthropic

        api_connection_error = getattr(anthropic, "APIConnectionError", ())
        api_timeout_error = getattr(anthropic, "APITimeoutError", ())
        timeout_error = getattr(anthropic, "Timeout", ())
        rate_limit_error = getattr(anthropic, "RateLimitError", ())
        authentication_error = getattr(anthropic, "AuthenticationError", ())
        permission_denied_error = getattr(anthropic, "PermissionDeniedError", ())
        not_found_error = getattr(anthropic, "NotFoundError", ())
        bad_request_error = getattr(anthropic, "BadRequestError", ())
        overloaded_error = getattr(anthropic, "OverloadedError", ())
        internal_server_error = getattr(anthropic, "InternalServerError", ())

        if isinstance(exc, api_connection_error):
            return ErrorKind.TRANSIENT
        if isinstance(exc, (api_timeout_error, timeout_error)):
            return ErrorKind.TRANSIENT
        if isinstance(exc, rate_limit_error):
            return ErrorKind.RATE_LIMIT
        if isinstance(exc, (authentication_error, permission_denied_error)):
            return ErrorKind.AUTH
        if isinstance(exc, not_found_error):
            if _is_context_length_error(exc):
                return ErrorKind.CONTEXT_LENGTH
            return ErrorKind.INVALID_REQUEST
        if isinstance(exc, bad_request_error):
            if _is_context_length_error(exc):
                return ErrorKind.CONTEXT_LENGTH
            by_code = _classify_by_status_code(exc)
            if by_code is not None:
                return by_code
            return ErrorKind.INVALID_REQUEST
        if isinstance(exc, overloaded_error):
            return ErrorKind.TRANSIENT
        if isinstance(exc, internal_server_error):
            return ErrorKind.TRANSIENT
    except ImportError:
        pass

    # Status-code fallback
    by_code = _classify_by_status_code(exc)
    if by_code is not None:
        return by_code

    # Transient keyword fallback (union of provider signal lists).
    if _classify_transient_by_message(exc):
        return ErrorKind.TRANSIENT

    by_message = _classify_by_message(exc)
    if by_message is not None:
        return by_message

    return ErrorKind.FATAL


def is_retryable(kind: ErrorKind) -> bool:
    return kind in _RETRYABLE


class ProviderError(Exception):
    """A terminal provider failure carrying a classified ``ErrorKind``.

    Raised by the runtime when a provider response reports
    ``finish_reason == "error"`` (e.g. after plan/56 retries are exhausted).
    Carries the provider's error category so callers (TaskRunner) can
    surface a useful, user-actionable message and recoverability flag
    without re-inspecting SDK/HTTP details.
    """

    def __init__(self, *, kind: ErrorKind, message: str):
        super().__init__(message)
        self.kind = kind
        self.message = message

    @property
    def recoverable(self) -> bool:
        return is_retryable(self.kind)


def retry_after_seconds(exc: BaseException) -> float | None:
    """Parse Retry-After header/attribute/response value.

    Check, in order:
    - exc.response.headers.get("Retry-After") or retry-after / retry_after attr
    - exc.headers if present
    - exc.retry_after or exc.retry_after_ms
    Return float seconds, None if missing/unparseable.
    """
    # Header first (canonical and retry-after variants)
    for header_name in ("Retry-After", "retry-after", "retry_after"):
        value = _header_value(exc, header_name)
        if value:
            parsed = _parse_retry_after_seconds(value)
            if parsed is not None:
                return parsed

    # Direct retry_after attribute (seconds)
    retry_after_attr = getattr(exc, "retry_after", None)
    if retry_after_attr is not None:
        parsed = _parse_retry_after_seconds(str(retry_after_attr))
        if parsed is not None:
            return parsed

    # Direct retry_after_ms attribute (milliseconds)
    retry_after_ms = getattr(exc, "retry_after_ms", None)
    if retry_after_ms is not None:
        try:
            return float(int(retry_after_ms)) / 1000.0
        except (TypeError, ValueError):
            pass

    return None


def _parse_retry_after_seconds(value: str) -> float | None:
    """Parse a Retry-After value expressed in seconds."""
    value = value.strip()
    if not value:
        return None
    try:
        return float(int(value))
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return None


def compute_backoff(
    attempt: int,
    *,
    retry_after: float | None = None,
    base: float = 0.5,
    cap: float = 30.0,
) -> float:
    """Compute backoff delay in seconds.

    If retry_after set: min(cap*2, retry_after + random()*base).
    Else: min(cap, (2 ** (attempt - 1)) * (base + random() * base)).
    attempt is 1-indexed.
    """
    attempt = max(1, int(attempt))
    if retry_after is not None and retry_after >= 0:
        return min(cap * 2, retry_after + random.random() * base)
    return min(cap, (2 ** (attempt - 1)) * (base + random.random() * base))


async def with_retry(
    factory: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    on_retry: Callable[[int, ErrorKind, float], None] | None = None,
) -> T:
    """Call factory repeatedly until success or non-retryable/exhausted.

    - On exception, classify it.
    - If attempt < max_attempts and is_retryable(kind): compute delay,
      call on_retry(attempt, kind, delay), await sleep(delay), continue.
    - Else raise the last exception.
    """
    last_exc: BaseException | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            return await factory()
        except BaseException as e:
            last_exc = e
            kind = classify_error(e)
            if attempt < max_attempts and is_retryable(kind):
                retry_after = retry_after_seconds(e)
                delay = compute_backoff(attempt, retry_after=retry_after)
                if on_retry is not None:
                    on_retry(attempt, kind, delay)
                await sleep(delay)
                continue
            raise
    if last_exc is not None:
        raise last_exc
    raise RuntimeError("with_retry exhausted without exception")
