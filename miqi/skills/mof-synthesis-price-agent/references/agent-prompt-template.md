# Agent Prompt Template

Use this template when the task includes cleaned paper text and the agent must replace DeepSeek extraction.

## Extraction Prompt

```text
You are using $mof-synthesis-price-agent. Read these references first:
- references/agent-extraction-rules.md
- references/schemas.md
- references/evidence-boundaries.md

Task:
Extract MOF/COF/coordination-polymer synthesis information from the provided cleaned paper text.

Output one JSON object with:
{
  "synthesis_routes": [...],
  "reagents": [...],
  "synthesis_summary": "Markdown summary using the required Chinese section headings",
  "feasibility": null
}

Hard requirements:
- Do not use DeepSeek or any external LLM API.
- Use only the paper text as evidence.
- Preserve verbatim source evidence in source_text when available.
- Do not include final products as their own reagents.
- Use route_index=-1 only for true universal reagents.
- Use null instead of invented CAS, amount, equiv, or safety fields.
- If evidence is insufficient, return a short evidence-boundary explanation instead of guessing.

Paper text:
<<<PASTE CLEANED TEXT HERE>>>
```

## Validation Repair Prompt

Use once when `scripts/write_agent_outputs.py` rejects the JSON.

```text
The JSON failed validation:
<<<PASTE VALIDATION ERROR>>>

Repair only the JSON. Do not add prose. Keep all facts evidence-bound and do not invent missing data.
```

## Long Text Handling

If the cleaned text is too long for reliable extraction:

1. Identify synthesis, experimental, preparation, supporting information, and procedure sections.
2. Keep route-relevant paragraphs plus enough surrounding context for target names and route mapping.
3. Exclude references, author info, characterization-only sections, catalysis tests, NMR/XRD/BET/TGA tables, and unrelated ligand-upstream details unless they directly define a MOF route reagent.
4. Run extraction on the condensed evidence.
5. Record that long-text condensation was performed in the final completion report.

## Batch Handling

For multiple papers, process one paper at a time and keep a per-paper ledger:

| paper_id | input | prefix | status | routes | reagents | degraded_reason | next_action |
| --- | --- | --- | --- | --- | --- | --- | --- |

Mixed success across a batch is `degraded_complete`, not total failure, when at least one paper produces usable outputs.
