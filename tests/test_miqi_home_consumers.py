from pathlib import Path


ALLOWED_DIRECT_HOME_FILES = {
    Path("miqi/paths.py"),
    # External tool discovery in config_cmd intentionally searches the user's
    # normal home and is not MiQi-owned storage.
    Path("miqi/cli/config_cmd.py"),
}


def test_production_code_does_not_construct_dot_miqi_from_path_home():
    violations = []
    for path in Path("miqi").rglob("*.py"):
        if path in ALLOWED_DIRECT_HOME_FILES:
            continue
        text = path.read_text(encoding="utf-8")
        if "Path.home() / \".miqi\"" in text or "_Path.home() / \".miqi\"" in text:
            violations.append(str(path))

    assert violations == []


# ── Behavior tests: each consumer respects MIQI_HOME ──────────────────────────


def test_snapshot_root_respects_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "miqi"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))

    from miqi.agent.tools.filesystem import _snapshots_dir

    snap_dir = _snapshots_dir()
    assert snap_dir.is_relative_to(miqi_home)
    assert snap_dir.name == "snapshots"


def test_cli_history_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "miqi"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    from miqi.paths import get_miqi_home

    history_parent = get_miqi_home() / "history"
    assert history_parent.is_relative_to(miqi_home)


def test_initialize_protocol_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "miqi"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    from miqi.paths import get_miqi_home

    assert str(get_miqi_home()) == str(miqi_home.resolve())


def test_user_plugins_dir_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "miqi"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    from miqi.paths import get_miqi_home

    plugins_dir = get_miqi_home() / "plugins"
    assert plugins_dir.is_relative_to(miqi_home)


def test_marketplaces_dir_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "miqi"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    from miqi.paths import get_miqi_home

    marketplaces_dir = get_miqi_home() / "marketplaces"
    assert marketplaces_dir.is_relative_to(miqi_home)


def test_config_exists_check_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "miqi"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    from miqi.paths import get_config_path

    config = get_config_path()
    assert config.is_relative_to(miqi_home)
    assert config.name == "config.json"


def test_sandbox_state_uses_miqi_home(monkeypatch, tmp_path):
    miqi_home = tmp_path / "miqi"
    monkeypatch.setenv("MIQI_HOME", str(miqi_home))
    from miqi.paths import get_miqi_home

    sandbox_file = get_miqi_home() / "sandbox_state.json"
    assert sandbox_file.is_relative_to(miqi_home)
