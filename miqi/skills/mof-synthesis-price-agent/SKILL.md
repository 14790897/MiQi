---
name: mof-synthesis-price-agent
description: Use when Codex needs to process MOF, COF, or coordination-polymer synthesis papers from /mof-synthesis-price-agent, DOI, doi/link CSV/TSV/XLSX, local PDF, cleaned text, agent JSON, or existing pipeline CSVs into synthesis routes, reagent lists, supplier pricing, GHS/fire-risk enrichment, feasibility screening, and HTML/Markdown/PDF reports. Use for Chinese or English requests such as 处理MOF论文, 提取MOF合成路线和试剂, 估算采购成本, 生成MOF采购/可行性报告, prepare DOI CSV for MOF papers, replace DeepSeek extraction with Codex agent extraction, or continue a MOF price pipeline. Do not use for BVSE ion migration, LAMMPS gas permeation, CIF cleaning, generic literature review, reaction prediction/design, automated purchasing, SDS/EHS approval, or regulatory compliance certification.
---

# MOF Synthesis Price Agent

Use this skill when the user invokes `/mof-synthesis-price-agent` or asks to run or continue the MOF synthesis/pricing/report workflow. The user provides an input plus a natural-language request; Codex handles internal routing and tool commands.

## Default Behavior

Default to the most complete workflow supported by the user's input:

1. Identify the input type: DOI, DOI CSV/TSV/XLSX, local PDF/file folder, cleaned `.txt`, agent JSON, or existing CSV prefix.
2. Run `scripts/mof_workflow.py <input>` as the deterministic router when an input path, DOI, or prefix is available.
3. If the router returns `needs_agent_extraction`, read the cleaned text, apply the extraction references, produce agent JSON, then run `scripts/mof_workflow.py <agent.json>` to continue.
4. Use Codex agent extraction for the former DeepSeek Call A/B/C/D and feasibility verdict.
5. Reuse deterministic project tools for PDF/SI download, text extraction, pricing/GHS enrichment, CSV writing, and report generation.
6. Report the completion state and evidence boundary.

Run a single stage only when the user explicitly asks for a named stage such as download only, extraction only, enrichment only, report only, feasibility only, rerun report, debug CAS, or prepare DOI CSV.

## Required References

Read only the reference files needed for the current task:

- `references/workflow.md`: input routing, stage map, completion states, and project command flow.
- `references/agent-extraction-rules.md`: mandatory rules for agent replacement of DeepSeek Call A/B/C/D and verdict.
- `references/agent-prompt-template.md`: ready-to-use extraction prompt template for cleaned text, validation repair, and long-text handling.
- `references/schemas.md`: JSON schemas, CSV headers, and validation requirements.
- `references/failure-handling.md`: stop/degrade/retry behavior.
- `references/evidence-boundaries.md`: scientific, pricing, safety, and compliance claim limits.
- `references/cnki-doi-preflight.md`: fast handling for CNKI DOI metadata, non-MOF scope checks, encoding, and gated-fulltext timing.
- `references/real-sample-validation.md`: Reality Run acceptance criteria and recommended real-paper smoke samples.

## Core Rules

- Do not require `DEEPSEEK_API_KEY`, `.env`, or any external LLM API for extraction. The Codex agent must produce structured routes, reagents, summaries, and feasibility verdicts directly from the evidence in the paper text and CSV artifacts.
- Do not call the original DeepSeek-bound full `pipeline.py`, `batch.py`, `llm/synthesis_extractor.py`, or `enrich/feasibility.py` on the default path. Use the router and deterministic stage scripts instead.
- Do not print, read aloud, store, or ask for secrets unless the user explicitly chooses to use an external API outside this skill's default path.
- Preserve the fixed boundary: MOF/COF/coordination-polymer synthesis information, reagent purchasing/pricing, GHS/fire-risk screening, and feasibility reporting. Do not expand into reaction prediction, automated purchasing, regulatory certification, or general literature review.
- For CNKI DOI inputs, especially `10.*j.cnki*` or `link.cnki.net/doi/...`, run the CNKI DOI preflight before dynamic search/PDF probing. If the resolved title is clearly not MOF/COF/coordination-polymer, stop at `evidence_boundary` and generate a metadata-only report instead of inventing routes, reagents, or prices.
- When publisher access is gated and only metadata is available, limit exploratory DOI/detail/PDF probing to short, bounded attempts; then produce an evidence-boundary output inventory and ask for PDF, exported text, or the experimental section.
- Keep claims evidence-bound. Prices are scraped/observed estimates; safety and fire-risk outputs are screening aids; SDS/EHS review remains required before lab work.
- For each material/reagent, keep only the top 10 value quotes in detailed pricing outputs and reports, sorted by positive CNY price ascending. Do not flood the final Markdown with all scraped supplier rows.
- Render all money in reports as ASCII `CNY 97.00`; do not use `¥`, `￥`, or the mojibake character `楼` in HTML, Markdown, or PDF outputs.
- Show a purchase link only when it has been verified as a reachable direct supplier product page. If a quote has a price but the product URL cannot be live-verified, keep the price for screening and mark the link as unverified/blank rather than emitting a fake or dead buy link.
- Validate all agent-generated JSON against `references/schemas.md` before writing CSVs. If validation fails, self-repair once using the validation error and source evidence. If it still fails, stop at an evidence boundary instead of writing misleading outputs.
- Mark degraded completion when optional outputs fail but core evidence is still useful, such as HTML/MD report generated but PDF rendering failed, pricing partially unavailable, SI download failed, or optional supplier source blocked.
- Treat hand-written fixtures as schema tests only. The skill is reality-ready only after at least one real DOI/PDF/text sample reaches `complete`, `degraded_complete`, `needs_agent_extraction`, or a documented `evidence_boundary` with output inventory.

