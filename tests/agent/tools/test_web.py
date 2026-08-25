"""WebSearchTool provider / fallback chain tests (#561).

Covers: provider normalization (hybrid→auto), the auto fallback chain
(Tavily → Brave → DDGS), error classification (RATE_LIMIT/AUTH/NO_RESULT),
the model-facing string format, and the legacy api_key → brave_api_key
config migration.
"""

from miqi.agent.tools.web import (
    BraveProvider,
    DDGSProvider,
    SearchProviderManager,
    SearchResult,
    TavilyProvider,
    WebSearchTool,
)
from miqi.config.loader import _migrate_config


# ── provider normalization ───────────────────────────────────────────────


def test_provider_auto_is_default():
    manager = SearchProviderManager("auto")
    assert manager.provider == "auto"


def test_provider_hybrid_maps_to_auto():
    manager = SearchProviderManager("hybrid")
    assert manager.provider == "auto"


def test_provider_unknown_maps_to_auto():
    manager = SearchProviderManager("nonsense")
    assert manager.provider == "auto"


def test_provider_explicit_brave_stays_brave():
    manager = SearchProviderManager("brave")
    assert manager.provider == "brave"


def test_auto_chain_uses_only_configured_key_providers():
    manager = SearchProviderManager("auto", tavily_api_key="tv-key")
    chain = manager._chain()
    assert [p.name for p in chain] == ["tavily", "ddgs"]

    manager2 = SearchProviderManager("auto", brave_api_key="bs-key")
    assert [p.name for p in manager2._chain()] == ["brave", "ddgs"]

    manager3 = SearchProviderManager("auto", tavily_api_key="t", brave_api_key="b")
    assert [p.name for p in manager3._chain()] == ["tavily", "brave", "ddgs"]

    manager4 = SearchProviderManager("auto")
    assert [p.name for p in manager4._chain()] == ["ddgs"]


# ── fallback chain behaviour ─────────────────────────────────────────────


async def test_auto_falls_through_on_rate_limit(monkeypatch):
    calls = []

    class _Tavily(TavilyProvider):
        async def search(self, query, count):
            calls.append("tavily")
            return SearchResult(False, error_type="RATE_LIMIT")

    class _Brave(BraveProvider):
        async def search(self, query, count):
            calls.append("brave")
            return SearchResult(False, error_type="RATE_LIMIT")

    manager = SearchProviderManager("auto", tavily_api_key="t", brave_api_key="b")
    manager._chain = lambda: [_Tavily("t"), _Brave("b"), DDGSProvider()]

    async def _ok(self, query, count):
        return SearchResult(True, [{"title": "ok", "url": "https://x", "snippet": "s"}])

    monkeypatch.setattr(DDGSProvider, "search", _ok)

    result = await manager.search("q", 5)
    assert result.success
    assert calls == ["tavily", "brave"]


async def test_auto_auth_error_degrades_with_warning(monkeypatch, caplog):
    calls = []

    class _Tavily(TavilyProvider):
        async def search(self, query, count):
            calls.append("tavily")
            return SearchResult(False, error_type="AUTH_ERROR")

    manager = SearchProviderManager("auto", tavily_api_key="bad")
    manager._chain = lambda: [_Tavily("bad"), DDGSProvider()]

    async def _ok(self, query, count):
        return SearchResult(True, [{"title": "ok", "url": "https://x", "snippet": "s"}])

    monkeypatch.setattr(DDGSProvider, "search", _ok)

    result = await manager.search("q", 5)
    assert result.success
    assert calls == ["tavily"]
    assert any("authentication failed" in r.message for r in caplog.records)


async def test_no_result_does_not_fallback(monkeypatch):
    calls = []

    class _Tavily(TavilyProvider):
        async def search(self, query, count):
            calls.append("tavily")
            return SearchResult(True, error_type="NO_RESULT")

    manager = SearchProviderManager("auto", tavily_api_key="t")
    manager._chain = lambda: [_Tavily("t"), DDGSProvider()]
    monkeypatch.setattr(
        DDGSProvider, "search",
        lambda self, query, count: SearchResult(True, [{"title": "x", "url": "https://x", "snippet": ""}]),
    )

    result = await manager.search("q", 5)
    assert result.success and result.error_type == "NO_RESULT"
    assert calls == ["tavily"]  # ddgs never tried


