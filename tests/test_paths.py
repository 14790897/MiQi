from pathlib import Path

from miqi.paths import (
    get_config_path,
    get_legacy_config_path,
    get_legacy_data_dir,
    get_miqi_home,
)


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


from miqi.config.loader import load_config, save_config
from miqi.config.schema import Config
from miqi.utils.helpers import get_data_path, get_workspace_path


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
