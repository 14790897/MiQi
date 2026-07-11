"""Maintainer-only helper to (re)generate the built-in model credential bundle.

This script is NOT shipped to end users and is never invoked at runtime. It
takes a plaintext provider API key plus an unlock code and emits the encrypted
bundle resource consumed by ``miqi.providers.builtin_credentials``.

Usage::

    uv run python scripts/encrypt_builtin_bundle.py \\
        --provider deepseek \\
        --key "sk-..." \\
        --code "TRIAL-XXXX-XXXX" \\
        --out miqi/resources/builtin_models/deepseek_trial.bundle

The bundle format mirrors what ``builtin_credentials.unlock`` expects:
``{provider, version, kdf_salt, kdf_iters, nonce, ciphertext}``.

Security note: this protects the bundled credential from casual extraction and
local file inspection. It does not prevent extraction from a compromised client
runtime — the runtime must hold the plaintext key in memory to call the model.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import secrets
import sys
from pathlib import Path

KDF_ITERS = 200_000
KEY_LEN = 32  # AES-256
BUNDLE_VERSION = 1


def derive_key(code: str, salt: bytes, iters: int = KDF_ITERS) -> bytes:
    """Derive an AES key from the unlock code via PBKDF2-HMAC-SHA256."""
    import hashlib

    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, iters, KEY_LEN)


def encrypt_bundle(provider: str, api_key: str, code: str) -> dict:
    """Encrypt ``api_key`` so it can only be decrypted with ``code``."""
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)  # 96-bit nonce recommended for AES-GCM
    key = derive_key(code, salt)
    # Bind provider+version into the AAD so a swapped bundle field can't decrypt.
    aad = f"{provider}|{BUNDLE_VERSION}".encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, api_key.encode("utf-8"), aad)
    return {
        "provider": provider,
        "version": BUNDLE_VERSION,
        "kdf_salt": base64.b64encode(salt).decode("ascii"),
        "kdf_iters": KDF_ITERS,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an encrypted builtin-model bundle.")
    parser.add_argument("--provider", required=True, help="Provider name, e.g. deepseek")
    parser.add_argument("--key", default=None, help="Plaintext API key to bundle (or env BUILTIN_BUNDLE_KEY)")
    parser.add_argument("--code", default=None, help="Unlock code that should activate this bundle (or env BUILTIN_BUNDLE_CODE)")
    parser.add_argument("--out", required=True, help="Output bundle JSON path")
    parser.add_argument("--bundle-id", default=None, help="Optional bundle id; defaults to provider name")
    args = parser.parse_args()

    api_key = args.key or os.environ.get("BUILTIN_BUNDLE_KEY")
    unlock_code = args.code or os.environ.get("BUILTIN_BUNDLE_CODE")
    if not api_key:
        parser.error("--key or BUILTIN_BUNDLE_KEY env var is required")
    if not unlock_code:
        parser.error("--code or BUILTIN_BUNDLE_CODE env var is required")

    bundle = encrypt_bundle(args.provider, api_key, unlock_code)
    bundle["bundle_id"] = args.bundle_id or args.provider

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(bundle, indent=2), encoding="utf-8")
    print(f"Wrote bundle for provider={args.provider} -> {out_path}")
    print("Verify by running builtin_credentials.unlock(code) in a test.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
