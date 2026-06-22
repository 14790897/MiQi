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
