"""Web tools: web_search and web_fetch."""

import html
import ipaddress
import asyncio
import json
import logging
import os
import re
import socket
from typing import Any
from urllib.parse import urlparse

import httpx

# Suppress noisy readability tracebacks for empty/broken pages
logging.getLogger("readability.readability").setLevel(logging.WARNING)

from miqi.agent.tools.base import Tool

# Shared constants
USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_7_2) AppleWebKit/537.36"
MAX_REDIRECTS = 5  # Limit redirects to prevent DoS attacks


def _strip_tags(text: str) -> str:
    """Remove HTML tags and decode entities."""
    text = re.sub(r"<script[\s\S]*?</script>", "", text, flags=re.I)
    text = re.sub(r"<style[\s\S]*?</style>", "", text, flags=re.I)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text).strip()


def _normalize(text: str) -> str:
    """Normalize whitespace."""
    text = re.sub(r"[ \t]+", " ", text)
    return re.sub(r"\n{3,}", "\n\n", text).strip()


# Private / reserved IP networks that must never be fetched (SSRF protection).
_PRIVATE_NETWORKS: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = [
    ipaddress.ip_network("127.0.0.0/8"),      # Loopback
    ipaddress.ip_network("10.0.0.0/8"),        # RFC 1918
    ipaddress.ip_network("172.16.0.0/12"),     # RFC 1918
    ipaddress.ip_network("192.168.0.0/16"),    # RFC 1918
    ipaddress.ip_network("169.254.0.0/16"),    # Link-local / cloud metadata (AWS/GCP/Azure)
    ipaddress.ip_network("100.64.0.0/10"),     # Shared address space (RFC 6598)
    ipaddress.ip_network("0.0.0.0/8"),         # "This" network
    ipaddress.ip_network("::1/128"),           # IPv6 loopback
    ipaddress.ip_network("fc00::/7"),          # IPv6 unique local
    ipaddress.ip_network("fe80::/10"),         # IPv6 link-local
]

# Hostnames that must never be fetched regardless of resolved IP.
_BLOCKED_HOSTNAMES: frozenset[str] = frozenset({
    "localhost",
    "metadata.google.internal",
    "metadata.aws.com",
})


def _is_private_host(host: str) -> bool:
    """Return True if *host* is a private/loopback/link-local address.

    Checks literal IPs directly; for hostnames, performs a DNS look-up and
    inspects every returned address.  Blocks known metadata service hostnames
    by name even before resolution.
    """
    host_lower = host.lower()
    if host_lower in _BLOCKED_HOSTNAMES:
        return True

    # Fast path: if the host is already a numeric IP, check it directly.
    try:
        addr = ipaddress.ip_address(host)
        return any(addr in net for net in _PRIVATE_NETWORKS)
    except ValueError:
        pass  # Not a literal IP; fall through to DNS resolution.

    # Resolve the hostname and check every returned address.
    try:
        infos = socket.getaddrinfo(host, None, socket.AF_UNSPEC, socket.SOCK_STREAM)
        for info in infos:
            ip_str = info[4][0].split("%")[0]  # Strip IPv6 zone ID if present.
            try:
                addr = ipaddress.ip_address(ip_str)
                if any(addr in net for net in _PRIVATE_NETWORKS):
                    return True
            except ValueError:
                continue
    except socket.gaierror:
        pass  # DNS lookup failed; let the HTTP layer report the error.

    return False


# Search-engine result/query pages that must never be fetched directly —
# scraping them yields redirect junk, and searching belongs in web_search.
_SEARCH_PAGE_HOSTS = (
    "so.com",
    "sogou.com",
    "bing.com",
    "google.com",
    "google.com.hk",
    "duckduckgo.com",
    "search.brave.com",
    "baidu.com",
)


def _validate_url(url: str) -> tuple[bool, str]:
    """Validate URL: must be http(s) with a publicly routable destination.

    Rejects requests targeting private, loopback, or link-local addresses to
    prevent Server-Side Request Forgery (SSRF) attacks, and rejects search-
    engine query pages (the model should use web_search instead of scraping
    search result HTML).
    """
    try:
        p = urlparse(url)
        if p.scheme not in ("http", "https"):
            return False, f"Only http/https allowed, got '{p.scheme or 'none'}'"
        host = p.hostname
        if not host:
            return False, "Missing domain"
        if _is_private_host(host):
            return False, (
                f"Requests to private/reserved addresses are not allowed (host: {host})"
            )
        host_l = host.lower()
        # Block only search-query pages, never bare roots — docs.google.com/ or
        # pan.baidu.com/ are legitimate pages, not search result pages.
        is_search_host = any(
            host_l == h or host_l.endswith("." + h) for h in _SEARCH_PAGE_HOSTS
        )
        is_query_path = "/search" in p.path or p.path == "/s" or p.path == "/web"
        if is_search_host and is_query_path:
            return False, (
                "Search-engine result pages are blocked — use web_search instead "
                f"of fetching '{host}' query pages"
            )
        return True, ""
    except Exception as e:
        return False, str(e)


