---
name: paper-research
description: "Search, download, translate, and summarize academic papers. Use when user asks to find papers, read a paper, translate a PDF, or generate a research briefing with references."
metadata: {"miqi":{"emoji":"📚"}}
---

# Paper Research

Full workflow: search → download → (translate) → summarize → report.

## Tools Available

| Tool | Purpose |
|------|---------|
| `paper_search` | Search by keyword/author/topic (Semantic Scholar) |
| `paper_get` | Fetch metadata + abstract for a known paper ID or DOI |
| `paper_download` | Download PDF to `workspace/artifacts/papers/` |
| `mcp_pdf2zh_translate_pdf` | Translate PDF (en→zh or other); returns mono + dual PDF paths. Requires `pdf2zh` MCP server (`miqi config pdf2zh`). |
| `web_search` | Fallback for news, preprints not yet indexed |

## Standard Research Briefing

When the user asks for a research briefing (e.g. "最新量子计算进展"):

1. `paper_search` — 3–5 searches with varied keywords; collect 10–20 candidates
2. Filter by year (prefer ≥ last 12 months) and citation count
3. For each selected paper: extract title, authors, year, DOI/URL, 1-sentence contribution
4. Write briefing in user's language; include a **References** section at the end

References format:
```
[1] Author et al. (Year). Title. Journal. https://doi.org/...
[2] ...
```

Never fabricate DOIs or URLs — only use what `paper_search`/`paper_get` returns.

## Downloading & Translating a Paper

```
# Download (saves to workspace/artifacts/papers/<title>.pdf)
paper_download(paper_id="<semantic_scholar_id_or_doi>")

# Translate to Chinese (requires pdftranslate-mcp, registered as the `pdf2zh` server)
mcp_pdf2zh_translate_pdf(file="<absolute_path>", lang_in="en", lang_out="zh")
# Returns: {"mono_pdf": "...", "dual_pdf": "..."}
```

Use `dual_pdf` when the user wants to read both languages side-by-side.  
Use `mono_pdf` when the user only wants the translation.

## Cron / Scheduled Briefings

When creating a scheduled briefing (e.g. "每天早上9点发量子计算简报"):
- Write the `message` as a **full self-contained prompt** including topic, language, format, and reference requirement
- Example message: `"Search for the latest quantum computing papers and news from the past 7 days. Write a Chinese briefing with key findings and a References section. Send via feishu."`
- Always pair with `tz="Asia/Shanghai"` and `cron_expr`

## Fallback

If `paper_search` returns no results, try `web_search` with site filters:
```
web_search("quantum computing 2026 site:arxiv.org OR site:nature.com")
```
