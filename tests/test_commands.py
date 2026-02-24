import shutil
from pathlib import Path
from unittest.mock import patch

import pytest
from typer.testing import CliRunner

from featherflow.cli.commands import app
from featherflow.config.schema import Config
from featherflow.providers.litellm_provider import LiteLLMProvider
from featherflow.providers.openai_codex_provider import _strip_model_prefix
from featherflow.providers.registry import find_by_model

runner = CliRunner()


@pytest.fixture
def mock_paths():
    """Mock config/workspace paths for test isolation."""
    with patch("featherflow.config.loader.get_config_path") as mock_cp, \
         patch("featherflow.config.loader.save_config") as mock_sc, \
         patch("featherflow.config.loader.load_config"), \
         patch("featherflow.utils.helpers.get_workspace_path") as mock_ws:

        base_dir = Path("./test_onboard_data")
        if base_dir.exists():
            shutil.rmtree(base_dir)
        base_dir.mkdir()

        config_file = base_dir / "config.json"
        workspace_dir = base_dir / "workspace"

        mock_cp.return_value = config_file
        mock_ws.return_value = workspace_dir
        mock_sc.side_effect = lambda config: config_file.write_text("{}")

        yield config_file, workspace_dir

        if base_dir.exists():
            shutil.rmtree(base_dir)


def test_onboard_fresh_install(mock_paths):
    """No existing config — should create from scratch."""
    config_file, workspace_dir = mock_paths

    result = runner.invoke(app, ["onboard"])

    assert result.exit_code == 0
    assert "Created config" in result.stdout
    assert "Created workspace" in result.stdout
    assert "featherflow is ready" in result.stdout
    assert config_file.exists()
    assert (workspace_dir / "AGENTS.md").exists()
    assert (workspace_dir / "memory" / "MEMORY.md").exists()


def test_onboard_existing_config_refresh(mock_paths):
    """Config exists, user declines overwrite — should refresh (load-merge-save)."""
    config_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "existing values preserved" in result.stdout
    assert workspace_dir.exists()
    assert (workspace_dir / "AGENTS.md").exists()


def test_onboard_existing_config_overwrite(mock_paths):
    """Config exists, user confirms overwrite — should reset to defaults."""
    config_file, workspace_dir = mock_paths
    config_file.write_text('{"existing": true}')

    result = runner.invoke(app, ["onboard"], input="y\n")

    assert result.exit_code == 0
    assert "Config already exists" in result.stdout
    assert "Config reset to defaults" in result.stdout
    assert workspace_dir.exists()


def test_onboard_existing_workspace_safe_create(mock_paths):
    """Workspace exists — should not recreate, but still add missing templates."""
    config_file, workspace_dir = mock_paths
    workspace_dir.mkdir(parents=True)
    config_file.write_text("{}")

    result = runner.invoke(app, ["onboard"], input="n\n")

    assert result.exit_code == 0
    assert "Created workspace" not in result.stdout
    assert "Created AGENTS.md" in result.stdout
    assert (workspace_dir / "AGENTS.md").exists()


def test_config_matches_github_copilot_codex_with_hyphen_prefix():
    config = Config()
    config.agents.defaults.model = "github-copilot/gpt-5.3-codex"

    assert config.get_provider_name() == "github_copilot"


def test_config_matches_openai_codex_with_hyphen_prefix():
    config = Config()
    config.agents.defaults.model = "openai-codex/gpt-5.1-codex"

    assert config.get_provider_name() == "openai_codex"


def test_find_by_model_prefers_explicit_prefix_over_generic_codex_keyword():
    spec = find_by_model("github-copilot/gpt-5.3-codex")

    assert spec is not None
    assert spec.name == "github_copilot"


def test_litellm_provider_canonicalizes_github_copilot_hyphen_prefix():
    provider = LiteLLMProvider(default_model="github-copilot/gpt-5.3-codex")

    resolved = provider._resolve_model("github-copilot/gpt-5.3-codex")

    assert resolved == "github_copilot/gpt-5.3-codex"


def test_openai_codex_strip_prefix_supports_hyphen_and_underscore():
    assert _strip_model_prefix("openai-codex/gpt-5.1-codex") == "gpt-5.1-codex"
    assert _strip_model_prefix("openai_codex/gpt-5.1-codex") == "gpt-5.1-codex"


