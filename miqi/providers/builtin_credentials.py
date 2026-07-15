"""Compatibility shim — built-in credentials have been merged into provider_handlers.

This module exists only to prevent import errors from stale test fixtures.
Do not add new functionality here.
"""
from __future__ import annotations

from typing import Any


class _BuiltinKeyProvider:
    """No-op provider — real logic is in miqi.runtime.provider_handlers."""

    @staticmethod
    def is_unlocked(_name: str | None) -> bool:
        return False

    @staticmethod
    def deactivate() -> None:
        pass

    @staticmethod
    def restore(_sealed: Any) -> None:
        pass

    @staticmethod
    def unlock(_code: str) -> dict[str, Any] | None:
        return None


BUILTIN_KEY_PROVIDER = _BuiltinKeyProvider()
_bundle_dir_override: Any = None