class SearchResult:
    """Structured internal result — the tool layer formats it back to a
    string for the model (the model-facing contract stays unchanged)."""

    __slots__ = ("success", "results", "error_type")

    def __init__(
        self,
        success: bool,
        results: list[dict[str, str]] | None = None,
        error_type: str | None = None,
    ):
        self.success = success
        self.results = results or []
        self.error_type = error_type  # RATE_LIMIT | NETWORK | SERVER_ERROR | AUTH_ERROR | NO_RESULT | None


# Error categories that should trigger fallback in auto mode.
_FALLBACK_ERRORS = {"RATE_LIMIT", "NETWORK", "SERVER_ERROR"}
# Errors that must NOT silently fall back (config problems) — log, but
# degrade to the keyless provider once so the user still gets an answer.
_AUTH_ERRORS = {"AUTH_ERROR"}


class SearchProvider:
    """Uniform interface for a search backend."""

    name = "base"

    async def search(self, query: str, count: int) -> SearchResult:  # pragma: no cover - interface
        raise NotImplementedError


def _format_results(query: str, results: list[dict[str, str]]) -> str:
    """Model-facing string format (unchanged from the old tool output)."""
    lines = [f"Results for: {query}\n"]
    for i, item in enumerate(results, 1):
        lines.append(f"{i}. {item.get('title', '')}\n   {item.get('url', '')}")
        if snippet := item.get("snippet"):
            lines.append(f"   {snippet}")
    return "\n".join(lines)


class DDGSProvider(SearchProvider):
    """DuckDuckGo via the ddgs library — keyless, always available."""

    name = "ddgs"

    async def search(self, query: str, count: int) -> SearchResult:
        try:
            from ddgs import DDGS
        except ImportError:
            return SearchResult(False, error_type="NETWORK")

        last_error = "UNKNOWN"
        # Rate limits are usually short-lived (seconds) — retry once with a
        # small backoff before giving up and falling through the chain (#561).
        for attempt in (1, 2):
            try:
                results = await asyncio.to_thread(
                    lambda: list(
                        DDGS().text(
                            query,
                            max_results=count,
                            backend="html,lite",  # multiple endpoints, more resilient
                        )
                    )
                )
                if not results:
                    return SearchResult(True, error_type="NO_RESULT")
                out = []
                for item in results[:count]:
                    href = item.get("href") or item.get("url", "")
                    if not href:
                        continue
                    out.append({
                        "title": item.get("title", ""),
                        "url": href,
                        "snippet": item.get("body") or item.get("description", ""),
                    })
                if not out:
                    return SearchResult(True, error_type="NO_RESULT")
                return SearchResult(True, out)
            except Exception as e:
                cls = type(e).__name__
                if "Ratelimit" in cls:
                    last_error = "RATE_LIMIT"
                elif "Timeout" in cls:
                    last_error = "NETWORK"
                else:
                    last_error = "SERVER_ERROR"
                if attempt == 1:
                    await asyncio.sleep(3.0)  # short backoff before retry
        return SearchResult(False, error_type=last_error)


class BraveProvider(SearchProvider):
    """Brave Search API — requires BRAVE_API_KEY."""

    name = "brave"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, count: int) -> SearchResult:
        if not self.api_key:
            return SearchResult(False, error_type="AUTH_ERROR")
        try:
            async with httpx.AsyncClient() as client:
                r = await client.get(
                    "https://api.search.brave.com/res/v1/web/search",
                    params={"q": query, "count": count},
                    headers={"Accept": "application/json",
                             "X-Subscription-Token": self.api_key},
                    timeout=10.0,
                )
                if r.status_code == 429:
                    return SearchResult(False, error_type="RATE_LIMIT")
                if r.status_code in (401, 403):
                    return SearchResult(False, error_type="AUTH_ERROR")
                if r.status_code >= 500:
                    return SearchResult(False, error_type="SERVER_ERROR")
                r.raise_for_status()

            items = r.json().get("web", {}).get("results", [])
            out = [
                {"title": it.get("title", ""), "url": it.get("url", ""),
                 "snippet": it.get("description", "")}
                for it in items[:count] if it.get("url")
            ]
            if not out:
                return SearchResult(True, error_type="NO_RESULT")
            return SearchResult(True, out)
        except httpx.TimeoutException:
            return SearchResult(False, error_type="NETWORK")
        except httpx.HTTPStatusError:
            return SearchResult(False, error_type="SERVER_ERROR")
        except Exception:
            return SearchResult(False, error_type="NETWORK")


