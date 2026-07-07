"""Helpers for wiring runtime sessions to the configured sandbox manager."""

from __future__ import annotations

from pathlib import Path
from typing import Any


def create_sandbox_manager_from_config(
    *,
    config: Any,
    workspace: Path,
) -> Any | None:
    """Create a SandboxManager from config, or None when sandboxing is disabled."""
    sb_cfg = getattr(getattr(config, "tools", None), "sandbox", None)
    if sb_cfg is None or not getattr(sb_cfg, "enabled", True):
        return None

    from miqi.sandbox.manager import SandboxManager

    return SandboxManager(
        workspace=workspace,
        share_net=getattr(sb_cfg, "share_net", False),
        enabled=getattr(sb_cfg, "enabled", True),
        max_sandboxes=getattr(sb_cfg, "max_sandboxes", 10),
        auto_cleanup=getattr(sb_cfg, "auto_cleanup", True),
        wsl_distro=getattr(sb_cfg, "wsl_distro", ""),
        wsl_base_dir=getattr(sb_cfg, "wsl_base_dir", "/tmp/miqi-sandboxes"),
        sandbox_distro_name=getattr(
            sb_cfg,
            "sandbox_distro_name",
            "AIShadowSandbox",
        ),
    )