async def test_explicit_provider_does_not_chain(monkeypatch):
    calls = []

    class _Tavily(TavilyProvider):
        async def search(self, query, count):
            calls.append("tavily")
            return SearchResult(False, error_type="RATE_LIMIT")

    manager = SearchProviderManager("tavily", tavily_api_key="t")
    manager._chain = lambda: [_Tavily("t")]
    result = await manager.search("q", 5)
    assert not result.success
    assert calls == ["tavily"]


# ── provider error classification ────────────────────────────────────────


async def test_tavily_401_classified_auth(monkeypatch):
    async def _fake_post(self, url, **kwargs):
        class _R:
            status_code = 401

            def json(self):
                return {}

            def raise_for_status(self):
                return None

        return _R()

    monkeypatch.setattr("miqi.agent.tools.web.httpx.AsyncClient.post", _fake_post)
    result = await TavilyProvider("k").search("q", 5)
    assert not result.success and result.error_type == "AUTH_ERROR"


async def test_tavily_429_classified_rate_limit(monkeypatch):
    async def _fake_post(self, url, **kwargs):
        class _R:
            status_code = 429

            def json(self):
                return {}

            def raise_for_status(self):
                return None

        return _R()

    monkeypatch.setattr("miqi.agent.tools.web.httpx.AsyncClient.post", _fake_post)
    result = await TavilyProvider("k").search("q", 5)
    assert not result.success and result.error_type == "RATE_LIMIT"


async def test_brave_missing_key_is_no_key_error():
    result = await BraveProvider("").search("q", 5)
    assert not result.success and result.error_type == "NO_KEY"
    assert result.provider == "brave"


# ── tool-level string format (model contract) ────────────────────────────


async def test_execute_returns_string_format(monkeypatch):
    async def _fake_search(self, query, count):
        return SearchResult(True, [
            {"title": "T1", "url": "https://example.com/a", "snippet": "s1"},
            {"title": "T2", "url": "https://example.com/b", "snippet": "s2"},
        ])

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)
    tool = WebSearchTool(provider="auto")
    out = await tool.execute("hello")
    assert out.startswith("Results for: hello")
    assert "1. T1" in out and "https://example.com/a" in out and "s1" in out


async def test_execute_all_providers_down_exposes_reason(monkeypatch):
    async def _fake_search(self, query, count):
        return SearchResult(False, error_type="NETWORK", provider="ddgs")

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)
    tool = WebSearchTool(provider="auto")
    out = await tool.execute("hello")
    assert out.startswith("Error:")
    assert "网络搜索失败" in out
    assert "网络连接失败" in out  # actionable reason surfaced (#804)
    assert "web_fetch" in out


async def test_execute_no_key_exposes_setting_hint(monkeypatch):
    async def _fake_search(self, query, count):
        return SearchResult(False, error_type="NO_KEY", provider="tavily")

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)
    tool = WebSearchTool(provider="auto")
    out = await tool.execute("hello")
    assert "未配置 Tavily API key，请在设置中填写" in out


async def test_execute_auth_error_exposes_bad_key_hint(monkeypatch):
    async def _fake_search(self, query, count):
        return SearchResult(False, error_type="AUTH_ERROR", provider="brave")

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)
    tool = WebSearchTool(provider="auto")
    out = await tool.execute("hello")
    assert "Brave API key 无效" in out


async def test_manager_chain_exhausted_surfaces_last_failure(monkeypatch):
    """Chain exhaustion must carry the last real failure, not a generic error."""

    class _Tavily(TavilyProvider):
        async def search(self, query, count):
            return SearchResult(False, error_type="NETWORK")

    class _Brave(BraveProvider):
        async def search(self, query, count):
            return SearchResult(False, error_type="RATE_LIMIT")

    manager = SearchProviderManager("auto", tavily_api_key="t", brave_api_key="b")
    manager._chain = lambda: [_Tavily("t"), _Brave("b")]
    result = await manager.search("q", 5)
    assert not result.success
    assert result.error_type == "RATE_LIMIT"
    assert result.provider == "brave"


async def test_execute_no_result_message(monkeypatch):
    async def _fake_search(self, query, count):
        return SearchResult(True, error_type="NO_RESULT")

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)
    tool = WebSearchTool(provider="auto")
    assert await tool.execute("qqq") == "No results for: qqq"