class TavilyProvider(SearchProvider):
    """Tavily Search API (https://tavily.com) — AI-friendly, structured."""

    name = "tavily"

    def __init__(self, api_key: str):
        self.api_key = api_key

    async def search(self, query: str, count: int) -> SearchResult:
        if not self.api_key:
            return SearchResult(False, error_type="AUTH_ERROR")
        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={"query": query, "max_results": count},
                    headers={"Authorization": f"Bearer {self.api_key}"},
                    timeout=10.0,
                )
                if r.status_code == 429:
                    return SearchResult(False, error_type="RATE_LIMIT")
                if r.status_code in (401, 403):
                    return SearchResult(False, error_type="AUTH_ERROR")
                if r.status_code >= 500:
                    return SearchResult(False, error_type="SERVER_ERROR")
                r.raise_for_status()

            items = r.json().get("results", [])
            out = [
                {"title": it.get("title", ""), "url": it.get("url", ""),
                 "snippet": it.get("content", "")}
                for it in items[:count] if it.get("url")
            ]
            if not out:
                return SearchResult(True, error_type="NO_RESULT")
            return SearchResult(True, out)
        except httpx.TimeoutException:
            return SearchResult(False, error_type="NETWORK")
        except httpx.HTTPStatusError:
            return SearchResult(False, error_type="SERVER_ERROR")
        except Exception:
            return SearchResult(False, error_type="NETWORK")


class SearchProviderManager:
    """Orchestrates providers for the configured search strategy.

    provider=auto: Tavily(if key) → Brave(if key) → DDGS — falling through
    on RATE_LIMIT/NETWORK/SERVER_ERROR.  AUTH_ERROR degrades straight to the
    keyless provider with a warning (never silently loops).
    """

    _PROVIDERS = {"tavily": TavilyProvider, "brave": BraveProvider, "ddgs": DDGSProvider}

    def __init__(
        self,
        provider: str,
        *,
        tavily_api_key: str = "",
        brave_api_key: str = "",
    ):
        self.tavily_api_key = tavily_api_key
        self.brave_api_key = brave_api_key
        name = (provider or "auto").lower()
        # Old "hybrid" value means the auto fallback chain now.
        self.provider = "auto" if name in {"auto", "hybrid"} else name
        if self.provider not in self._PROVIDERS:
            self.provider = "auto"

    def _make(self, name: str) -> SearchProvider | None:
        if name == "tavily":
            return TavilyProvider(self.tavily_api_key)
        if name == "brave":
            return BraveProvider(self.brave_api_key)
        if name == "ddgs":
            return DDGSProvider()
        return None

    def _chain(self) -> list[SearchProvider]:
        if self.provider != "auto":
            return [self._make(self.provider)]
        chain = []
        if self.tavily_api_key:
            chain.append(TavilyProvider(self.tavily_api_key))
        if self.brave_api_key:
            chain.append(BraveProvider(self.brave_api_key))
        chain.append(DDGSProvider())
        return chain

    async def search(self, query: str, count: int) -> SearchResult:
        chain = self._chain()
        last_auth_warned = False
        for provider in chain:
            result = await provider.search(query, count)
            if result.success:
                return result
            if result.error_type in _FALLBACK_ERRORS:
                logging.getLogger(__name__).warning(
                    "web_search: %s failed (%s), trying next provider",
                    provider.name, result.error_type,
                )
                continue
            if result.error_type in _AUTH_ERRORS:
                if not last_auth_warned:
                    logging.getLogger(__name__).warning(
                        "web_search: %s authentication failed — check API key",
                        provider.name,
                    )
                    last_auth_warned = True
                continue  # degrade to the next (keyless) provider once
            return result  # NO_RESULT etc. — not a fallback condition
        return SearchResult(False, error_type="SERVER_ERROR")


