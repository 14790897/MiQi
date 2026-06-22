"""Contract and integration tests for miqi.paths path resolution."""

from pathlib import Path

from miqi.config.loader import load_config, save_config
from miqi.config.schema import Config
from miqi.paths import (
    get_config_path,
    get_legacy_config_path,
    get_legacy_data_dir,
    get_miqi_home,
)
from miqi.utils.helpers import get_data_path, get_workspace_path


def test_miqi_home_defaults_to_dot_miqi(monkeypatch, tmp_path):
    monkeypatch.delenv("MIQI_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    assert get_miqi_home() == (tmp_path / "home" / ".miqi").resolve()


def test_miqi_home_uses_absolute_override(monkeypatch, tmp_path):
    configured = tmp_path / "custom-miqi"
    monkeypatch.setenv("MIQI_HOME", str(configured))

    assert get_miqi_home() == configured.resolve()


def test_miqi_home_resolves_relative_override(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("MIQI_HOME", "state/miqi")

    assert get_miqi_home() == (tmp_path / "state" / "miqi").resolve()


def test_blank_miqi_home_uses_default(monkeypatch, tmp_path):
    monkeypatch.setenv("MIQI_HOME", "   ")
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    assert get_miqi_home() == (tmp_path / "home" / ".miqi").resolve()


def test_config_and_legacy_paths(monkeypatch, tmp_path):
    monkeypatch.setenv("MIQI_HOME", str(tmp_path / "miqi"))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    assert get_config_path() == (tmp_path / "miqi" / "config.json").resolve()
    assert get_legacy_data_dir() == (tmp_path / "home" / ".assistant").resolve()
    assert get_legacy_config_path() == (
        tmp_path / "home" / ".assistant" / "config.json"
    ).resolve()


def test_path_getters_do_not_create_directories(monkeypatch, tmp_path):
    configured = tmp_path / "does-not-exist"
    monkeypatch.setenv("MIQI_HOME", str(configured))

    assert get_miqi_home() == configured.resolve()
    assert not configured.exists()


def test_data_path_uses_miqi_home_when_configured(monkeypatch, tmp_path):
    """When MIQI_HOME is set explicitly, get_data_path follows it."""
    miqi_home = tmp_path / "configured-miqi"
    legacy = tmp_path / "home" / ".assistant"
    legacy.mkdir(parents=True)
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    assert get_data_path() == miqi_home.resolve()


def test_data_path_defaults_to_dot_miqi_without_legacy(monkeypatch, tmp_path):
    """Fresh install: no MIQI_HOME and no legacy dir -> default ~/.miqi."""
    monkeypatch.delenv("MIQI_HOME", raising=False)
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: tmp_path / "home"))

    data_path = get_data_path()

    assert data_path == (tmp_path / "home" / ".miqi").resolve()


def test_data_path_falls_back_to_legacy_assistant(monkeypatch, tmp_path):
    """Legacy install: no MIQI_HOME but ~/.assistant exists -> use legacy."""
    monkeypatch.delenv("MIQI_HOME", raising=False)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    legacy = home / ".assistant"
    legacy.mkdir(parents=True)

    data_path = get_data_path()

    assert data_path == legacy.resolve()


def test_data_path_prefers_miqi_when_both_homes_exist(monkeypatch, tmp_path):
    """If both legacy and current home exist, prefer the current ~/.miqi."""
    monkeypatch.delenv("MIQI_HOME", raising=False)
    home = tmp_path / "home"
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: home))
    legacy = home / ".assistant"
    default_home = home / ".miqi"
    legacy.mkdir(parents=True)
    default_home.mkdir(parents=True)

    data_path = get_data_path()

    assert data_path == default_home.resolve()


def test_config_loader_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "isolated"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    config = Config()

    save_config(config)

    assert (miqi_home / "config.json").is_file()
    assert load_config().model_dump() == config.model_dump()


def test_data_and_default_workspace_use_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "isolated"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))

    assert get_data_path() == miqi_home.resolve()
    assert get_workspace_path() == (miqi_home / "workspace").resolve()


def test_default_config_workspace_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "isolated"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))

    assert Config().agents.defaults.workspace == "~/.miqi/workspace"
    assert Config().workspace_path == (miqi_home / "workspace").resolve()


def test_explicit_workspace_is_not_rebased_to_miqi_home(monkeypatch, tmp_path):
    monkeypatch.setenv("MIQI_HOME", str(tmp_path / "isolated"))
    config = Config()
    config.agents.defaults.workspace = str(tmp_path / "explicit-workspace")

    assert config.workspace_path == (tmp_path / "explicit-workspace").resolve()
