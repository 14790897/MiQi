# Agent Extraction Rules

These rules replace the SOP's DeepSeek Call A/B/C/D and feasibility verdict. The Codex agent must use only paper text, existing CSV artifacts, and scraped enrichment data as evidence.

## Call A: Synthesis Routes

Output `{"synthesis_routes": [...]}`.

Rules:

- Extract final characterizable MOF/COF/coordination-polymer products, not isolated intermediates unless the paper treats them as final tested materials.
- Merge dependent steps into one route when a later step uses an earlier product as precursor, including post-synthetic modification, anion exchange, metalation, oxidation/reduction, vapor/thermal treatment, or solvent exchange that creates the final material.
- Merge variants that differ only by metal, counterion, modulator, solvent, or closely related substituent when the procedure is the same; list all target names in `target_compound`.
- Keep explicit control or optimization routes separate when they skip a step or intentionally compare conditions.
- For fully referenced syntheses with no procedure in the paper, set `source_text` to null or the minimal quoted evidence and do not invent details.
- `procedure_text` should summarize from commercial/lab-available starting materials to final product, preferably in Chinese and <=200 Chinese characters when possible.
- `source_text` must be verbatim evidence from the paper when available. Do not paraphrase it.

Pre-output checks:

- No route target should appear as a reagent in its own route.
- No intermediate route should remain if another route consumes it to make a final target.
- Route indices are zero-based in downstream CSV.

## Call B: Reagents

Output `{"reagents": [...]}` using the routes from Call A.

Rules:

- Extract only reagents used to make the MOF/COF/coordination-polymer route, not catalytic test substrates, characterization chemicals, or unrelated ligand-upstream purification chemicals.
- Assign every reagent to the route where it is actually used. Use `route_index=-1` only when the same reagent appears with the same role and substantially same use across all routes.
- Do not include any route's final `target_compound` as a reagent for that same route.
- Include commercial ligands, metal salts, solvents, modulators, catalysts, and workup/solvent-exchange reagents that directly affect the final material synthesis.
- Use role values only: `reactant`, `solvent`, `catalyst`, `ligand`, `modulator`, `workup`.
- Use real CAS for commercial chemicals when known from paper text or reliable common-chemical knowledge. Use null for custom MOF/intermediate/coordination-complex products. Do not invent CAS.
- Fill `amount` when the paper gives it. Fill `equiv` when the value is numeric; otherwise place nonnumeric equivalents such as "excess" or "ca. 3 equiv" in `amount` or the procedure evidence rather than inventing a number.
- Preserve paper names in `name`; do not translate the primary name.

## Call C: Verification And Completion

Verify the reagent list against the text and route evidence.

- Mark a reagent confirmed when it appears by name, synonym, abbreviation, or chemically necessary SI-referenced step.
- Add missing direct synthesis reagents found during verification.
- Remove hallucinated reagents, final products, catalysis substrates, and ligand-upstream chemicals outside the MOF assembly route.
- If verification would remove >80% of Call B reagents, treat it as verification malfunction and fall back to Call B after reporting the issue.
- Deduplicate by `(normalized name, route_index, role)`.

## Call D: Synthesis Summary

Generate Markdown text, not JSON.

- Use sections:
  - `### 一、主合成路线（Primary）`
  - `### 二、对照/优化路线（Control）`
  - `### 三、引用路线（Reference）`
- Keep <=500 Chinese characters when possible.
- Summarize target materials, key ligand/metal sources, strategy, temperature, time, and key workup.
- Do not add unsupported reaction mechanisms or performance claims.

## Feasibility Verdict

Output `{"llm_verdict": "..."}` with <=100 Chinese characters.

- Base the verdict only on enriched reagent data, route data, pricing, GHS/fire-risk fields, controlled flags, and missing data.
- Mention specific high-risk or missing-data reagents when relevant.
- Do not state that synthesis is safe or approved; use screening language such as "建议先核对 SDS/EHS".

## Fire-Risk Fallback

Prefer scraped ChemicalBook/GHS/fire fields. If missing, the agent may infer cautiously from known chemical class and GHS evidence, but must mark the basis as inferred and use `unknown` when evidence is weak.
