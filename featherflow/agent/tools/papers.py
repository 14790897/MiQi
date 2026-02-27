"""Paper research tools: search and fetch paper metadata."""

from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote, unquote, urlparse
from xml.etree import ElementTree as ET

import httpx

from featherflow.agent.tools.base import Tool


def _safe_int(value: Any) -> int | None:
    try:
        if value is None:
            return None
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _extract_arxiv_id(entry_id: str) -> str:
    v = (entry_id or "").strip()
    if not v:
        return ""
    if "/abs/" in v:
        return v.split("/abs/", 1)[1]
    return v


def _safe_file_component(value: str, fallback: str = "paper") -> str:
    text = (value or "").strip()
    if not text:
        text = fallback
    text = unquote(text)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    text = re.sub(r"_+", "_", text).strip("._")
    return text or fallback


def _looks_like_pdf(bytes_head: bytes) -> bool:
    return bytes_head.startswith(b"%PDF-")


def _looks_like_html(content_type: str, sample: bytes) -> bool:
    ctype = (content_type or "").lower()
    if "text/html" in ctype or "application/xhtml+xml" in ctype:
        return True
    sample_text = sample[:512].decode("utf-8", errors="ignore").lower()
    return "<html" in sample_text or "<!doctype html" in sample_text


def _detect_paywall_text(sample: bytes) -> tuple[bool, list[str]]:
    text = sample[:8192].decode("utf-8", errors="ignore").lower()
    hints = [
        ("purchase", "purchase"),
        ("subscribe", "subscribe"),
        ("paywall", "paywall"),
        ("institutional access", "institutional_access"),
        ("access through your institution", "institutional_access"),
        ("log in", "login_required"),
        ("sign in", "login_required"),
        ("buy this article", "purchase"),
    ]
    found = [tag for key, tag in hints if key in text]
    return bool(found), sorted(set(found))


def _to_record(
    *,
    source: str,
    paper_id: str,
    title: str,
    abstract: str,
    authors: list[str],
    year: int | None,
    venue: str,
    doi: str,
    arxiv_id: str,
    citation_count: int | None,
    reference_count: int | None,
    is_open_access: bool,
    open_access_pdf_url: str,
    source_url: str,
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": paper_id,
        "title": title,
        "abstract": abstract,
        "authors": authors,
        "year": year,
        "venue": venue,
        "doi": doi,
        "arxiv_id": arxiv_id,
        "citation_count": citation_count,
        "reference_count": reference_count,
        "is_open_access": is_open_access,
        "open_access_pdf_url": open_access_pdf_url,
        "source": source,
        "source_url": source_url,
    }
    if extra:
        data["extra"] = extra
    return data


def _parse_arxiv_entry(entry: ET.Element, ns: dict[str, str]) -> dict[str, Any]:
    """Parse one arXiv Atom entry into normalized metadata fields."""
    entry_id = _normalize_text(entry.findtext("a:id", default="", namespaces=ns))
    arxiv_id = _extract_arxiv_id(entry_id)
    title = _normalize_text(entry.findtext("a:title", default="", namespaces=ns))
    summary = _normalize_text(entry.findtext("a:summary", default="", namespaces=ns))
    published = _normalize_text(entry.findtext("a:published", default="", namespaces=ns))
    year = _safe_int(published[:4]) if published else None
    authors = [
        _normalize_text(author.findtext("a:name", default="", namespaces=ns))
        for author in entry.findall("a:author", ns)
    ]
    authors = [a for a in authors if a]

    pdf_url = ""
    doi = ""
    for link in entry.findall("a:link", ns):
        if (link.attrib.get("title") or "").lower() == "pdf":
            pdf_url = _normalize_text(link.attrib.get("href", ""))
        if (link.attrib.get("title") or "").lower() == "doi":
            doi = _normalize_text(link.attrib.get("href", ""))

    category_terms = [c.attrib.get("term", "") for c in entry.findall("a:category", ns)]
    venue = category_terms[0] if category_terms else ""

    return {
        "entry_id": entry_id,
        "arxiv_id": arxiv_id,
        "title": title,
        "summary": summary,
        "year": year,
        "authors": authors,
        "pdf_url": pdf_url,
        "doi": doi,
        "venue": venue,
    }


