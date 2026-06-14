"""Phase 39 stored thread audit — method registration, stored fallbacks,
and safety checks (no AgentLoop, no direct bridge imports).
"""

from __future__ import annotations

import re
from pathlib import Path

_ROOT = Path(__file__).parents[2]
_MIQI = _ROOT / "miqi"

_PHASE39_METHODS = [
    "thread/list",
    "thread/read",
    "thread/turns/list",
    "thread/export",
    "thread/import",
]


def _registered_methods() -> set[str]:
    methods: set[str] = set()
    pattern = re.compile(r'register_method\(\s*"([^"]+)"')
    for py_file in _MIQI.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        methods.update(pattern.findall(text))
    return methods


def test_phase39_methods_registered():
    registered = _registered_methods()
    missing = [method for method in _PHASE39_METHODS if method not in registered]
    assert not missing, f"Missing Phase 39 methods: {missing}"


def test_thread_read_and_turns_list_do_not_unconditionally_require_live_session():
    path = _MIQI / "runtime" / "thread_app_handlers.py"
    text = path.read_text(encoding="utf-8")
    read_pos = text.index('async def _thread_read')
    turns_pos = text.index('async def _thread_turns_list')
    items_pos = text.index('async def _thread_turns_items_list')
    read_body = text[read_pos:turns_pos]
    turns_body = text[turns_pos:items_pos]
    assert "_stored" in read_body or "stored" in read_body.lower()
    assert "_stored" in turns_body or "stored" in turns_body.lower()


def test_phase39_runtime_modules_do_not_import_bridge_server():
    runtime_dir = _MIQI / "runtime"
    offenders: list[str] = []
    for module_name in [
        "stored_runtime.py",
        "thread_export.py",
        "thread_app_handlers.py",
    ]:
        path = runtime_dir / module_name
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "import miqi.bridge.server" in text or "from miqi.bridge.server import" in text:
            offenders.append(module_name)
    assert not offenders


def test_phase39_no_agentloop_or_process_direct_in_runtime_thread_paths():
    offenders = []
    for path in [
        _MIQI / "runtime" / "thread_app_handlers.py",
        _MIQI / "runtime" / "stored_runtime.py",
        _MIQI / "runtime" / "thread_export.py",
    ]:
        if not path.exists():
            continue
        text = path.read_text(encoding="utf-8")
        if "AgentLoop(" in text or "process_direct(" in text:
            offenders.append(path.name)
    assert not offenders


def test_thread_turns_items_list_still_explicitly_unsupported():
    path = _MIQI / "runtime" / "thread_app_handlers.py"
    text = path.read_text(encoding="utf-8")
    assert "thread/turns/items/list is not supported yet" in text
    assert "UNSUPPORTED_METHOD" in text
