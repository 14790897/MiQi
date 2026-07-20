#!/usr/bin/env python
"""Deterministic workflow helper for the MOF synthesis price skill.

This script intentionally does not call DeepSeek or any external LLM. It routes
inputs, performs deterministic project-tool stages, and returns JSON status so
Codex can decide when agent extraction is required.
"""
from __future__ import annotations

import argparse
import csv
import json
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote, urlparse
from typing import Any


DOI_RE = re.compile(r"10\.\d{4,}/[^\s,;\"'<>]+", re.I)
CAS_RE = re.compile(r"^\d{2,7}-\d{2}-\d$")
CNKI_RE = re.compile(r"j\.cnki|cnki\.net/doi|doi\.cnki\.net", re.I)
SYNTHESIS_HINT_RE = re.compile(
    r"synth|prepar|experimental|procedure|solvothermal|hydrothermal|配制|合成|制备|实验",
    re.I,
)


@dataclass
class WorkflowState:
    input: str
    input_type: str = "unknown"
    project_root: str = ""
    prefix: str = ""
    created_files: list[str] = field(default_factory=list)
    next_action: str = ""
    completion_state: str = "failed"
    missing_or_failed: list[str] = field(default_factory=list)
    counts: dict[str, int] = field(default_factory=dict)
    batch_ledger: str | None = None
    stage_timeout: int = 600

    def add_file(self, path: str | Path | None) -> None:
        if not path:
            return
        p = str(path)
        if p not in self.created_files:
            self.created_files.append(p)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input": self.input,
            "input_type": self.input_type,
            "project_root": self.project_root,
            "prefix": self.prefix,
            "created_files": self.created_files,
            "next_action": self.next_action,
            "completion_state": self.completion_state,
            "missing_or_failed": self.missing_or_failed,
            "counts": self.counts,
            "batch_ledger": self.batch_ledger,
        }


def _json_print(state: WorkflowState | dict[str, Any]) -> None:
    data = state.to_dict() if isinstance(state, WorkflowState) else state
    print(json.dumps(data, ensure_ascii=False, indent=2))


def _die(state: WorkflowState, message: str, state_name: str = "failed") -> WorkflowState:
    state.completion_state = state_name
    state.next_action = message
    state.missing_or_failed.append(message)
    return state


def _slug(value: str) -> str:
    value = DOI_RE.search(value).group(0) if DOI_RE.search(value) else value
    return re.sub(r'[<>:"/\\|?*\x00-\x1f\s.]+', "_", value.strip()).strip("_")[:120] or "mof_input"


def _script_root() -> Path:
    return Path(__file__).resolve().parent


def _skill_root() -> Path:
    return _script_root().parent


def _find_project_root(explicit: str | None) -> Path:
    candidates: list[Path] = []
    if explicit:
        candidates.append(Path(explicit))
    candidates.extend([
        Path.cwd(),
        Path(os.environ["MOF_PRICE_PROJECT"]) if os.environ.get("MOF_PRICE_PROJECT") else None,
        _skill_root().parent,
    ])
    required = [
        "extract/text_extractor.py",
        "enrich/chembook_scraper.py",
        "report.py",
    ]
    for base in [candidate for candidate in candidates if candidate is not None]:
        try:
            root = base.resolve()
        except OSError:
            continue
        if all((root / item).exists() for item in required):
            return root
    raise FileNotFoundError("Cannot find project root with extract/, enrich/, and report.py.")


def _run(cmd: list[str], cwd: Path, state: WorkflowState) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            cmd,
            cwd=str(cwd),
            text=True,
            encoding="utf-8",
            errors="replace",
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
            timeout=state.stage_timeout,
        )
    except subprocess.TimeoutExpired as exc:
        stdout = exc.stdout if isinstance(exc.stdout, str) else ""
        return subprocess.CompletedProcess(
            cmd,
            124,
            stdout=stdout,
            stderr=f"Command timed out after {state.stage_timeout}s: {' '.join(cmd)}",
        )
    except Exception as exc:  # pragma: no cover - defensive
        state.missing_or_failed.append(f"Command failed to start: {' '.join(cmd)}: {exc}")
        raise