class WebSearchTool(Tool):
    """Search the web. provider=auto falls back Tavily → Brave → DDGS."""

    name = "web_search"
    description = "Search the web. Returns titles, URLs, and snippets."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query", "minLength": 1},
            "count": {
                "type": "integer",
                "description": "Results (1-10)",
                "minimum": 1,
                "maximum": 10,
            },
        },
        "required": ["query"],
    }

    def __init__(
        self,
        api_key: str | None = None,
        max_results: int = 5,
        provider: str = "auto",
        tavily_api_key: str | None = None,
        brave_api_key: str | None = None,
    ):
        self.manager = SearchProviderManager(
            provider,
            # legacy api_key was the Brave key — never feed it to Tavily (#561)
            tavily_api_key=tavily_api_key or os.environ.get("TAVILY_API_KEY", ""),
            brave_api_key=brave_api_key or api_key or os.environ.get("BRAVE_API_KEY", ""),
        )
        self.max_results = max_results

    async def execute(self, query: str, count: int | None = None, **kwargs: Any) -> str:
        n = min(max(count or self.max_results, 1), 10)

        # Reasoning mode (issue #680): fast mode fans out into parallel
        # queries + fetches via SearchOrchestrator; think mode = current path.
        search_strategy = kwargs.get("_search_strategy")
        if search_strategy is not None and getattr(search_strategy, "fanout_queries", 1) > 1:
            from miqi.agent.search_orchestrator import SearchOrchestrator

            orchestrator = SearchOrchestrator(search_tool=self, fetch_tool=WebFetchTool())
            return await orchestrator.run(query, search_strategy, n_results=n)

        result = await self.manager.search(query, n)
        if not result.success:
            return (
                "Error: 网络搜索失败（所有可用搜索服务均不可用）。"
                "请勿尝试用 web_fetch 抓取搜索引擎页面（会被拒绝且结果不可用）。"
                "直接告知用户搜索暂不可用，或建议稍后重试。"
            )
        if result.error_type == "NO_RESULT":
            return f"No results for: {query}"
        return _format_results(query, result.results)


