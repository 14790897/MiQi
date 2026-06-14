"""Diagnostic handlers for AppServer dispatch.

Phase 35.8: Migrates python.check from bridge legacy handlers to
AppServer async handlers.
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any

from miqi.runtime.app_server import AppServerError


async def python_check_handler(
    request_id: str,
    params: dict[str, Any],
    client_id: str,
    session_id: str | None,
    registry: Any,
) -> dict[str, Any]:
    """Check if Python and MiQi dependencies are available."""
    issues = []

    # Check Python version
    py_ver = sys.version_info
    if py_ver < (3, 11):
        issues.append(
            f"Python {py_ver.major}.{py_ver.minor} is too old (need >= 3.11)",
        )

    # Check key dependencies
    for mod in ("pydantic", "httpx", "loguru"):
        try:
            importlib.import_module(mod)
        except ImportError:
            issues.append(f"Missing dependency: {mod}")

    return {"result": {
        "ok": len(issues) == 0,
        "python_version": f"{py_ver.major}.{py_ver.minor}.{py_ver.micro}",
        "issues": issues,
        "config_exists": (Path.home() / ".miqi" / "config.json").exists(),
    }}
