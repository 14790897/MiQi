"""Configuration loading utilities."""

import json
from pathlib import Path

from loguru import logger

from featherflow.config.schema import Config


def get_config_path() -> Path:
    """Get default config path, preferring ~/.featherflow/config.json with legacy fallback."""
    home = Path.home()
    preferred = home / ".featherflow" / "config.json"
    legacy = home / ".assistant" / "config.json"
    if preferred.exists() or not legacy.exists():
        return preferred
    return legacy


def get_data_dir() -> Path:
    """Get runtime data directory."""
    from featherflow.utils.helpers import get_data_path
    return get_data_path()


def load_config(config_path: Path | None = None) -> Config:
    """
    Load configuration from file or create default.

    Args:
        config_path: Optional path to config file. Uses default if not provided.

    Returns:
        Loaded configuration object.
    """
    path = config_path or get_config_path()

    if path.exists():
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
            data = _migrate_config(data)
            return Config.model_validate(data)
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


def _migrate_config(data: dict) -> dict:
    """Migrate old config formats to current."""
    # Move tools.exec.restrictToWorkspace → tools.restrictToWorkspace
    tools = data.get("tools", {})
    exec_cfg = tools.get("exec", {})
    if "restrictToWorkspace" in exec_cfg and "restrictToWorkspace" not in tools:
        tools["restrictToWorkspace"] = exec_cfg.pop("restrictToWorkspace")
    return data
