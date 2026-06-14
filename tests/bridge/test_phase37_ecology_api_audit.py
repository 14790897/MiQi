from __future__ import annotations

import re
from pathlib import Path


_ROOT = Path(__file__).parents[2]
_MIQI = _ROOT / "miqi"

_PHASE37_METHODS = [
    "skills/list",
    "skills/extraRoots/set",
    "hooks/list",
    "marketplace/add",
    "marketplace/remove",
    "marketplace/upgrade",
    "plugin/list",
    "plugin/installed",
    "plugin/read",
    "plugin/skill/read",
    "plugin/install",
    "plugin/uninstall",
    "mcpServerStatus/list",
    "config/mcpServer/reload",
    "mcpServer/resource/read",
    "mcpServer/tool/call",
]


def _registered_methods() -> set[str]:
    methods: set[str] = set()
    pattern = re.compile(r'register_method\(\s*"([^"]+)"')
    for py_file in _MIQI.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        methods.update(pattern.findall(text))
    return methods


def test_phase37_codex_ecology_methods_registered():
    registered = _registered_methods()
    missing = [method for method in _PHASE37_METHODS if method not in registered]
    assert not missing, f"Missing Phase 37 ecology methods: {missing}"


def test_phase37_legacy_miqi_ecology_methods_still_registered():
    registered = _registered_methods()
    for method in [
        "plugins.list",
        "plugins.install",
        "plugins.uninstall",
        "plugins.toggle",
        "mcp.list",
        "mcp.upsert",
        "mcp.delete",
        "skills.list",
        "skills.get",
        "skills.open_folder",
        "skills.create",
        "skills.upload",
        "skills.delete",
    ]:
        assert method in registered


def test_phase37_no_ecology_handler_imports_bridge_server_directly():
    runtime_dir = _MIQI / "runtime"
    forbidden = "import miqi.bridge.server"
    offenders = []
    for name in [
        "plugin_app_handlers.py",
        "mcp_app_handlers.py",
        "skills_app_handlers.py",
    ]:
        path = runtime_dir / name
        if path.exists() and forbidden in path.read_text(encoding="utf-8"):
            offenders.append(name)
    assert not offenders, f"Runtime AppServer ecology handlers import bridge server: {offenders}"
