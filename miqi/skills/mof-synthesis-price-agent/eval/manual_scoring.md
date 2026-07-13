# MOF Synthesis Price Agent Eval

## Trigger Accuracy

- Recall target: valid DOI/PDF/text/JSON/CSV-prefix requests should trigger.
- Precision target: BVSE, LAMMPS, CIF cleaning, generic literature review, reaction prediction, automated purchasing, SDS/EHS certification, and regulatory compliance should not trigger.
- Ambiguous target: broad "整理 MOF 文献" style prompts should clarify the intended workflow.

## Output Quality

- The default path must stay DeepSeek-free and use Codex extraction plus deterministic router scripts.
- CSV outputs must conform to `references/schemas.md`.
- Final reports must separate completed, degraded, skipped, failed, and evidence-boundary stages.

## Reality Readiness

- Real samples are required for readiness claims; synthetic fixtures only prove schemas.
- Accept `needs_agent_extraction` as a valid Reality Run intermediate when DOI/PDF/text acquisition succeeds and cleaned text is created.
- Accept `evidence_boundary` when a real artifact cannot provide usable synthesis evidence, as long as the blocker is explicit.

## Privacy

- Redact local user paths, server names, OAuth/login traces, and credential-like strings before sharing eval excerpts.
