# CNKI DOI Preflight

Use this reference when a DOI or URL looks like a CNKI DOI, for example:

- `10.13815/j.cnki...`
- `https://link.cnki.net/doi/...`
- `https://doi.cnki.net/...`

## Fast Path

Before trying dynamic CNKI search pages, login-gated detail pages, or PDF download endpoints:

1. Run the CNKI preflight helper when available:

```powershell
python "<skill-dir>\scripts\cnki_doi_preflight.py" "<doi>"
```

2. Treat the returned JSON as a pre-acquisition evidence record.
3. If `material_scope` is `not_mof`, stop the MOF workflow at `evidence_boundary` unless the user explicitly asks to process non-MOF materials with a separate workflow.
4. If `material_scope` is `unknown` and only title/authors are available, continue acquisition only if the requested scope still fits MOF/COF/coordination-polymer extraction or the user provides a local PDF/text.
5. If CNKI PDF/full text is gated, do not spend more than one short retry path on dynamic search/API probing. Produce a metadata-only evidence-boundary report and ask for PDF, exported text, or experimental section evidence.

## Scope Rules

Positive title hints include:

- MOF, MOFs, metal-organic framework, metal organic framework
- COF, covalent organic framework
- coordination polymer, 配位聚合物
- 金属有机框架, 共价有机框架

Negative title hints include:

- LDH, LDHs, layered double hydroxide, 层状双金属氢氧化物
- electrocatalysis-only LDH, hydroxide, oxide, sulfide, phosphide, alloy, battery electrode, unless the title/text explicitly says MOF/COF/coordination polymer

When negative hints dominate and no positive MOF/COF/coordination-polymer hint appears, set `completion_state=evidence_boundary`; do not invent MOF routes or generic reagent lists.

## Encoding And Validation

- Read and write Chinese JSON/Markdown with explicit UTF-8.
- In PowerShell validation, use `Get-Content -Encoding UTF8`, not the default encoding.
- Write CSVs with UTF-8-SIG when they are user-facing or Excel-targeted.

## Timing Discipline

Record coarse timing when a run hits a gated publisher path:

- DOI preflight time
- detail/PDF acquisition attempts and timeout count
- report-writing time
- final completion state

This timing note can be a short section in the final answer or a `timing` object in metadata JSON. It helps distinguish real extraction cost from access-probing cost.
