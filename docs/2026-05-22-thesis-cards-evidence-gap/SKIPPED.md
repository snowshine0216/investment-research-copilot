# Skipped items (with reasons)

| id  | title | source slice | reason for skipping |
|-----|-------|--------------|---------------------|
| C   | sector-themed-news-routing | Slice C (C1, C2) | Source diagnosis §3 Slice C explicitly defers to V2. C1 cannot work in V1 because per-sector report files do not exist in `data/research/` — the 7 files there (`cn_equity_property_policy`, `cn_monetary`, `geopolitics`, `gold_drivers`, `holdings_sector`, `us_fiscal_politics`, `us_monetary`) are macro-themed, not sector-themed. The "gold news in a consumer fund" symptom that motivated Slice C is partly resolved by item 003 (per-fund `thesis_evidence` is now per-stock with `scope="constituent"` evidence) and fully resolved when sector reports exist. C2 (V2) requires new `irc research --sector <name>` content authoring for 8–10 sector reports (consumer, tech, healthcare, semiconductor, new_energy, finance, defense, real_estate, metals, soe) — a separate content-authoring lift outside this run's scope. |

## Recovery path for V2

To unblock Slice C in a future run:

1. Author 8–10 sector-themed reports under `data/research/<sector>.md`.
2. Add a dominant-sector resolver next to `_resolve_research_theme` in `commands/opportunity_cmd.py` that consumes the `ConstituentAnalysis` weights (item 003 output) to pick the dominant sector.
3. Route the dominant-sector report through `derive_thesis_from_evidence`'s Path B (theme_report only), keeping the existing constituent-evidence path as primary.
4. Update E2 to assert themed `cn_equity_fund` resolves to `active_fund` (already covered by item 003) AND that the chosen `theme_report` matches the dominant sector.