## Tooling Pattern

- Prefer the existing project root in the current workspace when files such as `extract/text_extractor.py`, `enrich/chembook_scraper.py`, and `report.py` are present.
- On the known `g0048` server (`ruiqi@36.103.234.242`, port `2242`), use `/home/ruiqi/miniconda3/envs/mofsimbench/bin/python` as the preferred Python interpreter for this skill before searching other environments. Verified imports include `pandas`, `openpyxl`, `requests`, `bs4`, `lxml`, `pdfplumber`, `fitz`/PyMuPDF, `reportlab`, `pypdf`, `html5lib`, `tabulate`, plus the scientific packages used by neighboring MOF skills.
- On the local Codex desktop runtime, the default `python` already imports `pandas`, `openpyxl`, `requests`, `bs4`, `lxml`, `pdfplumber`, and `reportlab`; use server Python only when the input/project/output is intended to run on the server.
- Start with `scripts/mof_workflow.py <input>` for DOI, DOI files/tables, PDF/PDF folders, cleaned text, agent JSON, or existing CSV prefixes. Treat its JSON output as the run contract.
- If no MOF project root is available and the input is a CNKI DOI, run `scripts/cnki_doi_preflight.py <doi>` as a lightweight fallback before reporting failure. Use its metadata to decide whether the correct state is `evidence_boundary` rather than `failed`.
- Use `scripts/write_agent_outputs.py` only through the router unless debugging schema validation.
- Use `scripts/prepare_doi_csv.py` through the router when the user provides a spreadsheet or loose DOI/link table that needs normalization to `doi,link`.
- Let `scripts/mof_workflow.py` call deterministic project commands for text extraction, pricing/GHS enrichment, and report generation. Do not show those commands to the user unless debugging.

## Agent Extraction Handoff

When `mof_workflow.py` returns `completion_state: needs_agent_extraction`:

1. Read `references/agent-extraction-rules.md`, `references/agent-prompt-template.md`, `references/schemas.md`, and `references/evidence-boundaries.md`.
2. If `batch_ledger` is present, process every ledger row whose `status` is `needs_agent_extraction`; otherwise process the single returned `prefix`.
3. For each prefix, read the cleaned text path listed in `created_files` or `prefix + "_cleaned.txt"`.
4. Produce one JSON file named `prefix + "_agent_extraction.json"` with `synthesis_routes`, `reagents`, `synthesis_summary`, and optional `feasibility`.
5. Run `scripts/mof_workflow.py <agent_json>` to validate, write CSVs, enrich prices/GHS, and generate reports.
6. If JSON validation fails, repair once using the validation error and source evidence. Stop that paper at `evidence_boundary` if it fails again.
7. For batch runs, update the user-facing summary from the ledger plus every final router status; do not stop after only creating the ledger.

## Completion Report

Finish with:

- Input used and stage(s) run.
- Output paths created or reused.
- Counts: routes, reagents, enriched rows, price entries when available.
- Completion state: `complete`, `degraded_complete`, `needs_agent_extraction`, `failed`, or `evidence_boundary`.
- Skipped/failed stages and next action.
- Coarse timing when access probing or dynamic publisher pages consumed meaningful time.
- Explicit caveat that safety/pricing conclusions are screening outputs when relevant.
- Reality Run evidence when claiming readiness: real input type, command/tool path used, outputs created, degraded stages, and privacy/evidence-boundary result.
