"""Phase 38 audit tests — config, feature profile, and permission profile parity."""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_MIQI = _ROOT / "miqi"

_PHASE38_METHODS = [
    "model/list",
    "modelProvider/capabilities/read",
    "experimentalFeature/list",
    "experimentalFeature/enablement/set",
    "permissionProfile/list",
    "config/read",
    "config/batchWrite",
]

_PHASE38_LEGACY_METHODS = [
    "providers.list",
    "providers.test",
    "providers.update",
    "permissions.get",
    "permissions.update",
    "permissions.permanent.add",
    "permissions.permanent.remove",
    "config.get",
    "config.update",
]

_PHASE38_HANDLER_MODULES = [
    "config_app_handlers.py",
    "model_app_handlers.py",
    "feature_app_handlers.py",
    "permission_profile_app_handlers.py",
]


def _registered_methods() -> set[str]:
    methods: set[str] = set()
    pattern = re.compile(r'register_method\(\s*"([^"]+)"')
    for py_file in _MIQI.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        methods.update(pattern.findall(text))
    return methods


def test_phase38_codex_config_feature_methods_registered():
    registered = _registered_methods()
    missing = [method for method in _PHASE38_METHODS if method not in registered]
    assert not missing, f"Missing Phase 38 Codex methods: {missing}"


def test_phase38_legacy_methods_still_registered():
    registered = _registered_methods()
    missing = [method for method in _PHASE38_LEGACY_METHODS if method not in registered]
    assert not missing, f"Missing Phase 38 legacy methods: {missing}"


def test_phase38_runtime_handlers_do_not_import_bridge_server_directly():
    """New Phase 38 handler modules and config_handlers.py must not import
    miqi.bridge.server directly."""
    runtime_dir = _MIQI / "runtime"
    forbidden_patterns = ["import miqi.bridge.server", "from miqi.bridge.server import"]
    offenders: list[str] = []

    # Include config_handlers.py in the check.
    for module_name in _PHASE38_HANDLER_MODULES + ["config_handlers.py"]:
        path = runtime_dir / module_name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        for forbidden in forbidden_patterns:
            if forbidden in text:
                offenders.append(module_name)
                break

    assert not offenders, (
        f"Phase 38 handler modules import miqi.bridge.server directly: {offenders}. "
        f"Use get_bridge_state(registry) instead."
    )


def test_phase38_no_raw_secret_values_in_model_or_config_handlers():
    """New model/config handlers must not directly return raw API keys/tokens."""
    runtime_dir = _MIQI / "runtime"
    offenders: list[str] = []

    for module_name in ["config_app_handlers.py", "model_app_handlers.py"]:
        path = runtime_dir / module_name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        # Look for lines that return or yield with api_key without redaction
        for line in text.splitlines():
            stripped = line.strip()
            if "return" in stripped and "api_key" in stripped.lower():
                if "hint" not in stripped.lower() and "redact" not in stripped.lower():
                    offenders.append(f"{module_name}: {stripped[:80]}")

    assert not offenders, (
        f"Potential raw secret exposure in Phase 38 handlers: {offenders}"
    )
