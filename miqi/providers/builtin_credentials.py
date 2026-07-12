"""Built-in model credential unlock support.

The bundled credential is encrypted at rest and decrypted only after the user
enters a matching unlock code. The plaintext key is held in process memory and
is never written back to MiQi config.

Security boundary: this protects against casual local file inspection. It does
not make a client-shipped credential impossible to extract from a compromised
runtime, because the runtime must eventually hold the plaintext key to call the
provider.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
from importlib.resources import files
from pathlib import Path
from typing import Any

from loguru import logger

BUILTIN_DEFAULT_MODEL = "deepseek/deepseek-v4-flash"

_KEY_LEN = 32
_KDF = "sha256"
_RESOURCE_ROOT = "miqi"
_RESOURCE_SUBPATH = ("resources", "builtin_models")
_MANIFEST_NAME = "index.json"
_LOCAL_KEY_NAME = "local_vault.key"

_bundle_dir_override: Path | None = None


def _bundle_dir() -> Path:
    if _bundle_dir_override is not None:
        return _bundle_dir_override
    override = os.environ.get("MIQI_BUILTIN_MODELS_DIR", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    traversable = files(_RESOURCE_ROOT)
    for part in _RESOURCE_SUBPATH:
        traversable = traversable / part
    return Path(str(traversable))


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


def _load_manifest() -> dict[str, Any]:
    path = _bundle_dir() / _MANIFEST_NAME
    if not path.exists():
        return {"version": 1, "bundles": []}
    return json.loads(path.read_text(encoding="utf-8"))


def _bundle_path_for_code(code: str) -> Path | None:
    manifest = _load_manifest()
    wanted = _code_hash(code)
    for item in manifest.get("bundles", []):
        if not isinstance(item, dict):
            continue
        if item.get("code_sha256") != wanted:
            continue
        filename = item.get("file")
        if not isinstance(filename, str) or not filename:
            return None
        return _bundle_dir() / filename
    return None


def _load_bundle(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _derive_key(code: str, salt: bytes, iters: int) -> bytes:
    return hashlib.pbkdf2_hmac(_KDF, code.encode("utf-8"), salt, iters, _KEY_LEN)


def _decrypt(bundle: dict[str, Any], code: str) -> str:
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = base64.b64decode(bundle["kdf_salt"])
    nonce = base64.b64decode(bundle["nonce"])
    ciphertext = base64.b64decode(bundle["ciphertext"])
    iters = int(bundle["kdf_iters"])
    key = _derive_key(code, salt, iters)
    aad_subject = bundle.get("license_id") or bundle.get("provider") or "builtin"
    aad = f'{aad_subject}|{bundle["version"]}'.encode("utf-8")
    try:
        plaintext = AESGCM(key).decrypt(nonce, ciphertext, aad)
    except InvalidTag as exc:
        raise ValueError("invalid unlock code or corrupted bundle") from exc
    return plaintext.decode("utf-8")


def _local_vault_key() -> bytes:
    """Return a per-install key used to survive bridge restarts without plaintext config."""
    from miqi.paths import get_miqi_home

    vault_dir = get_miqi_home() / "builtin_models"
    vault_dir.mkdir(parents=True, exist_ok=True)
    path = vault_dir / _LOCAL_KEY_NAME
    if path.exists():
        return base64.b64decode(path.read_text(encoding="utf-8").strip())
    key = secrets.token_bytes(_KEY_LEN)
    path.write_text(base64.b64encode(key).decode("ascii"), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return key


def _seal_payload(payload: dict[str, Any]) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    nonce = secrets.token_bytes(12)
    plaintext = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(_local_vault_key()).encrypt(nonce, plaintext, b"miqi-builtin-v1")
    return {
        "version": 1,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def _unseal_payload(sealed: dict[str, Any]) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    if int(sealed.get("version") or 0) != 1:
        raise ValueError("unsupported sealed credential version")
    nonce = base64.b64decode(str(sealed["nonce"]))
    ciphertext = base64.b64decode(str(sealed["ciphertext"]))
    plaintext = AESGCM(_local_vault_key()).decrypt(nonce, ciphertext, b"miqi-builtin-v1")
    payload = json.loads(plaintext.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("invalid sealed credential payload")
    return payload


def _normalize_provider(item: dict[str, Any]) -> dict[str, Any] | None:
    provider = str(item.get("provider") or item.get("name") or "").strip()
    api_key = str(item.get("api_key") or item.get("key") or "").strip()
    if not provider or not api_key:
        return None
    models = item.get("models")
    normalized_models = [str(model).strip() for model in models] if isinstance(models, list) else []
    normalized_models = [model for model in normalized_models if model]
    default_model = str(item.get("default_model") or item.get("defaultModel") or "").strip()
    if not default_model and normalized_models:
        default_model = normalized_models[0]
    return {
        "provider": provider,
        "api_key": api_key,
        "models": normalized_models,
        "default_model": default_model,
    }


def _decode_license_payload(bundle: dict[str, Any], plaintext: str) -> dict[str, Any]:
    """Decode a decrypted bundle payload.

    New bundles encrypt a JSON license payload with one or more providers.
    Older single-provider bundles encrypted just the API key string; keep that
    path for compatibility with the first issue #191 implementation.
    """
    try:
        payload = json.loads(plaintext)
    except json.JSONDecodeError:
        provider = str(bundle.get("provider") or "deepseek")
        return {
            "license_id": str(bundle.get("bundle_id") or provider),
            "providers": [{
                "provider": provider,
                "api_key": plaintext,
                "models": [BUILTIN_DEFAULT_MODEL] if provider == "deepseek" else [],
                "default_model": BUILTIN_DEFAULT_MODEL if provider == "deepseek" else "",
            }],
        }
    if not isinstance(payload, dict):
        raise ValueError("invalid license payload")
    providers = payload.get("providers")
    if not isinstance(providers, list):
        raise ValueError("license payload must include providers")
    normalized = [_normalize_provider(item) for item in providers if isinstance(item, dict)]
    normalized = [item for item in normalized if item is not None]
    if not normalized:
        raise ValueError("license payload contains no usable providers")
    return {
        "license_id": str(payload.get("license_id") or bundle.get("bundle_id") or ""),
        "label": str(payload.get("label") or ""),
        "providers": normalized,
    }


class _BuiltinKeyProvider:
    """Process-global holder for unlocked license provider credentials."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._keys: dict[str, str] = {}
        self._provider_meta: dict[str, dict[str, Any]] = {}
        self._bundle_id: str | None = None
        self._license_id: str | None = None
        self._label: str | None = None

    def unlock(self, code: str) -> dict[str, Any] | None:
        path = _bundle_path_for_code(code)
        if path is None or not path.exists():
            logger.debug("builtin model unlock: unknown code")
            return None
        try:
            bundle = _load_bundle(path)
            plaintext = _decrypt(bundle, code)
            license_payload = _decode_license_payload(bundle, plaintext)
        except Exception as exc:  # noqa: BLE001 - any failure means invalid bundle/code.
            logger.debug("builtin model unlock failed: {}", exc)
            return None
        with self._lock:
            self._bundle_id = str(bundle.get("bundle_id") or "")
            self._license_id = license_payload.get("license_id") or self._bundle_id
            self._label = license_payload.get("label") or ""
            self._keys = {
                item["provider"]: item["api_key"]
                for item in license_payload["providers"]
            }
            self._provider_meta = {
                item["provider"]: {
                    "provider": item["provider"],
                    "models": item.get("models") or [],
                    "defaultModel": item.get("default_model") or "",
                }
                for item in license_payload["providers"]
            }
        return self.metadata()

    def get_key(self, provider: str) -> str | None:
        with self._lock:
            return self._keys.get(provider)

    def is_unlocked(self, provider: str) -> bool:
        with self._lock:
            return provider in self._keys

    def providers(self) -> list[str]:
        with self._lock:
            return list(self._keys.keys())

    def metadata(self) -> dict[str, Any]:
        with self._lock:
            return {
                "bundleId": self._bundle_id,
                "licenseId": self._license_id,
                "label": self._label or "",
                "providers": list(self._provider_meta.values()),
            }

    def sealed_credentials(self) -> dict[str, Any] | None:
        with self._lock:
            if not self._keys:
                return None
            providers = []
            for provider, api_key in self._keys.items():
                meta = self._provider_meta.get(provider, {})
                providers.append({
                    "provider": provider,
                    "api_key": api_key,
                    "models": meta.get("models") or [],
                    "default_model": meta.get("defaultModel") or "",
                })
            return _seal_payload({
                "bundle_id": self._bundle_id,
                "license_id": self._license_id,
                "label": self._label or "",
                "providers": providers,
            })

    def restore(self, sealed: dict[str, Any] | None) -> bool:
        if not isinstance(sealed, dict):
            return False
        try:
            payload = _unseal_payload(sealed)
            providers = payload.get("providers")
            if not isinstance(providers, list):
                return False
            normalized = [_normalize_provider(item) for item in providers if isinstance(item, dict)]
            normalized = [item for item in normalized if item is not None]
            if not normalized:
                return False
        except Exception as exc:  # noqa: BLE001 - corrupted local cache should act as missing.
            logger.debug("builtin model restore failed: {}", exc)
            return False
        with self._lock:
            self._bundle_id = str(payload.get("bundle_id") or "")
            self._license_id = str(payload.get("license_id") or self._bundle_id or "")
            self._label = str(payload.get("label") or "")
            self._keys = {
                item["provider"]: item["api_key"]
                for item in normalized
            }
            self._provider_meta = {
                item["provider"]: {
                    "provider": item["provider"],
                    "models": item.get("models") or [],
                    "defaultModel": item.get("default_model") or "",
                }
                for item in normalized
            }
        return True

    def bundle_id(self) -> str | None:
        with self._lock:
            return self._bundle_id

    def deactivate(self) -> None:
        with self._lock:
            self._keys = {}
            self._provider_meta = {}
            self._bundle_id = None
            self._license_id = None
            self._label = None


BUILTIN_KEY_PROVIDER = _BuiltinKeyProvider()
