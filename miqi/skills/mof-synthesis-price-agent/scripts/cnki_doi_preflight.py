#!/usr/bin/env python
"""Fast CNKI DOI metadata preflight for evidence-boundary decisions."""
from __future__ import annotations

import argparse
import html
import json
import re
import sys
import time
from html.parser import HTMLParser
from urllib.parse import quote
from urllib.request import Request, urlopen


DOI_RE = re.compile(r"10\.\d{4,}/[^\s,;\"'<>]+", re.I)
FIELD_BOUNDARY_RE = re.compile(r"(题名|作者|来源|出版机构|出版年|DOI码|注册时间)\s*[:：]|以下是您获得", re.S)
POSITIVE_RE = re.compile(
    r"\bMOFs?\b|\bCOFs?\b|metal[- ]organic framework|covalent organic framework|"
    r"coordination polymer|金属有机框架|共价有机框架|配位聚合物",
    re.I,
)
NEGATIVE_RE = re.compile(
    r"\bLDHs?\b|layered double hydroxide|层状双金属氢氧化物|氢氧化物|氧化物|硫化物|"
    r"磷化物|合金|析氧|电催化",
    re.I,
)


class TextParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if text:
            self.parts.append(text)


def _extract_doi(value: str) -> str:
    match = DOI_RE.search(value)
    if not match:
        raise ValueError("No DOI-like value found.")
    return match.group(0)


def _fetch_cnki_handler(doi: str, timeout: int) -> tuple[str, str]:
    url = "https://doi.cnki.net/resolution/handler?doi=" + quote(doi, safe="")
    req = Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urlopen(req, timeout=timeout) as resp:
        raw = resp.read()
        charset = resp.headers.get_content_charset() or "utf-8"
    return url, raw.decode(charset, errors="replace")


def _field(text: str, label: str) -> str | None:
    pattern = re.compile(re.escape(label) + r"\s*[:：]\s*(.*?)(?=" + FIELD_BOUNDARY_RE.pattern + r"|$)", re.S)
    match = pattern.search(text)
    if not match:
        return None
    value = re.sub(r"\s+", " ", match.group(1)).strip(" ;；")
    if label == "注册时间":
        date_match = re.search(r"\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}", value)
        if date_match:
            value = date_match.group(0)
    return html.unescape(value) or None


def _scope(title: str | None) -> str:
    if not title:
        return "unknown"
    positive = bool(POSITIVE_RE.search(title))
    negative = bool(NEGATIVE_RE.search(title))
    if positive:
        return "mof_like"
    if negative:
        return "not_mof"
    return "unknown"


def preflight(value: str, timeout: int) -> dict[str, object]:
    started = time.perf_counter()
    doi = _extract_doi(value)
    result: dict[str, object] = {
        "input": value,
        "doi": doi,
        "source": "cnki_doi_handler",
        "status": "failed",
        "url": None,
        "title": None,
        "authors": [],
        "publication_institution": None,
        "doi_registration_time": None,
        "material_scope": "unknown",
        "completion_state_hint": "failed",
        "elapsed_ms": None,
        "error": None,
    }
    try:
        url, body = _fetch_cnki_handler(doi, timeout)
        parser = TextParser()
        parser.feed(body)
        text = "\n".join(parser.parts)
        title = _field(text, "题名")
        authors_raw = _field(text, "作者") or ""
        authors = [item for item in re.split(r"[;；]\s*", authors_raw) if item]
        result.update(
            {
                "status": "reachable",
                "url": url,
                "title": title,
                "authors": authors,
                "publication_institution": _field(text, "出版机构"),
                "doi_registration_time": _field(text, "注册时间"),
                "material_scope": _scope(title),
            }
        )
        result["completion_state_hint"] = (
            "evidence_boundary" if result["material_scope"] == "not_mof" else "continue_or_need_full_text"
        )
    except Exception as exc:
        result["error"] = str(exc)
    finally:
        result["elapsed_ms"] = round((time.perf_counter() - started) * 1000)
    return result


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight CNKI DOI metadata and MOF scope.")
    parser.add_argument("doi_or_url")
    parser.add_argument("--timeout", type=int, default=10)
    args = parser.parse_args()
    data = preflight(args.doi_or_url, args.timeout)
    print(json.dumps(data, ensure_ascii=False, indent=2))
    return 0 if data["status"] == "reachable" else 1


if __name__ == "__main__":
    raise SystemExit(main())
