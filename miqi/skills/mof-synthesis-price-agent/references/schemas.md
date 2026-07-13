# Schemas And CSV Contract

## JSON Schemas

`SynthesisRoute`:

```json
{
  "target_compound": "string",
  "yield_percent": 78.0,
  "temperature": "105 C",
  "duration": "24 h",
  "atmosphere": "air",
  "procedure_text": "string",
  "source": "main_text",
  "route_type": "primary",
  "source_text": "verbatim text or null"
}
```

Required: `target_compound`, `procedure_text`, `source`. `source` must be `main_text` or `SI`. `route_type` defaults to `primary`.

`Reagent`:

```json
{
  "name": "DMF",
  "name_zh": null,
  "name_en": null,
  "cas": "68-12-2",
  "role": "solvent",
  "amount": "30 mL",
  "equiv": null,
  "route_index": 0,
  "is_controlled": false,
  "pricing": [],
  "fire_hazard": null,
  "fire_hazard_basis": null,
  "ghs_hazards": null,
  "scraped_at": null
}
```

Required: `name`, `role`, `route_index`, `is_controlled`. `role` must be one of `reactant`, `solvent`, `catalyst`, `ligand`, `modulator`, `workup`.

`PriceEntry`:

```json
{
  "supplier": "string",
  "spec": "500 mL",
  "purity": "99%",
  "price_cny": 88.0,
  "purchase_url": "https://example.com"
}
```

`Feasibility`:

```json
{
  "estimated_cost_cny": 188.0,
  "has_toxic_reagent": false,
  "has_high_fire_risk": false,
  "has_controlled_substance": false,
  "missing_data": [],
  "llm_verdict": "screening verdict"
}
```

## Agent Output Files

`scripts/write_agent_outputs.py` accepts:

```json
{
  "synthesis_routes": [],
  "reagents": [],
  "synthesis_summary": "",
  "feasibility": {}
}
```

At minimum, provide routes and reagents for Step 3 output.

## CSV Headers

`*_routes.csv`:

```text
route_index,target_compound,yield_percent,temperature,duration,atmosphere,procedure_text,source,route_type,source_text
```

`*_reagents.csv`:

```text
name,cas,role,amount,equiv,is_controlled,route_index,target_compound
```

`*_enriched.csv`:

```text
name,name_zh,name_en,cas,role,route_index,target_compound,ghs_hazards,fire_hazard,fire_hazard_basis,min_price_cny,cheapest_supplier,cheapest_spec,cheapest_url,pricing_count,scraped_at
```

`*_pricing.csv`:

```text
name,cas,role,route_index,supplier,spec,purity,price_cny,purchase_url
```

## Validation Rules

- `route_index` must be `-1` or a valid zero-based route index.
- A reagent name must not exactly match its own route target after normalization.
- Empty routes from sufficient synthesis text are an evidence-boundary stop.
- Empty reagents from sufficient synthesis text require one agent self-repair attempt.
- CSVs must be written with UTF-8-SIG for Excel compatibility.
