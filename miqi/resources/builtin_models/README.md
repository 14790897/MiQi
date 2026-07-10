# Built-in model credential bundles

This directory holds **runtime credential bundles** shipped with the package.
Each bundle is an AES-GCM-encrypted JSON file (see
`miqi/providers/builtin_credentials.py`) whose decryption key is derived from
an unlock code via PBKDF2.

**Production bundles are generated during release preparation, not committed
to this repository.** Do not commit production (real) credentials here, and do
not commit development placeholder bundles — they belong in
`tests/fixtures/builtin_models/` (never packaged).

To (re)generate a release bundle:

```bash
uv run python scripts/encrypt_builtin_bundle.py \
    --provider deepseek \
    --key "<real api key>" \
    --code "<unlock code>" \
    --bundle-id deepseek_trial_001 \
    --out miqi/resources/builtin_models/deepseek_trial.bundle
```

`builtin_credentials.py` resolves this directory via `importlib.resources`, so
it works in editable installs, wheels, and PyInstaller builds. At runtime, if
no matching bundle is present, `unlock(code)` returns False (the feature is a
no-op for end users until a bundle is shipped).
