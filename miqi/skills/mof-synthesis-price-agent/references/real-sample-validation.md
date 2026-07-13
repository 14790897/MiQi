# Real Sample Validation

Use this reference when validating that the MOF synthesis price workflow works on real evidence instead of synthetic fixtures.

## Reality Run Acceptance

A valid Reality Run must include:

- real input: DOI, publisher/author PDF, local PDF, cleaned text extracted from a real paper, or a DOI/link table pointing to real papers
- command/tool entrypoint: usually `scripts/mof_workflow.py <input> --project-root <project>`
- output inventory: cleaned text, agent JSON when extraction is needed, routes/reagents CSV, enrichment CSVs when available, and HTML/Markdown/PDF report when report generation is available
- completion state: `complete`, `degraded_complete`, `needs_agent_extraction`, `failed`, or `evidence_boundary`
- explicit caveats: pricing is scraped/observed screening data, safety is not SDS/EHS approval, and synthesis extraction is limited to paper evidence

## Recommended Smoke Samples

Use known real MOF papers with public DOI/PDF evidence when available:

- MOF-5 / IRMOF-1: DOI `10.1038/46248`; acceptable when a public author PDF or local PDF is available.
- HKUST-1 / MOF-199: DOI `10.1126/science.283.5405.1148`; acceptable when the PDF or cleaned text is already available.

If download is blocked, use a local PDF or cleaned text derived from the real paper. Record the blocker and keep the run at `needs_agent_extraction` or `evidence_boundary` instead of claiming full completion.

## Negative Reality Sample

Keep at least one real DOI that should stop cleanly at the scope boundary:

- CNKI DOI `10.13815/j.cnki.jmtc(ns).2025.02.002` resolves to `溶剂热法制备NiCo-LDHs及其电催化析氧性能研究`, a NiCo-LDH paper rather than a MOF/COF/coordination-polymer synthesis paper. A correct run should use CNKI DOI preflight, produce metadata-only `evidence_boundary` outputs, avoid generic reagent guesses, and mention that PDF/experimental text is required for any non-MOF synthesis/pricing workflow.

## Fixture Boundary

Synthetic or hand-written JSON/CSV fixtures are allowed only for:

- schema validation
- CSV writer smoke tests
- report rendering smoke tests

They do not prove extraction quality, DOI/PDF acquisition, scientific completeness, price availability, or reality readiness.
