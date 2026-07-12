"""Maintainer helper to generate encrypted built-in model bundles.

This script is not used at runtime. It takes one or more provider API keys plus
an unlock code, writes an encrypted license bundle, and updates an index
manifest that stores only sha256(unlock_code), not the code itself.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path
from typing import Any

KDF_ITERS = 200_000
KEY_LEN = 32
BUNDLE_VERSION = 1


def derive_key(code: str, salt: bytes, iters: int = KDF_ITERS) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", code.encode("utf-8"), salt, iters, KEY_LEN)


def encrypt_bundle(
    *,
    license_payload: dict[str, Any],
    code: str,
    bundle_id: str,
) -> dict[str, Any]:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM

    salt = secrets.token_bytes(16)
    nonce = secrets.token_bytes(12)
    key = derive_key(code, salt)
    license_id = str(license_payload.get("license_id") or bundle_id)
    aad = f"{license_id}|{BUNDLE_VERSION}".encode("utf-8")
    plaintext = json.dumps(license_payload, separators=(",", ":")).encode("utf-8")
    ciphertext = AESGCM(key).encrypt(nonce, plaintext, aad)
    return {
        "license_id": license_id,
        "version": BUNDLE_VERSION,
        "kdf_salt": base64.b64encode(salt).decode("ascii"),
        "kdf_iters": KDF_ITERS,
        "nonce": base64.b64encode(nonce).decode("ascii"),
        "ciphertext": base64.b64encode(ciphertext).decode("ascii"),
        "bundle_id": bundle_id,
    }


def update_manifest(manifest_path: Path, code: str, bundle_file: str, license_id: str) -> None:
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    else:
        manifest = {"version": 1, "bundles": []}
    bundles = [item for item in manifest.get("bundles", []) if isinstance(item, dict)]
    code_sha256 = hashlib.sha256(code.encode("utf-8")).hexdigest()
    bundles = [item for item in bundles if item.get("code_sha256") != code_sha256]
    bundles.append({
        "code_sha256": code_sha256,
        "file": bundle_file,
        "license_id": license_id,
    })
    manifest["version"] = 1
    manifest["bundles"] = bundles
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate an encrypted built-in model bundle.")
    parser.add_argument(
        "--provider",
        action="append",
        default=[],
        help=(
            "Provider entry as provider=api_key or provider=api_key:model1,model2. "
            "May be repeated."
        ),
    )
    parser.add_argument("--key", default=None, help="Plaintext API key for --provider-name, or BUILTIN_BUNDLE_KEY")
    parser.add_argument("--provider-name", default="deepseek", help="Provider name used with --key")
    parser.add_argument(
        "--model",
        action="append",
        default=[],
        help="Model allowed for --provider-name/--key. May be repeated.",
    )
    parser.add_argument("--code", default=None, help="Unlock code, or BUILTIN_BUNDLE_CODE")
    parser.add_argument("--out", required=True, help="Output bundle path")
    parser.add_argument("--bundle-id", default=None)
    parser.add_argument("--license-id", default=None)
    parser.add_argument("--label", default="")
    parser.add_argument("--manifest", default=None, help="Manifest path, defaults to <out dir>/index.json")
    args = parser.parse_args()

    api_key = args.key or os.environ.get("BUILTIN_BUNDLE_KEY")
    unlock_code = args.code or os.environ.get("BUILTIN_BUNDLE_CODE")
    provider_entries: list[dict[str, Any]] = []
    for raw in args.provider:
        name_and_key, _, models_text = raw.partition(":")
        name, sep, key = name_and_key.partition("=")
        if not sep or not name.strip() or not key.strip():
            parser.error("--provider entries must look like provider=api_key[:model1,model2]")
        models = [model.strip() for model in models_text.split(",") if model.strip()]
        provider_entries.append({
            "provider": name.strip(),
            "api_key": key.strip(),
            "models": models,
            "default_model": models[0] if models else "",
        })

    if api_key:
        models = [model.strip() for model in args.model if model.strip()]
        provider_entries.append({
            "provider": args.provider_name,
            "api_key": api_key,
            "models": models,
            "default_model": models[0] if models else "",
        })

    if not provider_entries:
        parser.error("--key or BUILTIN_BUNDLE_KEY is required")
    if not unlock_code:
        parser.error("--code or BUILTIN_BUNDLE_CODE is required")

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    bundle_id = args.bundle_id or f"license_{secrets.token_hex(4)}"
    license_id = args.license_id or bundle_id
    license_payload = {
        "license_id": license_id,
        "label": args.label,
        "providers": provider_entries,
    }
    bundle = encrypt_bundle(license_payload=license_payload, code=unlock_code, bundle_id=bundle_id)
    out_path.write_text(json.dumps(bundle, indent=2) + "\n", encoding="utf-8")

    manifest_path = Path(args.manifest) if args.manifest else out_path.parent / "index.json"
    update_manifest(manifest_path, unlock_code, out_path.name, license_id)
    print(f"Wrote encrypted bundle: {out_path}")
    print(f"Updated manifest: {manifest_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
