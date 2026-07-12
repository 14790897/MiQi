Built-in model bundle resources live here in release builds.

The source tree intentionally does not include plaintext credentials or unlock
codes. Internal test credentials are stored only inside AES-GCM encrypted
bundles, and `index.json` stores only `sha256(unlock_code)`.

A release may ship:

- `index.json`: maps `sha256(unlock_code)` to an encrypted bundle file.
- `*.bundle`: AES-GCM encrypted built-in model payloads.

The current MVP ships one internal DeepSeek provider:

```json
{
  "license_id": "internal_deepseek",
  "label": "Internal DeepSeek",
  "providers": [
    {
      "provider": "deepseek",
      "api_key": "sk-...",
      "models": ["deepseek-v4-flash"],
      "default_model": "deepseek-v4-flash"
    }
  ]
}
```

The runtime only persists non-secret activation metadata under
`desktop.builtinModel`; it never writes decrypted API keys to user config.
