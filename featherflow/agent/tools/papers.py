"""Paper research tools: search and fetch paper metadata."""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import quote
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
        yearFrom: int | None = None,
        yearTo: int | None = None,
        fieldsOfStudy: str | None = None,
        minCitationCount: int | None = None,
        openAccessOnly: bool = False,
        source: str | None = None,
        sort: str = "relevance",
        **kwargs: Any,
    ) -> str:
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
                year_from=yearFrom,
                year_to=yearTo,
                fields_of_study=fieldsOfStudy,
                min_citation_count=minCitationCount,
                open_access_only=openAccessOnly,
            )

        if resolved_source == "arxiv":
            return await self._search_arxiv(q, n, sort=sort)

        semantic_result = await self._search_semantic_scholar(
            q,
            n,
            year_from=yearFrom,
            year_to=yearTo,
            fields_of_study=fieldsOfStudy,
            min_citation_count=minCitationCount,
            open_access_only=openAccessOnly,
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

                items.append(
                    _to_record(
                        source="arxiv",
                        paper_id=f"ARXIV:{arxiv_id}" if arxiv_id else entry_id,
                        title=title,
                        abstract=summary,
                        authors=authors,
                        year=year,
                        venue=venue,
                        doi=doi,
                        arxiv_id=arxiv_id,
                        citation_count=None,
                        reference_count=None,
                        is_open_access=bool(pdf_url),
                        open_access_pdf_url=pdf_url,
                        source_url=entry_id,
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
        paperId: str,
        source: str | None = None,
        withReferences: bool = False,
        withCitations: bool = False,
        edgeLimit: int = 20,
        **kwargs: Any,
    ) -> str:
        pid = _normalize_text(paperId)
        if not pid:
            return json.dumps({"error": "paperId is required"}, ensure_ascii=False)

        resolved_source = (source or self.provider or "hybrid").strip().lower()
        edge_limit = min(max(edgeLimit, 1), 200)

        if resolved_source == "semantic_scholar":
            return await self._get_semantic_scholar(pid, withReferences, withCitations, edge_limit)
        if resolved_source == "arxiv":
            return await self._get_arxiv(pid)

        s2 = await self._get_semantic_scholar(pid, withReferences, withCitations, edge_limit)
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

            entry_id = _normalize_text(entry.findtext("a:id", default="", namespaces=ns))
            parsed_arxiv_id = _extract_arxiv_id(entry_id)
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

            item = _to_record(
                source="arxiv",
                paper_id=f"ARXIV:{parsed_arxiv_id}" if parsed_arxiv_id else entry_id,
                title=title,
                abstract=summary,
                authors=authors,
                year=year,
                venue=venue,
                doi=doi,
                arxiv_id=parsed_arxiv_id,
                citation_count=None,
                reference_count=None,
                is_open_access=bool(pdf_url),
                open_access_pdf_url=pdf_url,
                source_url=entry_id,
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


def _try_json(text: str) -> dict[str, Any] | None:
    try:
        val = json.loads(text)
        if isinstance(val, dict):
            return val
        return None
    except Exception:
        return None
