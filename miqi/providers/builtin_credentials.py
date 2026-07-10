"""Built-in model credential unlock (issue #191, P2 — minimal loop).

Holds the built-in trial credential (DeepSeek in Phase 1) and exposes
``unlock`` / ``get_key`` / ``deactivate``. The decrypted key lives in process
memory only and is never persisted; after a restart the user re-enters the
unlock code.

This module keeps the MVP implementation local and minimal. Credential delivery
mechanisms can evolve independently later without changing the call sites below
(``unlock`` / ``get_key`` / ``deactivate``).

Security boundary (also stated in the PR description):

    This protects the bundled credential from casual extraction and local file
    inspection. It does not prevent extraction from a compromised client
    runtime — the runtime must hold the plaintext key in memory to call the
    model. The encryption ensures the bundled key is not readable by simply
    opening the bundle file, and that a wrong unlock code cannot derive the
    decryption key.
"""

from __future__ import annotations

import base64
import hashlib
import json
import threading
from importlib.resources import files
from pathlib import Path
from typing import Any

from loguru import logger

# Phase 1 ships exactly one built-in trial provider.
BUILTIN_PROVIDER = "deepseek"
_KEY_LEN = 32  # AES-256
_KDF = "sha256"
_AAD_VERSION = 1

# Maps an unlock code to its bundle file name. A code is the unit of revocation:
# retire an entry here to revoke that capability set. This table is empty in the
# source repo — production (code, bundle) pairs are populated by the release
# process that also generates the encrypted bundle resources. Tests inject their
# own mapping (plus a fixture bundle dir) via ``_CODE_TO_BUNDLE`` /
# ``_bundle_dir_override``, so no test/dev unlock code ever ships in the package.
_CODE_TO_BUNDLE: dict[str, str] = {}

# Bundle discovery. Production bundles ship under miqi/resources/builtin_models
# (resolved via importlib.resources so it works in editable installs, wheels,
# and PyInstaller builds). Tests point ``_bundle_dir_override`` at a fixtures
# dir instead of committing a dev bundle into the shipped package.
_RESOURCE_ROOT = "miqi"
_RESOURCE_SUBPATH = ("resources", "builtin_models")
_bundle_dir_override: Path | None = None


def _bundle_dir() -> Path:
    """Resolve the directory holding bundle files (package resources, or an
    injected override used by tests/dev)."""
    if _bundle_dir_override is not None:
        return _bundle_dir_override
    traversable = files(_RESOURCE_ROOT)
    for part in _RESOURCE_SUBPATH:
        traversable = traversable / part
    return Path(str(traversable))


def _bundle_path(code: str) -> Path | None:
    name = _CODE_TO_BUNDLE.get(code)
    if name is None:
        return None
    return _bundle_dir() / name


def _load_bundle(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _derive_key(code: str, salt: bytes, iters: int) -> bytes:
    return hashlib.pbkdf2_hmac(_KDF, code.encode("utf-8"), salt, iters, _KEY_LEN)


def _decrypt(bundle: dict[str, Any], code: str) -> str:
    """Decrypt the bundle credential. Raises on any failure (wrong code,
    corrupt bundle, version mismatch). Caller treats exception as bad code."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = base64.b64decode(bundle["kdf_salt"])
    nonce = base64.b64decode(bundle["nonce"])
    ciphertext = base64.b64decode(bundle["ciphertext"])
    iters = int(bundle["kdf_iters"])
    key = _derive_key(code, salt, iters)
    # AAD binds provider+version so a field-swapped bundle won't decrypt.
    aad = f'{bundle["provider"]}|{bundle["version"]}'.encode("utf-8")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:  # wrong code or tampered ciphertext
        raise ValueError("invalid unlock code or corrupted bundle") from exc
    return plaintext.decode("utf-8")


class _BuiltinKeyProvider:
    """Process-global holder for the unlocked built-in credential."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._key: str | None = None  # in-memory only; never persisted
        self._bundle_id: str | None = None

    def unlock(self, code: str) -> bool:
        """Validate ``code`` and decrypt the built-in key into memory.

        Returns True on success, False on a wrong/unknown code. Never raises
        to the caller — callers translate False into an AppServerError.
        """
        path = _bundle_path(code)
        if path is None or not path.exists():
            logger.debug("builtin unlock: unknown code")
            return False
        try:
            bundle = _load_bundle(path)
            key = _decrypt(bundle, code)
        except Exception as exc:  # noqa: BLE001 — any failure = bad code/state
            logger.debug("builtin unlock failed: {}", exc)
            return False
        with self._lock:
            self._key = key
            self._bundle_id = bundle.get("bundle_id")
        return True

    def get_key(self, provider: str) -> str | None:
        """Return the in-memory built-in key for ``provider``, else None.

        Only ``BUILTIN_PROVIDER`` is supported in Phase 1. Returns None (never
        raises) so ``Config.get_api_key`` can fall through cleanly.
        """
        if provider != BUILTIN_PROVIDER:
            return None
        with self._lock:
            return self._key

    def is_unlocked(self, provider: str) -> bool:
        if provider != BUILTIN_PROVIDER:
            return False
        with self._lock:
            return self._key is not None

    def bundle_id(self) -> str | None:
        with self._lock:
            return self._bundle_id

    def deactivate(self) -> None:
        """Clear the in-memory key. The persisted enabled flag is cleared by
        the handler; this drops the live credential so get_api_key falls through."""
        with self._lock:
            self._key = None
            self._bundle_id = None


# Single process-global instance. Handlers and Config.get_api_key share this.
BUILTIN_KEY_PROVIDER = _BuiltinKeyProvider()