class WebFetchTool(Tool):
    """Fetch and extract content from a URL using Readability."""

    name = "web_fetch"
    description = "Fetch URL and extract readable content (HTML → markdown/text)."
    parameters = {
        "type": "object",
        "properties": {
            "url": {"type": "string", "description": "URL to fetch", "minLength": 1},
            "extractMode": {"type": "string", "enum": ["markdown", "text"], "default": "markdown"},
            "maxChars": {"type": "integer", "minimum": 100},
        },
        "required": ["url"],
    }

    def __init__(
        self,
        max_chars: int = 50000,
        provider: str = "builtin",
        ollama_api_key: str | None = None,
        ollama_api_base: str | None = None,
    ):
        self.max_chars = max_chars
        # Keep backward compatibility with old "miqi" value.
        self.provider = "builtin" if provider == "miqi" else provider
        self.ollama_api_key = ollama_api_key or os.environ.get(
            "OLLAMA_API_KEY", "")
        self.ollama_api_base = (
            ollama_api_base or "https://ollama.com").rstrip("/")

    async def execute(
        self,
        url: str,
        extract_mode: str = "markdown",
        max_chars: int | None = None,
        **kwargs: Any,
    ) -> str:
        extract_mode = kwargs.get("extractMode", extract_mode)
        max_chars = kwargs.get("maxChars", max_chars)

        if self.provider == "ollama":
            return await self._ollama_fetch(url, max_chars=max_chars)
        if self.provider == "hybrid":
            result = await self._builtin_fetch(url, extract_mode, max_chars)
            if not result.startswith('{"error"'):
                return result
            return await self._ollama_fetch(url, max_chars=max_chars)
        return await self._builtin_fetch(url, extract_mode, max_chars)

    async def _builtin_fetch(
        self,
        url: str,
        extract_mode: str = "markdown",
        max_chars: int | None = None,
    ) -> str:
        from readability import Document

        max_chars = max_chars or self.max_chars

        # Validate URL before fetching
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps({"error": f"URL validation failed: {error_msg}", "url": url}, ensure_ascii=False)

        try:
            # 手动跟随重定向，每跳都验证目标 URL（CodeRabbit #741：公共 URL
            # 可重定向到内网/元数据地址，自动 follow_redirects 会绕过 _validate_url）。
            current = url
            for _ in range(MAX_REDIRECTS + 1):
                async with httpx.AsyncClient(
                    follow_redirects=False, timeout=30.0
                ) as client:
                    r = await client.get(current, headers={"User-Agent": USER_AGENT})
                if r.status_code in (301, 302, 303, 307, 308):
                    location = r.headers.get("location")
                    if not location:
                        break
                    next_url = str(httpx.URL(current).join(location))
                    is_valid, error_msg = _validate_url(next_url)
                    if not is_valid:
                        return json.dumps(
                            {"error": f"Redirect target rejected: {error_msg}", "url": next_url},
                            ensure_ascii=False,
                        )
                    current = next_url
                    continue
                r.raise_for_status()
                break
            else:
                return json.dumps(
                    {"error": "Too many redirects", "url": url}, ensure_ascii=False
                )

            ctype = r.headers.get("content-type", "")

            # JSON
            if "application/json" in ctype:
                text, extractor = json.dumps(r.json(), indent=2, ensure_ascii=False), "json"
            # HTML
            elif "text/html" in ctype or r.text[:256].lower().startswith(("<!doctype", "<html")):
                raw_html = r.text.strip()
                if not raw_html:
                    text, extractor = "(empty page)", "raw"
                else:
                    doc = Document(raw_html)
                    try:
                        summary_html = doc.summary()
                    except Exception:
                        summary_html = raw_html[:max_chars]
                    content = (
                        self._to_markdown(summary_html)
                        if extract_mode == "markdown"
                        else _strip_tags(summary_html)
                    )
                    text = f"# {doc.title()}\n\n{content}" if doc.title(
                    ) else content
                    extractor = "readability"
            else:
                text, extractor = r.text, "raw"

            truncated = len(text) > max_chars
            if truncated:
                text = text[:max_chars]

            return json.dumps({"url": url, "finalUrl": str(r.url), "status": r.status_code,
                              "extractor": extractor, "truncated": truncated, "length": len(text), "text": text}, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

    async def _miqi_fetch(
        self,
        url: str,
        extract_mode: str = "markdown",
        max_chars: int | None = None,
    ) -> str:
        """Backward-compatible alias for old internal method name."""
        return await self._builtin_fetch(url, extract_mode, max_chars)

    async def _ollama_fetch(self, url: str, max_chars: int | None = None) -> str:
        if not self.ollama_api_key:
            return json.dumps(
                {"error": "OLLAMA_API_KEY not configured for Ollama web_fetch", "url": url},
                ensure_ascii=False,
            )

        # SEC-11: Validate URL before forwarding to Ollama backend to prevent
        # SSRF via Ollama-as-proxy.  The same guard as _builtin_fetch applies.
        is_valid, error_msg = _validate_url(url)
        if not is_valid:
            return json.dumps(
                {"error": f"URL validation failed: {error_msg}", "url": url},
                ensure_ascii=False,
            )

        resolved_max_chars = self.max_chars if max_chars is None else max_chars
        endpoint = f"{self.ollama_api_base}/api/web_fetch"

        try:
            async with httpx.AsyncClient() as client:
                r = await client.post(
                    endpoint,
                    json={"url": url},
                    headers={
                        "Authorization": f"Bearer {self.ollama_api_key}",
                        "Content-Type": "application/json",
                    },
                    timeout=20.0,
                )
                r.raise_for_status()

            payload = r.json()
            content = payload.get("content", "")
            truncated = len(content) > resolved_max_chars
            if truncated:
                content = content[:resolved_max_chars]

            return json.dumps(
                {
                    "url": url,
                    "extractor": "ollama_web_fetch",
                    "title": payload.get("title", ""),
                    "links": payload.get("links", []),
                    "truncated": truncated,
                    "length": len(content),
                    "text": content,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps({"error": str(e), "url": url}, ensure_ascii=False)

    def _to_markdown(self, html: str) -> str:
        """Convert HTML to markdown."""
        # Convert links, headings, lists before stripping tags
        text = re.sub(
            r'<a\s+[^>]*href=["\']([^"\']+)["\'][^>]*>([\s\S]*?)</a>',
            lambda m: f"[{_strip_tags(m[2])}]({m[1]})",
            html,
            flags=re.I,
        )
        text = re.sub(
            r"<h([1-6])[^>]*>([\s\S]*?)</h\1>",
            lambda m: f"\n{'#' * int(m[1])} {_strip_tags(m[2])}\n",
            text,
            flags=re.I,
        )
        text = re.sub(
            r"<li[^>]*>([\s\S]*?)</li>", lambda m: f"\n- {_strip_tags(m[1])}", text, flags=re.I
        )
        text = re.sub(r"</(p|div|section|article)>", "\n\n", text, flags=re.I)
        text = re.sub(r"<(br|hr)\s*/?>", "\n", text, flags=re.I)
        return _normalize(_strip_tags(text))
