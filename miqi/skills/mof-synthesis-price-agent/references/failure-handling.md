# Failure Handling

## Stop

Stop and report `failed` or `evidence_boundary` when:

- Input path does not exist.
- DOI/CSV contains no valid DOI-like values.
- PDF text extraction returns no usable text and OCR is not available.
- Cleaned text is too short or lacks synthesis/procedure evidence.
- Agent JSON fails schema validation after one repair attempt.
- Core project scripts are missing from the selected project root.
- A DOI preflight resolves to a clearly non-MOF/COF/coordination-polymer material, such as LDH/oxide/hydroxide/electrocatalyst-only papers without MOF evidence.
- Publisher or CNKI pages expose only metadata and no full text, SI, experimental section, or downloadable PDF after short bounded attempts.

## Degrade And Continue

Continue as `degraded_complete` when:

- SI download fails but main PDF text is usable.
- Some supplier sources are blocked, slow, or return no price.
- Some reagents have CAS but no price/GHS data.
- PDF report generation fails but HTML/Markdown report exists.
- Optional fire-risk inference is weak; mark `unknown` instead of inventing a class.

## Retry

- Retry transient network or scraper failures once when the command supports it.
- Do not change multiple parameter classes at once.
- Preserve logs or terminal summaries in the final report.
- For CNKI or other gated publisher paths, record coarse timing and timeout counts so future runs can identify access-probing waste.
- For agent JSON repair, provide the validation error and relevant source evidence, then retry once.

## Ask User

Ask for input when:

- Multiple plausible project roots exist and no current root contains the MOF pipeline scripts.
- The user requests a regulatory, purchasing, or safety approval action beyond screening.
- A commercial/license-sensitive download or credentialed access is required.
- The paper text is unavailable and no DOI/PDF/link is provided.
- A non-MOF paper was provided but the user still wants synthesis/pricing support under a different material workflow.

## Known Project-Specific Behaviors

- Existing `pipeline.py` and `batch.py` call DeepSeek-bound code in the original project. When using this skill's default agent path, avoid those calls for Step 3 and instead split the workflow into deterministic text extraction, agent extraction, enrichment, and reporting.
- `report.py` can generate HTML and Markdown even when PDF rendering has optional dependency issues.
- CAS-less custom intermediates should not be treated as failed pricing rows.
- PowerShell may misread UTF-8 Chinese files with the default encoding. Validate JSON/Markdown with `Get-Content -Encoding UTF8`; write user-facing CSV with UTF-8-SIG.
