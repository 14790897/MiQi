import os
import tempfile
from pathlib import Path

import pytest

from miqi.paths import get_miqi_home


def test_pytest_basetemp_is_inside_repo(request, tmp_path):
    """Regression: tmp_path must be created under a repository-local base temp."""
    repo_root = Path(request.config.rootpath).resolve()
    resolved = tmp_path.resolve()
    assert resolved.is_relative_to(repo_root)
    assert ".pytest-basetemp" in str(resolved)


def test_global_fixture_isolates_home_and_temp(tmp_path):
    root = tmp_path.resolve()

    assert get_miqi_home().is_relative_to(root)
    assert Path(os.environ["HOME"]).resolve().is_relative_to(root)
    assert Path(tempfile.gettempdir()).resolve().is_relative_to(root)


@pytest.mark.self_managed_env
def test_self_managed_env_still_uses_test_owned_paths(monkeypatch, tmp_path):
    home = tmp_path / "managed-home"
    miqi_home = tmp_path / "managed-miqi"
    temp_dir = tmp_path / "managed-temp"
    home.mkdir()
    temp_dir.mkdir()

    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    monkeypatch.setenv("HOME", str(home))
    monkeypatch.setenv("USERPROFILE", str(home))
    monkeypatch.setenv("TEMP", str(temp_dir))
    monkeypatch.setenv("TMP", str(temp_dir))
    monkeypatch.setenv("TMPDIR", str(temp_dir))
    monkeypatch.setattr(tempfile, "tempdir", str(temp_dir))

    assert get_miqi_home() == miqi_home.resolve()
    assert Path(tempfile.gettempdir()).resolve() == temp_dir.resolve()
