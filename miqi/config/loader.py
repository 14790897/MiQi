"""Configuration loading utilities."""

import json
from pathlib import Path

from loguru import logger

from miqi.config.schema import Config
from miqi.paths import get_config_path, get_legacy_config_path


def _get_load_path() -> Path:
    """Return the preferred config path, falling back to legacy for reads only."""
    preferred = get_config_path()
    legacy = get_legacy_config_path()
    if preferred.exists() or not legacy.exists():
        return preferred
    return legacy


def get_data_dir() -> Path:
    """Get runtime data directory."""
    from miqi.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or _get_load_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            config = Config.model_validate(data)

            # Phase 31.X: load permanent approvals into global allowlist
            _init_permanent_approvals(config)

            return config
        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(f"Failed to load config from {path}: {e}")
            logger.warning("Using default configuration.")

    return Config()


def save_config(config: Config, config_path: Path | None = None) -> None:
    """
    Save configuration to file.

    Args:
        config: Configuration to save.
        config_path: Optional path to save to. Uses default if not provided.
    """
    path = config_path or get_config_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    data = config.model_dump(by_alias=True)

    # Prune providers that are completely unconfigured (apiKey="" apiBase=null
    # extraHeaders=null) so they don't clutter the config file.
    providers = data.get("providers", {})
    pruned = {
        k: v
        for k, v in providers.items()
        if v.get("apiKey") or v.get("apiBase") is not None or v.get("extraHeaders")
    }
    if pruned != providers:
        data["providers"] = pruned

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    path.chmod(0o600)  # Restrict to owner only — config contains API keys


def save_config_allowlist(patterns: set[str]) -> None:
    """Persist permanent approval patterns into the user config.

    Adds/updates ``permanent_approvals`` in config.json so that
    approved tool+argument keys survive bridge restarts.
    """
    path = get_config_path()
    try:
        config = load_config(path)
    except Exception:
        config = Config()
    existing: list[str] = list(getattr(config.agents, "permanent_approvals", None) or [])
    merged = sorted(set(existing) | patterns)
    config.agents.permanent_approvals = merged
    save_config(config, path)


def _init_permanent_approvals(config: Config) -> None:
    """Load permanent approval patterns from config into global allowlist."""
    patterns = getattr(config.agents, "permanent_approvals", None) or []
    if patterns:
        try:
            from miqi.agent.command_approval import load_permanent_allowlist
            load_permanent_allowlist(set(patterns))
            logger.debug("Loaded {} permanent approval patterns", len(patterns))
        except Exception as exc:
            logger.warning("Failed to load permanent approvals: {}", exc)


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