# ── legacy config migration (#561) ───────────────────────────────────────


def test_migrate_old_api_key_to_brave_api_key():
    data = {
        "tools": {
            "web": {
                "search": {"provider": "brave", "api_key": "old-brave-key"},
            }
        }
    }
    migrated = _migrate_config(data)
    search = migrated["tools"]["web"]["search"]
    assert search["brave_api_key"] == "old-brave-key"
    assert "api_key" not in search


def test_migrate_keeps_existing_brave_key():
    data = {
        "tools": {
            "web": {
                "search": {"provider": "auto", "api_key": "old", "brave_api_key": "new"},
            }
        }
    }
    migrated = _migrate_config(data)
    search = migrated["tools"]["web"]["search"]
    assert search["brave_api_key"] == "new"
    assert "api_key" not in search


# ── fast 模式扇出搜索走配置链（#804）──────────────────────────────────


async def test_parallel_search_uses_manager_chain_first(monkeypatch):
    """fast 扇出：配置链（Tavily→Brave→DDGS）优先，成功就不碰 ddgs 区域兜底。"""
    calls = []

    async def _fake_search(self, query, count):
        calls.append("manager")
        return SearchResult(True, [
            {"title": "T1", "url": "https://example.com/a", "snippet": "s1"},
        ])

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)

    async def _boom(query, n_queries, n):
        raise AssertionError("ddgs fallback must not run when chain succeeds")

    monkeypatch.setattr(
        "miqi.agent.search_orchestrator._ddgs_regional_search", _boom
    )
    tool = WebSearchTool(provider="auto")
    blocks = await tool._parallel_search("hello", n_queries=2, n=5)
    assert calls == ["manager"]
    assert len(blocks) == 1
    assert blocks[0].startswith("Results for: hello")
    assert "https://example.com/a" in blocks[0]


async def test_parallel_search_falls_back_to_regional_ddgs(monkeypatch):
    """fast 扇出：配置链失败/空结果 → 回退 ddgs 区域变体。"""
    calls = []

    async def _fake_search(self, query, count):
        calls.append("manager")
        return SearchResult(False, error_type="NETWORK", provider="ddgs")

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)

    async def _fake_ddgs(query, n_queries, n):
        calls.append("ddgs")
        return ["Results for: hello (region: 全球)\n- T\n  https://x.com\n  s"]

    monkeypatch.setattr(
        "miqi.agent.search_orchestrator._ddgs_regional_search", _fake_ddgs
    )
    tool = WebSearchTool(provider="auto")
    blocks = await tool._parallel_search("hello", n_queries=2, n=5)
    assert calls == ["manager", "ddgs"]
    assert blocks and "https://x.com" in blocks[0]


async def test_parallel_search_falls_back_on_empty_chain_result(monkeypatch):
    """fast 扇出：配置链成功但空结果 → 也回退 ddgs（否则空结果直接丢失）。"""

    async def _fake_search(self, query, count):
        return SearchResult(True, error_type="NO_RESULT")

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)

    async def _fake_ddgs(query, n_queries, n):
        return ["fallback block"]

    monkeypatch.setattr(
        "miqi.agent.search_orchestrator._ddgs_regional_search", _fake_ddgs
    )
    tool = WebSearchTool(provider="auto")
    blocks = await tool._parallel_search("hello", n_queries=1, n=5)
    assert blocks == ["fallback block"]


async def test_parallel_search_all_down_exposes_reason(monkeypatch):
    """fast 扇出：配置链 + ddgs 全失败 → 透出失败原因，不让模型误读为\"无结果\"。"""

    async def _fake_search(self, query, count):
        return SearchResult(False, error_type="NO_KEY", provider="tavily")

    monkeypatch.setattr(SearchProviderManager, "search", _fake_search)

    async def _empty_ddgs(query, n_queries, n):
        return []

    monkeypatch.setattr(
        "miqi.agent.search_orchestrator._ddgs_regional_search", _empty_ddgs
    )
    tool = WebSearchTool(provider="auto")
    blocks = await tool._parallel_search("hello", n_queries=2, n=5)
    assert len(blocks) == 1
    assert "未配置 Tavily API key，请在设置中填写" in blocks[0]