class PaperSearchTool(Tool):
    """Search papers from Semantic Scholar / arXiv."""

    name = "paper_search"
    description = "Search scholarly papers and return normalized metadata."
    parameters = {
        "type": "object",
        "properties": {
            "query": {"type": "string", "description": "Search query"},
            "limit": {"type": "integer", "minimum": 1, "maximum": 20, "default": 8},
            "yearFrom": {"type": "integer", "description": "Optional start year"},
            "yearTo": {"type": "integer", "description": "Optional end year"},
            "fieldsOfStudy": {
                "type": "string",
                "description": "Optional comma-separated fields of study for Semantic Scholar",
            },
            "minCitationCount": {"type": "integer", "minimum": 0},
            "openAccessOnly": {"type": "boolean", "default": False},
            "source": {
                "type": "string",
                "enum": ["hybrid", "semantic_scholar", "arxiv"],
                "default": "hybrid",
            },
            "sort": {
                "type": "string",
                "enum": ["relevance", "recent"],
                "default": "relevance",
            },
        },
        "required": ["query"],
    }

    def __init__(
        self,
        provider: str = "hybrid",
        semantic_scholar_api_key: str | None = None,
        timeout_seconds: int = 20,
        default_limit: int = 8,
        max_limit: int = 20,
    ):
        self.provider = provider
        self.semantic_scholar_api_key = (semantic_scholar_api_key or "").strip()
        self.timeout_seconds = max(3, timeout_seconds)
        self.default_limit = max(1, default_limit)
        self.max_limit = max(1, max_limit)

    async def execute(
        self,
        query: str,
        limit: int | None = None,
        year_from: int | None = None,
        year_to: int | None = None,
        fields_of_study: str | None = None,
        min_citation_count: int | None = None,
        open_access_only: bool = False,
        source: str | None = None,
        sort: str = "relevance",
        **kwargs: Any,
    ) -> str:
        year_from = kwargs.get("yearFrom", year_from)
        year_to = kwargs.get("yearTo", year_to)
        fields_of_study = kwargs.get("fieldsOfStudy", fields_of_study)
        min_citation_count = kwargs.get("minCitationCount", min_citation_count)
        open_access_only = kwargs.get("openAccessOnly", open_access_only)

        q = _normalize_text(query)
        if not q:
            return json.dumps({"error": "query is required"}, ensure_ascii=False)

        n = limit or self.default_limit
        n = min(max(n, 1), self.max_limit)

        resolved_source = (source or self.provider or "hybrid").strip().lower()

        if resolved_source == "semantic_scholar":
            return await self._search_semantic_scholar(
                q,
                n,
                year_from=year_from,
                year_to=year_to,
                fields_of_study=fields_of_study,
                min_citation_count=min_citation_count,
                open_access_only=open_access_only,
            )

        if resolved_source == "arxiv":
            return await self._search_arxiv(q, n, sort=sort)

        semantic_result = await self._search_semantic_scholar(
            q,
            n,
            year_from=year_from,
            year_to=year_to,
            fields_of_study=fields_of_study,
            min_citation_count=min_citation_count,
            open_access_only=open_access_only,
        )
        semantic_payload = _try_json(semantic_result)
        if isinstance(semantic_payload, dict) and semantic_payload.get("items"):
            return semantic_result

        return await self._search_arxiv(q, n, sort=sort)

    async def _search_semantic_scholar(
        self,
        query: str,
        limit: int,
        year_from: int | None,
        year_to: int | None,
        fields_of_study: str | None,
        min_citation_count: int | None,
        open_access_only: bool,
    ) -> str:
        params: dict[str, Any] = {
            "query": query,
            "limit": limit,
            "offset": 0,
            "fields": (
                "paperId,title,abstract,authors,year,venue,url,"
                "citationCount,referenceCount,externalIds,isOpenAccess,openAccessPdf"
            ),
        }

        if year_from is not None and year_to is not None:
            params["year"] = f"{year_from}-{year_to}"
        elif year_from is not None:
            params["year"] = f"{year_from}-"
        elif year_to is not None:
            params["year"] = f"-{year_to}"

        if fields_of_study:
            params["fieldsOfStudy"] = fields_of_study
        if min_citation_count is not None:
            params["minCitationCount"] = min_citation_count
        if open_access_only:
            params["openAccessPdf"] = ""

        headers: dict[str, str] = {}
        if self.semantic_scholar_api_key:
            headers["x-api-key"] = self.semantic_scholar_api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(
                    "https://api.semanticscholar.org/graph/v1/paper/search",
                    params=params,
                    headers=headers,
                )
                resp.raise_for_status()
            payload = resp.json()
            items = []
            for p in payload.get("data", []):
                ext_ids = p.get("externalIds") or {}
                authors = [a.get("name", "") for a in p.get("authors", []) if a.get("name")]
                open_access_pdf = p.get("openAccessPdf") or {}
                items.append(
                    _to_record(
                        source="semantic_scholar",
                        paper_id=_normalize_text(p.get("paperId")),
                        title=_normalize_text(p.get("title")),
                        abstract=_normalize_text(p.get("abstract")),
                        authors=authors,
                        year=_safe_int(p.get("year")),
                        venue=_normalize_text(p.get("venue")),
                        doi=_normalize_text(ext_ids.get("DOI")),
                        arxiv_id=_normalize_text(ext_ids.get("ArXiv") or ext_ids.get("ARXIV")),
                        citation_count=_safe_int(p.get("citationCount")),
                        reference_count=_safe_int(p.get("referenceCount")),
                        is_open_access=bool(p.get("isOpenAccess") or open_access_pdf.get("url")),
                        open_access_pdf_url=_normalize_text(open_access_pdf.get("url")),
                        source_url=_normalize_text(p.get("url")),
                    )
                )
            return json.dumps(
                {
                    "query": query,
                    "source": "semantic_scholar",
                    "total": payload.get("total"),
                    "count": len(items),
                    "items": items,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {
                    "error": f"semantic_scholar_search_failed: {e}",
                    "query": query,
                    "source": "semantic_scholar",
                    "items": [],
                },
                ensure_ascii=False,
            )

    async def _search_arxiv(self, query: str, limit: int, sort: str = "relevance") -> str:
        sort_by = "submittedDate" if sort == "recent" else "relevance"
        params = {
            "search_query": f"all:{query}",
            "start": 0,
            "max_results": limit,
            "sortBy": sort_by,
            "sortOrder": "descending",
        }
        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get("http://export.arxiv.org/api/query", params=params)
                resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            entries = root.findall("a:entry", ns)
            items = []
            for entry in entries:
                parsed = _parse_arxiv_entry(entry, ns)

                items.append(
                    _to_record(
                        source="arxiv",
                        paper_id=f"ARXIV:{parsed['arxiv_id']}" if parsed["arxiv_id"] else parsed["entry_id"],
                        title=parsed["title"],
                        abstract=parsed["summary"],
                        authors=parsed["authors"],
                        year=parsed["year"],
                        venue=parsed["venue"],
                        doi=parsed["doi"],
                        arxiv_id=parsed["arxiv_id"],
                        citation_count=None,
                        reference_count=None,
                        is_open_access=bool(parsed["pdf_url"]),
                        open_access_pdf_url=parsed["pdf_url"],
                        source_url=parsed["entry_id"],
                    )
                )

            return json.dumps(
                {
                    "query": query,
                    "source": "arxiv",
                    "count": len(items),
                    "items": items,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {
                    "error": f"arxiv_search_failed: {e}",
                    "query": query,
                    "source": "arxiv",
                    "items": [],
                },
                ensure_ascii=False,
            )


class PaperGetTool(Tool):
    """Get normalized details for a specific paper."""

    name = "paper_get"
    description = "Get paper details by paper ID / DOI / arXiv ID, with optional references/citations."
    parameters = {
        "type": "object",
        "properties": {
            "paperId": {"type": "string", "description": "Paper id, DOI, or arXiv id"},
            "source": {
                "type": "string",
                "enum": ["hybrid", "semantic_scholar", "arxiv"],
                "default": "hybrid",
            },
            "withReferences": {"type": "boolean", "default": False},
            "withCitations": {"type": "boolean", "default": False},
            "edgeLimit": {"type": "integer", "minimum": 1, "maximum": 200, "default": 20},
        },
        "required": ["paperId"],
    }

    def __init__(
        self,
        provider: str = "hybrid",
        semantic_scholar_api_key: str | None = None,
        timeout_seconds: int = 20,
    ):
        self.provider = provider
        self.semantic_scholar_api_key = (semantic_scholar_api_key or "").strip()
        self.timeout_seconds = max(3, timeout_seconds)

    async def execute(
        self,
        paper_id: str | None = None,
        source: str | None = None,
        with_references: bool = False,
        with_citations: bool = False,
        edge_limit: int = 20,
        **kwargs: Any,
    ) -> str:
        paper_id = kwargs.get("paperId", paper_id)
        with_references = kwargs.get("withReferences", with_references)
        with_citations = kwargs.get("withCitations", with_citations)
        edge_limit = kwargs.get("edgeLimit", edge_limit)

        pid = _normalize_text(paper_id)
        if not pid:
            return json.dumps({"error": "paperId is required"}, ensure_ascii=False)

        resolved_source = (source or self.provider or "hybrid").strip().lower()
        edge_limit = min(max(edge_limit, 1), 200)

        if resolved_source == "semantic_scholar":
            return await self._get_semantic_scholar(pid, with_references, with_citations, edge_limit)
        if resolved_source == "arxiv":
            return await self._get_arxiv(pid)

        s2 = await self._get_semantic_scholar(pid, with_references, with_citations, edge_limit)
        s2_payload = _try_json(s2)
        if isinstance(s2_payload, dict) and s2_payload.get("item"):
            return s2
        return await self._get_arxiv(pid)

    async def _get_semantic_scholar(
        self,
        paper_id: str,
        with_references: bool,
        with_citations: bool,
        edge_limit: int,
    ) -> str:
        norm_id = paper_id
        if re.match(r"^10\.\S+/\S+", paper_id, flags=re.I):
            norm_id = f"DOI:{paper_id}"
        elif paper_id.lower().startswith("arxiv:"):
            norm_id = f"ARXIV:{paper_id.split(':', 1)[1]}"

        fields = (
            "paperId,title,abstract,authors,year,venue,url,"
            "citationCount,referenceCount,externalIds,isOpenAccess,openAccessPdf"
        )
        encoded = quote(norm_id, safe="")
        headers: dict[str, str] = {}
        if self.semantic_scholar_api_key:
            headers["x-api-key"] = self.semantic_scholar_api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get(
                    f"https://api.semanticscholar.org/graph/v1/paper/{encoded}",
                    params={"fields": fields},
                    headers=headers,
                )
                resp.raise_for_status()
                payload = resp.json()

                ext_ids = payload.get("externalIds") or {}
                authors = [a.get("name", "") for a in payload.get("authors", []) if a.get("name")]
                open_access_pdf = payload.get("openAccessPdf") or {}

                item = _to_record(
                    source="semantic_scholar",
                    paper_id=_normalize_text(payload.get("paperId")),
                    title=_normalize_text(payload.get("title")),
                    abstract=_normalize_text(payload.get("abstract")),
                    authors=authors,
                    year=_safe_int(payload.get("year")),
                    venue=_normalize_text(payload.get("venue")),
                    doi=_normalize_text(ext_ids.get("DOI")),
                    arxiv_id=_normalize_text(ext_ids.get("ArXiv") or ext_ids.get("ARXIV")),
                    citation_count=_safe_int(payload.get("citationCount")),
                    reference_count=_safe_int(payload.get("referenceCount")),
                    is_open_access=bool(payload.get("isOpenAccess") or open_access_pdf.get("url")),
                    open_access_pdf_url=_normalize_text(open_access_pdf.get("url")),
                    source_url=_normalize_text(payload.get("url")),
                )

                references = []
                citations = []

                if with_references:
                    ref_resp = await client.get(
                        f"https://api.semanticscholar.org/graph/v1/paper/{encoded}/references",
                        params={
                            "limit": edge_limit,
                            "offset": 0,
                            "fields": "title,year,citationCount,venue,authors",
                        },
                        headers=headers,
                    )
                    ref_resp.raise_for_status()
                    for row in ref_resp.json().get("data", []):
                        p = row.get("citedPaper") or {}
                        references.append(
                            {
                                "id": _normalize_text(p.get("paperId")),
                                "title": _normalize_text(p.get("title")),
                                "year": _safe_int(p.get("year")),
                                "citation_count": _safe_int(p.get("citationCount")),
                                "venue": _normalize_text(p.get("venue")),
                                "authors": [a.get("name", "") for a in p.get("authors", []) if a.get("name")],
                            }
                        )

                if with_citations:
                    cit_resp = await client.get(
                        f"https://api.semanticscholar.org/graph/v1/paper/{encoded}/citations",
                        params={
                            "limit": edge_limit,
                            "offset": 0,
                            "fields": "title,year,citationCount,venue,authors",
                        },
                        headers=headers,
                    )
                    cit_resp.raise_for_status()
                    for row in cit_resp.json().get("data", []):
                        p = row.get("citingPaper") or {}
                        citations.append(
                            {
                                "id": _normalize_text(p.get("paperId")),
                                "title": _normalize_text(p.get("title")),
                                "year": _safe_int(p.get("year")),
                                "citation_count": _safe_int(p.get("citationCount")),
                                "venue": _normalize_text(p.get("venue")),
                                "authors": [a.get("name", "") for a in p.get("authors", []) if a.get("name")],
                            }
                        )

            return json.dumps(
                {
                    "source": "semantic_scholar",
                    "item": item,
                    "references": references,
                    "citations": citations,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {
                    "error": f"semantic_scholar_get_failed: {e}",
                    "source": "semantic_scholar",
                    "item": None,
                },
                ensure_ascii=False,
            )

    async def _get_arxiv(self, paper_id: str) -> str:
        arxiv_id = paper_id
        if paper_id.lower().startswith("arxiv:"):
            arxiv_id = paper_id.split(":", 1)[1]
        elif "/abs/" in paper_id:
            arxiv_id = paper_id.split("/abs/", 1)[1]

        params = {
            "id_list": arxiv_id,
            "start": 0,
            "max_results": 1,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
                resp = await client.get("http://export.arxiv.org/api/query", params=params)
                resp.raise_for_status()

            root = ET.fromstring(resp.text)
            ns = {"a": "http://www.w3.org/2005/Atom"}
            entry = root.find("a:entry", ns)
            if entry is None:
                return json.dumps(
                    {"error": "arxiv_not_found", "source": "arxiv", "item": None},
                    ensure_ascii=False,
                )

            parsed = _parse_arxiv_entry(entry, ns)

            item = _to_record(
                source="arxiv",
                paper_id=f"ARXIV:{parsed['arxiv_id']}" if parsed["arxiv_id"] else parsed["entry_id"],
                title=parsed["title"],
                abstract=parsed["summary"],
                authors=parsed["authors"],
                year=parsed["year"],
                venue=parsed["venue"],
                doi=parsed["doi"],
                arxiv_id=parsed["arxiv_id"],
                citation_count=None,
                reference_count=None,
                is_open_access=bool(parsed["pdf_url"]),
                open_access_pdf_url=parsed["pdf_url"],
                source_url=parsed["entry_id"],
            )

            return json.dumps(
                {
                    "source": "arxiv",
                    "item": item,
                    "references": [],
                    "citations": [],
                },
                ensure_ascii=False,
            )
        except Exception as e:
            return json.dumps(
                {
                    "error": f"arxiv_get_failed: {e}",
                    "source": "arxiv",
                    "item": None,
                },
                ensure_ascii=False,
            )


class PaperDownloadTool(Tool):
    """Download paper PDFs to workspace with paywall-aware handling."""

    name = "paper_download"
    description = "Download an open-access paper PDF to workspace and return local file path."
    parameters = {
        "type": "object",
        "properties": {
            "paperId": {
                "type": "string",
                "description": "Paper id/DOI/arXiv id. Required when url is not provided.",
            },
            "url": {
                "type": "string",
                "description": "Direct PDF URL. If provided, takes precedence over paperId.",
            },
            "source": {
                "type": "string",
                "enum": ["hybrid", "semantic_scholar", "arxiv"],
                "default": "hybrid",
            },
            "outPath": {
                "type": "string",
                "description": "Optional output path (relative to workspace).",
            },
            "overwrite": {"type": "boolean", "default": False},
            "maxSizeMB": {
                "type": "integer",
                "minimum": 1,
                "maximum": 500,
                "description": "Maximum allowed file size in MB before aborting.",
            },
        },
    }

    def __init__(
        self,
        workspace: Path,
        provider: str = "hybrid",
        semantic_scholar_api_key: str | None = None,
        timeout_seconds: int = 30,
        max_size_mb: int = 80,
    ):
        self.workspace = workspace.resolve()
        self.provider = provider
        self.semantic_scholar_api_key = (semantic_scholar_api_key or "").strip()
        self.timeout_seconds = max(5, timeout_seconds)
        self.max_size_mb = max(1, max_size_mb)

    async def execute(
        self,
        paper_id: str | None = None,
        url: str | None = None,
        source: str | None = None,
        out_path: str | None = None,
        overwrite: bool = False,
        max_size_mb: int | None = None,
        **kwargs: Any,
    ) -> str:
        paper_id = kwargs.get("paperId", paper_id)
        out_path = kwargs.get("outPath", out_path)
        max_size_mb = kwargs.get("maxSizeMB", max_size_mb)

        resolved_source = (source or self.provider or "hybrid").strip().lower()
        max_size_bytes = max(1, (max_size_mb or self.max_size_mb)) * 1024 * 1024

        download_url = _normalize_text(url)
        paper_meta: dict[str, Any] | None = None
        if not download_url:
            pid = _normalize_text(paper_id)
            if not pid:
                return json.dumps(
                    {"ok": False, "error": "Either url or paperId is required."},
                    ensure_ascii=False,
                )
            paper_payload = await self._resolve_paper_pdf_url(pid, resolved_source)
            if "error" in paper_payload:
                return json.dumps(
                    {
                        "ok": False,
                        "error": paper_payload["error"],
                        "paper_id": pid,
                        "source": resolved_source,
                        "paywall_suspected": bool(paper_payload.get("paywall_suspected", False)),
                        "next_steps": [
                            "Try another source or open-access mirror.",
                        ],
                    },
                    ensure_ascii=False,
                )
            download_url = str(paper_payload.get("pdf_url") or "").strip()
            paper_meta = paper_payload.get("item")

        parsed = urlparse(download_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return json.dumps(
                {"ok": False, "error": f"Invalid download URL: {download_url}"},
                ensure_ascii=False,
            )

        try:
            save_path = self._resolve_save_path(
                out_path=out_path,
                paper_id=_normalize_text(paper_id),
                download_url=download_url,
            )
        except Exception as e:
            return json.dumps({"ok": False, "error": str(e)}, ensure_ascii=False)

        if save_path.exists() and not overwrite:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"Target file already exists: {save_path}",
                    "saved_path": str(save_path),
                },
                ensure_ascii=False,
            )

        save_path.parent.mkdir(parents=True, exist_ok=True)
        tmp_path = save_path.with_suffix(save_path.suffix + ".part")
        if tmp_path.exists():
            tmp_path.unlink(missing_ok=True)

        status_code = 0
        content_type = ""
        final_url = download_url
        sample = b""
        total = 0
        digest = hashlib.sha256()

        headers = {
            "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) FeatherFlow/1.0",
            "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.5",
        }

        try:
            async with httpx.AsyncClient(
                timeout=self.timeout_seconds,
                follow_redirects=True,
            ) as client:
                async with client.stream("GET", download_url, headers=headers) as resp:
                    status_code = int(resp.status_code)
                    content_type = str(resp.headers.get("content-type", "") or "")
                    final_url = str(resp.url)

                    if status_code >= 400:
                        body = await resp.aread()
                        paywall_suspected, tags = _detect_paywall_text(body)
                        return json.dumps(
                            {
                                "ok": False,
                                "error": f"Download failed with HTTP {status_code}",
                                "status_code": status_code,
                                "content_type": content_type,
                                "download_url": download_url,
                                "final_url": final_url,
                                "paywall_suspected": paywall_suspected
                                or status_code in {401, 402, 403, 451},
                                "signals": tags,
                            },
                            ensure_ascii=False,
                        )

                    with open(tmp_path, "wb") as f:
                        async for chunk in resp.aiter_bytes():
                            if not chunk:
                                continue
                            if not sample:
                                sample = chunk[:1024]
                            elif len(sample) < 8192:
                                remain = 8192 - len(sample)
                                sample += chunk[:remain]

                            total += len(chunk)
                            if total > max_size_bytes:
                                tmp_path.unlink(missing_ok=True)
                                return json.dumps(
                                    {
                                        "ok": False,
                                        "error": f"File too large (> {max_size_bytes} bytes).",
                                        "status_code": status_code,
                                        "download_url": download_url,
                                        "final_url": final_url,
                                    },
                                    ensure_ascii=False,
                                )
                            digest.update(chunk)
                            f.write(chunk)
        except httpx.TimeoutException:
            tmp_path.unlink(missing_ok=True)
            return json.dumps(
                {
                    "ok": False,
                    "error": f"Download timed out after {self.timeout_seconds}s",
                    "download_url": download_url,
                },
                ensure_ascii=False,
            )
        except Exception as e:
            tmp_path.unlink(missing_ok=True)
            return json.dumps(
                {"ok": False, "error": f"Download failed: {e}", "download_url": download_url},
                ensure_ascii=False,
            )

        if total <= 0:
            tmp_path.unlink(missing_ok=True)
            return json.dumps(
                {"ok": False, "error": "Downloaded file is empty", "download_url": download_url},
                ensure_ascii=False,
            )

        paywall_suspected, tags = _detect_paywall_text(sample)
        if not _looks_like_pdf(sample) and (_looks_like_html(content_type, sample) or paywall_suspected):
            tmp_path.unlink(missing_ok=True)
            return json.dumps(
                {
                    "ok": False,
                    "error": "Response is not a PDF (likely paywall/login/interstitial page).",
                    "status_code": status_code,
                    "content_type": content_type,
                    "download_url": download_url,
                    "final_url": final_url,
                    "paywall_suspected": True,
                    "signals": tags,
                    "next_steps": [
                        "Try institution/VPN-authenticated access outside the bot.",
                        "Use an open-access mirror URL and retry.",
                    ],
                },
                ensure_ascii=False,
            )

        tmp_path.replace(save_path)

        payload: dict[str, Any] = {
            "ok": True,
            "paper_id": _normalize_text(paper_id),
            "source": resolved_source,
            "download_url": download_url,
            "final_url": final_url,
            "status_code": status_code,
            "content_type": content_type,
            "saved_path": str(save_path),
            "size_bytes": total,
            "sha256": digest.hexdigest(),
        }
        if paper_meta:
            payload["item"] = paper_meta
        return json.dumps(payload, ensure_ascii=False)

    async def _resolve_paper_pdf_url(self, paper_id: str, source: str) -> dict[str, Any]:
        getter = PaperGetTool(
            provider=source,
            semantic_scholar_api_key=self.semantic_scholar_api_key,
            timeout_seconds=self.timeout_seconds,
        )
        result = await getter.execute(paperId=paper_id, source=source)
        payload = _try_json(result) or {}
        item = payload.get("item") if isinstance(payload.get("item"), dict) else {}
        pdf_url = _normalize_text((item or {}).get("open_access_pdf_url"))
        if pdf_url:
            return {"pdf_url": pdf_url, "item": item}

        reason = payload.get("error") or "No open-access PDF URL found in metadata."
        return {
            "error": str(reason),
            "paywall_suspected": True,
            "item": item,
        }

    def _resolve_save_path(self, out_path: str | None, paper_id: str, download_url: str) -> Path:
        if out_path:
            p = Path(out_path).expanduser()
            target = p if p.is_absolute() else (self.workspace / p)
        else:
            parsed = urlparse(download_url)
            name_from_url = Path(parsed.path).name
            candidate = _safe_file_component(name_from_url or paper_id or "paper")
            if not candidate.lower().endswith(".pdf"):
                candidate = f"{candidate}.pdf"
            target = self.workspace / "artifacts" / "papers" / candidate

        resolved = target.resolve()
        try:
            resolved.relative_to(self.workspace)
        except ValueError:
            raise PermissionError(f"Output path outside workspace is not allowed: {resolved}")
        return resolved


def _try_json(text: str) -> dict[str, Any] | None:
    try:
        val = json.loads(text)
        if isinstance(val, dict):
            return val
        return None
    except Exception:
        return None
