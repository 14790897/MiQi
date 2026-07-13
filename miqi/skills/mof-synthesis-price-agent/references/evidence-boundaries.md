# Evidence Boundaries

## Supported Claims

The skill may claim:

- Routes and reagents were extracted from the provided paper text or SI evidence.
- Pricing and supplier links were observed from scraper outputs at run time.
- GHS/fire-risk fields came from scraped data or were explicitly marked as inferred/unknown.
- Feasibility is a screening estimate based on available reagent, price, hazard, and missing-data evidence.

## Unsupported Claims

Do not claim:

- The route is experimentally validated beyond what the paper reports.
- Prices are current, complete, lowest available in the market, or legally binding.
- A synthesis is safe, approved, compliant, or ready for lab execution.
- Fire-risk classification is official when inferred from partial evidence.
- The workflow predicts new reactions or designs new MOFs.
- The skill has purchased reagents or checked institutional procurement rules.

## Required Caveats

When reporting final results, include caveats when relevant:

- "价格为抓取时的在线报价/询价信息筛查，不代表真实采购成本。"
- "安全/GHS/火灾风险为实验前筛查，不替代 SDS 和 EHS 审核。"
- "缺少 CAS、GHS、报价或 SI 时，结论处于证据边界。"

## Privacy And Secrets

- Do not print API keys, cookies, tokens, or institutional credentials.
- Do not write real credentials into skill files or generated reports.
- Prefer local environment variables only when a user explicitly opts into an external service; this skill does not need DeepSeek by default.