def test_status_with_existing_config_no_crash(monkeypatch, tmp_path):
    """Status should not crash when config file exists."""
    config_path = tmp_path / "config.json"
    config_path.write_text("{}", encoding="utf-8")

    config = Config()
    config.providers.openrouter.api_key = "sk-or-v1-test"
    config.agents.defaults.model = "anthropic/claude-opus-4-5"

    monkeypatch.setattr("featherflow.config.loader.get_config_path", lambda: config_path)
    monkeypatch.setattr("featherflow.config.loader.load_config", lambda: config)

    result = runner.invoke(app, ["status"])

    assert result.exit_code == 0
    assert "FeatherFlow Status" in result.stdout
    assert "OpenRouter" in result.stdout


def test_config_heartbeat_defaults_and_alias_parsing():
    default_config = Config()
    assert default_config.heartbeat.enabled is True
    assert default_config.heartbeat.interval_seconds == 1800

    parsed = Config.model_validate(
        {"heartbeat": {"enabled": False, "intervalSeconds": 90}}
    )
    assert parsed.heartbeat.enabled is False
    assert parsed.heartbeat.interval_seconds == 90


def test_agent_command_passes_runtime_configs(monkeypatch, tmp_path):
    config = Config()
    config.providers.openrouter.api_key = "sk-or-v1-test"
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)

    captured: dict = {}

    class FakeCronService:
        def __init__(self, _store_path):
            self.on_job = None

    class FakeAgentLoop:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.channels_config = kwargs.get("channels_config")

        async def process_direct(self, *_args, **_kwargs):
            return "ok"

        async def close_mcp(self):
            return None

    monkeypatch.setattr("featherflow.config.loader.load_config", lambda: config)
    monkeypatch.setattr("featherflow.config.loader.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("featherflow.cli.commands._make_provider", lambda _cfg: object())
    monkeypatch.setattr("featherflow.cron.service.CronService", FakeCronService)
    monkeypatch.setattr("featherflow.agent.loop.AgentLoop", FakeAgentLoop)

    result = runner.invoke(app, ["agent", "-m", "hello"])

    assert result.exit_code == 0
    assert captured["agent_name"] == config.agents.defaults.name
    assert captured["reflect_after_tool_calls"] == config.agents.defaults.reflect_after_tool_calls
    assert captured["web_config"] is config.tools.web
    assert captured["memory_config"] is config.agents.memory
    assert captured["self_improvement_config"] is config.agents.self_improvement
    assert captured["session_config"] is config.agents.sessions


def test_cron_run_passes_runtime_configs(monkeypatch, tmp_path):
    config = Config()
    config.providers.openrouter.api_key = "sk-or-v1-test"
    config.agents.defaults.workspace = str(tmp_path / "workspace")
    (tmp_path / "workspace").mkdir(parents=True, exist_ok=True)

    captured: dict = {}

    class FakeCronService:
        def __init__(self, _store_path):
            self.on_job = None

        async def run_job(self, _job_id, force=False):
            return bool(force)

    class FakeAgentLoop:
        def __init__(self, **kwargs):
            captured.update(kwargs)
            self.channels_config = kwargs.get("channels_config")

        async def process_direct(self, *_args, **_kwargs):
            return "ok"

        async def close_mcp(self):
            return None

        def stop(self):
            return None

    monkeypatch.setattr("featherflow.config.loader.load_config", lambda: config)
    monkeypatch.setattr("featherflow.config.loader.get_data_dir", lambda: tmp_path)
    monkeypatch.setattr("featherflow.cli.commands._make_provider", lambda _cfg: object())
    monkeypatch.setattr("featherflow.cron.service.CronService", FakeCronService)
    monkeypatch.setattr("featherflow.agent.loop.AgentLoop", FakeAgentLoop)

    result = runner.invoke(app, ["cron", "run", "demo", "--force"])

    assert result.exit_code == 0
    assert "Job executed" in result.stdout
    assert captured["agent_name"] == config.agents.defaults.name
    assert captured["reflect_after_tool_calls"] == config.agents.defaults.reflect_after_tool_calls
    assert captured["web_config"] is config.tools.web
    assert captured["memory_config"] is config.agents.memory
    assert captured["self_improvement_config"] is config.agents.self_improvement
    assert captured["session_config"] is config.agents.sessions
