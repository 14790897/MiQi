# Workflow Contract

## Input Routing

Choose the first matching route:

| Input | Default action | Required next evidence |
| --- | --- | --- |
| DOI such as `10.xxxx/...` | Run `scripts/mof_workflow.py <doi>`; download PDF/SI and extract text when project tooling is available | cleaned text and `needs_agent_extraction` |
| CSV/TSV/XLSX with `doi` and optional `link` | Run `scripts/mof_workflow.py <table>`; normalize DOI/link and batch deterministic acquisition | per-DOI cleaned text, ledger, or failure record |
| Local PDF or folder of PDFs | Extract text from each PDF | cleaned text |
| Cleaned `.txt` | Start agent extraction directly | paper text |
| Agent extraction JSON | Validate/write standard CSV, then enrich/report | matching route/reagent CSVs |
| Existing prefix with `*_routes.csv`, `*_reagents.csv`, `*_enriched.csv`, `*_pricing.csv` | Continue from the latest complete stage | matching CSV set |
| Single CAS | Run single-compound enrichment/debug only | CAS and optional compound name |

Inputs are alternatives, not all required. A full DOI/PDF workflow creates intermediate files automatically.

## Stage Map

| Stage | Purpose | Deterministic tool | Agent role | Output |
| --- | --- | --- | --- | --- |
| 0. Preflight | Identify input, project root, dependencies, output prefix | `scripts/mof_workflow.py` | decide route and stage scope | status JSON and output prefix |
| 1. Text acquisition | Download/extract/reuse paper text | `scripts/mof_workflow.py`, `fetch/*`, `extract/text_extractor.py`, or existing txt | judge if text is sufficient | `*_cleaned.txt` |
| 2. Structured extraction | Replace DeepSeek Call A/B/C/D | `scripts/write_agent_outputs.py` for writing | produce and validate routes, reagents, summary | `*_routes.csv`, `*_reagents.csv`, optional JSON |
| 3. Enrichment | Price/GHS/fire-risk data | `enrich/chembook_scraper.py --batch <prefix>` | handle missing evidence and inferred fire-risk caveats | `*_enriched.csv`, `*_pricing.csv` |
| 4. Feasibility | Cost/risk screening | optional JSON writer | produce feasibility JSON and <=100 char verdict | feasibility JSON or report metadata |
| 5. Report | Human-readable outputs | `report.py <prefix>` | summarize completion and caveats | `*_report.html`, `*_report.md`, `*_report.pdf` |

## Completion States

- `complete`: required stages for the requested scope succeeded and outputs exist.
- `degraded_complete`: core outputs exist but optional data is missing, such as SI, some pricing, one supplier source, or PDF report.
- `needs_agent_extraction`: deterministic acquisition succeeded and Codex must now read cleaned text, generate agent JSON, and call the router again.
- `failed`: requested scope cannot produce usable output due to invalid input, missing core tool, command failure, or corrupt artifact.
- `evidence_boundary`: source evidence is insufficient for a truthful extraction or claim, such as no text layer, too-short text, no synthesis section, or schema validation failure after one repair.

## Router Status JSON

`scripts/mof_workflow.py` returns:

```json
{
  "input_type": "pdf|cleaned_txt|agent_json|csv_prefix|doi|doi_table",
  "prefix": "output/skill_runs/example",
  "created_files": [],
  "next_action": "human-readable next step",
  "completion_state": "complete|degraded_complete|needs_agent_extraction|failed|evidence_boundary",
  "missing_or_failed": [],
  "counts": {}
}
```

Treat this JSON as the handoff contract. If `completion_state` is `needs_agent_extraction`, do not stop; perform Codex agent extraction and then rerun the router on the generated agent JSON.

## Default Commands

Use the router from the project root or any current workspace that contains the MOF project:

```powershell
python "<skill-dir>\scripts\mof_workflow.py" <input> --project-root "<mof-project-root>"
```

If `--project-root` is omitted, the router searches the current directory, `MOF_PRICE_PROJECT`, and nearby skill/project locations for `extract/`, `enrich/`, and `report.py`.

Do not call the original full `pipeline.py` or `batch.py` in the default path because those enter DeepSeek-bound extraction. Split the workflow through router acquisition, Codex agent extraction, router enrichment, and router report generation.