def _count_csv_rows(path: Path) -> int:
    if not path.exists():
        return 0
    with path.open(encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


def _detect(input_value: str) -> tuple[str, Path | None, str | None]:
    text = input_value.strip().strip('"')
    p = Path(text)
    if p.exists():
        if p.is_dir():
            if list(p.glob("*.pdf")):
                return "pdf_folder", p, None
            return "directory", p, None
        suffix = p.suffix.lower()
        if suffix == ".pdf":
            return "pdf", p, None
        if suffix == ".txt":
            content = p.read_text(encoding="utf-8", errors="ignore")
            stripped = content.strip()
            if CAS_RE.fullmatch(stripped):
                return "single_cas", None, stripped
            if DOI_RE.search(content) and len(content.strip().splitlines()) <= 100:
                return "doi_text_file", p, None
            return "cleaned_txt", p, None
        if suffix in {".json"}:
            return "agent_json", p, None
        if suffix in {".csv", ".tsv", ".xlsx", ".xls"}:
            # Existing prefix may be passed as a CSV path.
            if suffix == ".csv" and p.name.endswith(("_routes.csv", "_reagents.csv", "_enriched.csv", "_pricing.csv")):
                stem = re.sub(r"_(routes|reagents|enriched|pricing)\.csv$", "", str(p), flags=re.I)
                return "csv_prefix", Path(stem), None
            return "doi_table", p, None
    if DOI_RE.fullmatch(text) or DOI_RE.search(text):
        return "doi", None, DOI_RE.search(text).group(0)
    if CAS_RE.fullmatch(text):
        return "single_cas", None, text
    prefix = Path(text)
    if any(prefix.parent.glob(prefix.name + "_*.csv")):
        return "csv_prefix", prefix, None
    return "unknown", p, None


def _cnki_preflight_fallback(input_value: str, state: WorkflowState) -> WorkflowState:
    try:
        from cnki_doi_preflight import preflight
    except Exception as exc:
        return _die(state, f"Cannot import CNKI DOI preflight helper: {exc}")

    data = preflight(input_value, timeout=min(10, max(1, state.stage_timeout)))
    state.input_type = "doi"
    state.counts["cnki_preflight_elapsed_ms"] = int(data.get("elapsed_ms") or 0)
    state.counts["routes"] = 0
    state.counts["reagents"] = 0
    if data.get("status") != "reachable":
        return _die(state, f"CNKI DOI preflight failed: {data.get('error') or 'metadata unavailable'}", "failed")

    title = data.get("title") or ""
    scope = data.get("material_scope") or "unknown"
    state.created_files = []
    if scope == "not_mof":
        state.completion_state = "evidence_boundary"
        state.next_action = (
            f"CNKI DOI preflight resolved a non-MOF/COF/coordination-polymer title: {title}. "
            "Do not infer MOF routes/reagents/prices; ask for a non-MOF workflow or the paper PDF/experimental section."
        )
        state.missing_or_failed.append("Input is outside MOF/COF/coordination-polymer scope.")
        return state

    state.completion_state = "evidence_boundary"
    state.next_action = (
        "CNKI DOI metadata is reachable, but no MOF project root/full text is available. "
        "Provide a local PDF, exported text, or project root to continue."
    )
    state.missing_or_failed.append("Project root/full text unavailable after CNKI metadata preflight.")
    return state


def _needs_agent_from_text(path: Path, prefix: Path, state: WorkflowState, input_type: str = "cleaned_txt") -> WorkflowState:
    text = path.read_text(encoding="utf-8", errors="ignore")
    state.input_type = input_type
    state.prefix = str(prefix)
    state.add_file(path)
    if len(text.strip()) < 500 or not SYNTHESIS_HINT_RE.search(text):
        return _die(
            state,
            "Cleaned text is too short or lacks synthesis/procedure evidence.",
            "evidence_boundary",
        )
    state.completion_state = "needs_agent_extraction"
    state.next_action = (
        "Read cleaned_text, produce agent JSON with synthesis_routes/reagents/summary/feasibility, "
        "then run this helper on that JSON to continue enrichment and report."
    )
    state.counts["cleaned_text_chars"] = len(text)
    return state


def _extract_pdf(pdf: Path, prefix: Path, project_root: Path, state: WorkflowState) -> WorkflowState:
    out_txt = prefix.parent / f"{prefix.name}_cleaned.txt"
    out_txt.parent.mkdir(parents=True, exist_ok=True)
    cmd = [sys.executable, "extract/text_extractor.py", str(pdf), "-o", str(out_txt), "--preview", "0"]
    result = _run(cmd, project_root, state)
    if result.returncode != 0:
        return _die(state, result.stderr.strip() or result.stdout.strip() or "PDF text extraction failed.")
    if not out_txt.exists() or not out_txt.read_text(encoding="utf-8", errors="ignore").strip():
        return _die(state, "PDF text extraction returned no usable text; OCR/manual text is required.", "evidence_boundary")
    state.add_file(out_txt)
    return _needs_agent_from_text(out_txt, prefix, state, input_type=state.input_type)


def _download_doi(doi: str, link: str, prefix: Path, project_root: Path, state: WorkflowState) -> WorkflowState:
    downloads = project_root / "downloads"
    downloads.mkdir(exist_ok=True)

    fallback_pdf = _download_link_fallback(doi, link, downloads, state)
    if fallback_pdf:
        state.add_file(fallback_pdf)
        return _extract_pdf(fallback_pdf, prefix, project_root, state)

    try:
        sys.path.insert(0, str(project_root))
        from fetch.paper_fetcher import fetch_pdf  # type: ignore
    except Exception as exc:
        return _die(state, f"Cannot import DOI fetch tools: {exc}")

    # Keep this deterministic and secret-free: do not instantiate the project
    # Config class because it reads DEEPSEEK_API_KEY from .env/env by default.
    cfg = SimpleNamespace(
        fetch_timeout=60,
        scrape_retry=3,
        scrape_delay_min=1.0,
        scrape_delay_max=3.0,
        unpaywall_email=os.environ.get("UNPAYWALL_EMAIL", ""),
        scihub_mirrors=[
            "https://sci-hub.ee",
            "https://sci-hub.ru",
        ],
    )
    pdf_result = fetch_pdf(doi, cfg, downloads)
    if pdf_result.status == "fetch_failed" or not pdf_result.pdf_path:
        return _die(state, pdf_result.error or "PDF download failed.")
    state.add_file(pdf_result.pdf_path)
    return _extract_pdf(Path(pdf_result.pdf_path), prefix, project_root, state)


def _handle_single_cas(cas: str, output_dir: Path, project_root: Path, state: WorkflowState) -> WorkflowState:
    prefix = output_dir / cas.replace("/", "-")
    state.input_type = "single_cas"
    state.prefix = str(prefix)
    cmd = [
        sys.executable,
        "enrich/chembook_scraper.py",
        cas,
        "--name",
        "compound",
        "-o",
        str(prefix),
    ]
    result = _run(cmd, project_root, state)
    pricing_csv = prefix.parent / f"{prefix.name}_pricing.csv"
    if pricing_csv.exists():
        state.add_file(pricing_csv)
        state.counts["price_entries"] = _count_csv_rows(pricing_csv)
    if result.returncode != 0 and not pricing_csv.exists():
        return _die(state, result.stderr.strip() or result.stdout.strip() or "Single CAS enrichment failed.")
    state.completion_state = "complete" if pricing_csv.exists() else "degraded_complete"
    state.next_action = "Use the pricing CSV as single-CAS scraper/debug evidence; this is not a full paper pipeline."
    if result.returncode != 0:
        state.missing_or_failed.append(result.stderr.strip() or result.stdout.strip() or "Single CAS enrichment had warnings.")
    return state


def _download_link_fallback(doi: str, link: str, downloads: Path, state: WorkflowState) -> Path | None:
    """Best-effort direct PDF fallback for doi,link tables.

    The link column is often a DOI landing page, which may still be blocked; only
    accept responses that are real PDF bytes so we do not save HTML as a paper.
    """
    if not link or not link.lower().startswith(("http://", "https://")):
        return None
    try:
        import requests
    except Exception as exc:
        state.missing_or_failed.append(f"Direct link fallback unavailable: requests import failed: {exc}")
        return None

    candidates = [link]
    parsed = urlparse(link)
    if parsed.netloc.lower().endswith("doi.org"):
        return None
    if link.lower().endswith(".pdf") is False and "/pdf" not in link.lower():
        candidates.extend([
            link.rstrip("/") + ".pdf",
            link.replace("/article/", "/content/pdf/").rstrip("/") + ".pdf",
        ])

    headers = {"User-Agent": "Mozilla/5.0", "Accept": "application/pdf,text/html,*/*;q=0.8"}
    safe = _slug(doi)
    for url in dict.fromkeys(candidates):
        try:
            resp = requests.get(url, headers=headers, timeout=state.stage_timeout, allow_redirects=True)
            if resp.status_code >= 400:
                continue
            content = resp.content
            content_type = resp.headers.get("content-type", "").lower()
            final_url = unquote(resp.url)
            if not (content.startswith(b"%PDF-") or "application/pdf" in content_type or final_url.lower().endswith(".pdf")):
                continue
            if not content.startswith(b"%PDF-"):
                continue
            downloads.mkdir(parents=True, exist_ok=True)
            out = downloads / f"{safe}_link.pdf"
            out.write_bytes(content)
            return out
        except Exception as exc:
            state.missing_or_failed.append(f"Direct link fallback failed for {url[:120]}: {exc}")
    return None


def _read_doi_pairs(path: Path, project_root: Path, state: WorkflowState) -> list[tuple[str, str]]:
    suffix = path.suffix.lower()
    prepared = path
    if suffix in {".csv", ".xlsx", ".xls", ".tsv"} and not path.name.endswith("_prepared_dois.csv"):
        prepared = path.with_name(path.stem + "_prepared_dois.csv")
        cmd = [sys.executable, str(_script_root() / "prepare_doi_csv.py"), str(path), "-o", str(prepared)]
        result = _run(cmd, project_root, state)
        if result.returncode != 0:
            state.missing_or_failed.append(result.stderr.strip() or result.stdout.strip() or "DOI table normalization failed.")
            return []
        state.add_file(prepared)

    if prepared.suffix.lower() == ".txt":
        pairs = []
        for line in prepared.read_text(encoding="utf-8-sig", errors="ignore").splitlines():
            m = DOI_RE.search(line)
            if m:
                pairs.append((m.group(0), ""))
        return pairs

    delimiter = "\t" if prepared.suffix.lower() == ".tsv" else ","
    pairs: list[tuple[str, str]] = []
    with prepared.open(encoding="utf-8-sig", newline="") as f:
        sample = f.read(4096)
        f.seek(0)
        if "doi" not in sample.lower() and DOI_RE.search(sample):
            return [(m.group(0), "") for m in DOI_RE.finditer(sample)]
        reader = csv.DictReader(f, delimiter=delimiter)
        for row in reader:
            doi = row.get("doi", "").strip()
            link = row.get("link", "").strip()
            if doi:
                pairs.append((doi, link))
    return pairs


def _handle_batch(path: Path, project_root: Path, output_dir: Path, state: WorkflowState) -> WorkflowState:
    pairs = _read_doi_pairs(path, project_root, state)
    if not pairs:
        return _die(state, "No valid DOI values found in the input.", "failed")
    ledger_rows: list[dict[str, Any]] = []
    any_success = False
    for doi, link in pairs:
        prefix = output_dir / _slug(doi) / _slug(doi)
        child = WorkflowState(
            input=doi,
            input_type="doi",
            project_root=str(project_root),
            prefix=str(prefix),
            stage_timeout=state.stage_timeout,
        )
        child = _download_doi(doi, link, prefix, project_root, child)
        any_success = any_success or child.completion_state in {"needs_agent_extraction", "complete", "degraded_complete"}
        ledger_rows.append({
            "input": doi,
            "prefix": child.prefix,
            "status": child.completion_state,
            "next_action": child.next_action,
            "missing_or_failed": " | ".join(child.missing_or_failed),
        })

    output_dir.mkdir(parents=True, exist_ok=True)
    ledger_csv = output_dir / "batch_ledger.csv"
    ledger_json = output_dir / "batch_ledger.json"
    with ledger_csv.open("w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=["input", "prefix", "status", "next_action", "missing_or_failed"])
        writer.writeheader()
        writer.writerows(ledger_rows)
    ledger_json.write_text(json.dumps(ledger_rows, ensure_ascii=False, indent=2), encoding="utf-8")
    state.add_file(ledger_csv)
    state.add_file(ledger_json)
    state.batch_ledger = str(ledger_csv)
    state.counts["batch_inputs"] = len(pairs)
    for row in ledger_rows:
        key = f"batch_{row['status']}"
        state.counts[key] = state.counts.get(key, 0) + 1
    if any(r["status"] == "needs_agent_extraction" for r in ledger_rows):
        state.completion_state = "needs_agent_extraction"
        state.next_action = (
            "For every ledger row with status=needs_agent_extraction, read <prefix>_cleaned.txt, "
            "write <prefix>_agent_extraction.json with Codex agent extraction, run this helper on each JSON, "
            "then summarize the final per-paper reports."
        )
    elif any_success:
        state.completion_state = "degraded_complete"
        state.next_action = "Review the ledger; no remaining row is waiting for agent extraction."
    else:
        state.completion_state = "failed"
        state.next_action = "No DOI could be downloaded/extracted; provide local PDFs or direct PDF links."
    if not any_success:
        state.missing_or_failed.append("No DOI could be downloaded/extracted.")
    return state


def _continue_from_json(json_path: Path, prefix: Path, project_root: Path, state: WorkflowState, skip_enrich: bool, skip_report: bool, price_mode: str = "fast") -> WorkflowState:
    cmd = [sys.executable, str(_script_root() / "write_agent_outputs.py"), str(json_path), str(prefix)]
    result = _run(cmd, project_root, state)
    if result.returncode != 0:
        return _die(state, result.stderr.strip() or result.stdout.strip() or "Agent JSON validation/write failed.", "evidence_boundary")
    for suffix in ["_agent_extraction.json", "_synthesis_summary.md", "_feasibility.json", "_routes.csv", "_reagents.csv"]:
        p = prefix.parent / f"{prefix.name}{suffix}"
        if p.exists():
            state.add_file(p)
    if skip_enrich:
        state.completion_state = "complete"
        state.counts.update({
            "routes": _count_csv_rows(prefix.parent / f"{prefix.name}_routes.csv"),
            "reagents": _count_csv_rows(prefix.parent / f"{prefix.name}_reagents.csv"),
        })
        state.next_action = "Run router again without --skip-enrich to scrape pricing/GHS and generate reports."
        return state
    return _enrich_and_report(prefix, project_root, state, skip_report=skip_report, price_mode=price_mode)


def _required_csv_status(prefix: Path) -> tuple[list[str], dict[str, int]]:
    required_headers = {
        "_routes.csv": {"route_index", "target_compound", "procedure_text", "source"},
        "_reagents.csv": {"name", "role", "route_index", "target_compound"},
    }
    missing: list[str] = []
    counts: dict[str, int] = {}
    for suffix, required in required_headers.items():
        path = prefix.parent / f"{prefix.name}{suffix}"
        label = suffix.removeprefix("_").removesuffix(".csv")
        if not path.exists():
            missing.append(f"Missing required CSV: {path}")
            counts[label] = 0
            continue
        with path.open(encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f)
            headers = set(reader.fieldnames or [])
            absent = sorted(required - headers)
            if absent:
                missing.append(f"{path} is missing required column(s): {', '.join(absent)}")
            rows = list(reader)
            counts[label] = len(rows)
            if not rows:
                missing.append(f"{path} has no data rows.")
    return missing, counts


def _enrich_and_report(prefix: Path, project_root: Path, state: WorkflowState, skip_report: bool = False, price_mode: str = "fast") -> WorkflowState:
    missing_required, required_counts = _required_csv_status(prefix)
    state.counts.update(required_counts)
    if missing_required:
        state.missing_or_failed.extend(missing_required)
        state.next_action = "Provide a complete CSV prefix with valid *_routes.csv and *_reagents.csv, or rerun from agent JSON."
        state.completion_state = "failed"
        return state

    reagents_csv = prefix.parent / f"{prefix.name}_reagents.csv"

    enriched_csv = prefix.parent / f"{prefix.name}_enriched.csv"
    pricing_csv = prefix.parent / f"{prefix.name}_pricing.csv"
    if not (enriched_csv.exists() and pricing_csv.exists()):
        result = _run([sys.executable, "enrich/chembook_scraper.py", "--batch", str(prefix), "--price-mode", price_mode], project_root, state)
        if result.returncode != 0:
            state.missing_or_failed.append(result.stderr.strip() or result.stdout.strip() or "Pricing/GHS enrichment failed.")
            state.completion_state = "degraded_complete"
            state.next_action = "Review enrichment failure; report generation may still be possible if enriched/pricing CSVs exist."
        profile_csv = prefix.parent / f"{prefix.name}_pricing_profile.csv"
        for p in [enriched_csv, pricing_csv, profile_csv]:
            if p.exists():
                state.add_file(p)

    if skip_report:
        state.completion_state = "complete"
        state.counts.update({
            "routes": _count_csv_rows(prefix.parent / f"{prefix.name}_routes.csv"),
            "reagents": _count_csv_rows(reagents_csv),
            "enriched_rows": _count_csv_rows(enriched_csv),
            "price_entries": _count_csv_rows(pricing_csv),
            "pricing_profile_rows": _count_csv_rows(prefix.parent / f"{prefix.name}_pricing_profile.csv"),
        })
        state.next_action = "Run router again without --skip-report to generate HTML/MD/PDF reports."
        return state

    result = _run([sys.executable, "report.py", str(prefix)], project_root, state)
    html = prefix.parent / f"{prefix.name}_report.html"
    md = prefix.parent / f"{prefix.name}_report.md"
    pdf = prefix.parent / f"{prefix.name}_report.pdf"
    for p in [html, md, pdf]:
        if p.exists():
            state.add_file(p)
    if result.returncode != 0 and not (html.exists() or md.exists()):
        return _die(state, result.stderr.strip() or result.stdout.strip() or "Report generation failed.")
    if result.returncode != 0 or not pdf.exists():
        state.completion_state = "degraded_complete"
        state.missing_or_failed.append("PDF report may be missing; HTML/MD report is the primary fallback.")
    elif state.completion_state not in {"degraded_complete"}:
        state.completion_state = "complete"

    state.counts.update({
        "routes": _count_csv_rows(prefix.parent / f"{prefix.name}_routes.csv"),
        "reagents": _count_csv_rows(reagents_csv),
        "enriched_rows": _count_csv_rows(enriched_csv),
        "price_entries": _count_csv_rows(pricing_csv),
        "pricing_profile_rows": _count_csv_rows(prefix.parent / f"{prefix.name}_pricing_profile.csv"),
    })
    state.next_action = "Open the report first; use CSV/JSON files for audit or continuation."
    return state


def run_auto(
    input_value: str,
    project_root_arg: str | None,
    output_dir_arg: str,
    skip_enrich: bool = False,
    skip_report: bool = False,
    stage_timeout: int = 600,
    price_mode: str = "fast",
) -> WorkflowState:
    state = WorkflowState(input=input_value, stage_timeout=stage_timeout)
    input_type, path, doi = _detect(input_value)
    state.input_type = input_type
    try:
        project_root = _find_project_root(project_root_arg)
    except Exception as exc:
        if input_type == "doi" and CNKI_RE.search(input_value):
            return _cnki_preflight_fallback(input_value, state)
        return _die(state, str(exc))
    state.project_root = str(project_root)
    output_dir = Path(output_dir_arg)
    if not output_dir.is_absolute():
        output_dir = project_root / output_dir

    if input_type == "unknown":
        return _die(state, "Input was not recognized as DOI, path, JSON, PDF, text, table, or CSV prefix.")
    if input_type == "directory":
        return _die(state, "Directory has no PDFs and is not a recognized CSV prefix.")

    if input_type == "doi":
        assert doi
        prefix = output_dir / _slug(doi) / _slug(doi)
        state.prefix = str(prefix)
        return _download_doi(doi, "", prefix, project_root, state)
    if input_type == "single_cas":
        assert doi
        return _handle_single_cas(doi, output_dir, project_root, state)
    if input_type == "doi_text_file":
        assert path
        return _handle_batch(path, project_root, output_dir / path.stem, state)
    if input_type == "doi_table":
        assert path
        return _handle_batch(path, project_root, output_dir / path.stem, state)
    if input_type == "pdf":
        assert path
        prefix = output_dir / path.stem
        state.prefix = str(prefix)
        return _extract_pdf(path, prefix, project_root, state)
    if input_type == "pdf_folder":
        assert path
        rows: list[dict[str, Any]] = []
        any_success = False
        for pdf in sorted(path.glob("*.pdf")):
            prefix = output_dir / path.name / pdf.stem
            child = WorkflowState(
                input=str(pdf),
                input_type="pdf",
                project_root=str(project_root),
                prefix=str(prefix),
                stage_timeout=state.stage_timeout,
            )
            child = _extract_pdf(pdf, prefix, project_root, child)
            any_success = any_success or child.completion_state == "needs_agent_extraction"
            rows.append({"input": str(pdf), "prefix": child.prefix, "status": child.completion_state, "next_action": child.next_action, "missing_or_failed": " | ".join(child.missing_or_failed)})
        ledger = output_dir / path.name / "batch_ledger.csv"
        ledger.parent.mkdir(parents=True, exist_ok=True)
        with ledger.open("w", newline="", encoding="utf-8-sig") as f:
            writer = csv.DictWriter(f, fieldnames=["input", "prefix", "status", "next_action", "missing_or_failed"])
            writer.writeheader()
            writer.writerows(rows)
        state.add_file(ledger)
        state.batch_ledger = str(ledger)
        for row in rows:
            key = f"batch_{row['status']}"
            state.counts[key] = state.counts.get(key, 0) + 1
        state.completion_state = "needs_agent_extraction" if any_success else "failed"
        state.next_action = (
            "For every ledger row with status=needs_agent_extraction, read <prefix>_cleaned.txt, "
            "write <prefix>_agent_extraction.json with Codex agent extraction, run this helper on each JSON, "
            "then summarize the final per-paper reports."
        ) if any_success else "No PDF in the folder produced usable text."
        return state
    if input_type == "cleaned_txt":
        assert path
        prefix = output_dir / path.stem.removesuffix("_cleaned")
        return _needs_agent_from_text(path, prefix, state)
    if input_type == "agent_json":
        assert path
        prefix = output_dir / path.stem.removesuffix("_agent_extraction")
        state.prefix = str(prefix)
        return _continue_from_json(path, prefix, project_root, state, skip_enrich=skip_enrich, skip_report=skip_report, price_mode=price_mode)
    if input_type == "csv_prefix":
        assert path
        state.prefix = str(path)
        return _enrich_and_report(path, project_root, state, skip_report=skip_report, price_mode=price_mode)
    return _die(state, f"Unhandled input type: {input_type}")


def main() -> int:
    parser = argparse.ArgumentParser(description="MOF skill deterministic workflow helper.")
    parser.add_argument("input", help="DOI, path, table, JSON, text, PDF, folder, or CSV prefix.")
    parser.add_argument("--project-root", help="Project root containing extract/, enrich/, report.py.")
    parser.add_argument("-o", "--output-dir", default="output/skill_runs", help="Output directory for generated artifacts.")
    parser.add_argument("--json", action="store_true", help="Print JSON status (default behavior).")
    parser.add_argument("--skip-enrich", action="store_true", help="Stop after validated routes/reagents CSVs are written from agent JSON.")
    parser.add_argument("--skip-report", action="store_true", help="Run enrichment if needed but skip report generation.")
    parser.add_argument("--stage-timeout", type=int, default=600, help="Seconds before a deterministic subprocess degrades or fails.")
    parser.add_argument("--price-mode", choices=["fast", "full"], default="fast", help="Pricing mode passed to enrichment.")
    args = parser.parse_args()

    # Do not inherit stale DeepSeek credentials into subprocess paths.
    os.environ.pop("DEEPSEEK_API_KEY", None)

    state = run_auto(
        args.input,
        args.project_root,
        args.output_dir,
        skip_enrich=args.skip_enrich,
        skip_report=args.skip_report,
        stage_timeout=args.stage_timeout,
        price_mode=args.price_mode,
    )
    _json_print(state)
    return 0 if state.completion_state in {"complete", "degraded_complete", "needs_agent_extraction", "evidence_boundary"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
