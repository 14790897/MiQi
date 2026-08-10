"""WebSearchTool provider fallback tests (#638).

Verifies that brave/hybrid without an API key degrades to ddgs both on the
tool instance and at the configuration owner (saved ``tools.web.search.provider``),
so later sessions/subagents read ``ddgs`` after a reload.
"""

from miqi.agent.tools.web import WebSearchTool
from miqi.config.loader import get_config_path, load_config, save_config
from miqi.config.schema import Config


def _write_config_with_provider(provider: str) -> None:
    config = Config()
    config.tools.web.search.provider = provider
    save_config(config)


def test_brave_without_key_falls_back_and_persists_config(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    _write_config_with_provider("brave")

    tool = WebSearchTool(provider="brave", api_key=None)

    assert tool.provider == "ddgs"
    # Persisted at the configuration owner: a reload reads ddgs.
    reloaded = load_config()
    assert reloaded.tools.web.search.provider == "ddgs"


def test_hybrid_without_key_falls_back_and_persists_config(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    _write_config_with_provider("hybrid")

    tool = WebSearchTool(provider="hybrid", api_key=None)

    assert tool.provider == "ddgs"
    reloaded = load_config()
    assert reloaded.tools.web.search.provider == "ddgs"


def test_ddgs_stays_ddgs_and_config_untouched(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    _write_config_with_provider("ddgs")

    tool = WebSearchTool(provider="ddgs", api_key=None)

    assert tool.provider == "ddgs"
    reloaded = load_config()
    assert reloaded.tools.web.search.provider == "ddgs"


def test_brave_with_key_keeps_brave_and_config_untouched():
    _write_config_with_provider("brave")

    tool = WebSearchTool(provider="brave", api_key="test-key")

    assert tool.provider == "brave"
    reloaded = load_config()
    assert reloaded.tools.web.search.provider == "brave"


def test_brave_with_env_key_keeps_brave(monkeypatch):
    _write_config_with_provider("brave")
    monkeypatch.setenv("BRAVE_API_KEY", "env-key")

    tool = WebSearchTool(provider="brave", api_key=None)

    assert tool.provider == "brave"
    reloaded = load_config()
    assert reloaded.tools.web.search.provider == "brave"


def test_no_config_file_creates_nothing_on_ddgs(monkeypatch):
    monkeypatch.delenv("BRAVE_API_KEY", raising=False)
    assert not get_config_path().exists()

    tool = WebSearchTool(provider="ddgs", api_key=None)

    assert tool.provider == "ddgs"
    # No fallback → no config file created as a side effect.
    assert not get_config_path().exists()
