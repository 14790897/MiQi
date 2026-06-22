"""Canonical path resolution for MiQi-owned files and directories."""

from __future__ import annotations

import os
from pathlib import Path

MIQI_HOME_ENV = "MIQI_HOME"
DEFAULT_HOME_NAME = ".miqi"
LEGACY_HOME_NAME = ".assistant"


def get_miqi_home() -> Path:
    configured = os.environ.get(MIQI_HOME_ENV, "").strip()
    if configured:
        return Path(configured).expanduser().resolve()
    return (Path.home() / DEFAULT_HOME_NAME).resolve()


def get_config_path() -> Path:
    return get_miqi_home() / "config.json"


def get_legacy_data_dir() -> Path:
    return (Path.home() / LEGACY_HOME_NAME).resolve()


def get_legacy_config_path() -> Path:
    return get_legacy_data_dir() / "config.json"
