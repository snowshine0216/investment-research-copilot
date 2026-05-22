# Investment Research Copilot — Domain Glossary

Canonical terms used in the opportunity / memo / discipline pipeline. Pointed to by the diagnosis doc, the workflow diagram, and code reviews. This file is a glossary, not a spec.

## Evidence & citation

- **Active fund** — an actively-managed CN equity fund (`asset_class="cn_equity_fund"`). The disclosed top-N holdings reflect manager judgement, so each holding receives its own evidence record. Subject to the **drill-through requirement**: per-constituent data + information legs (filing/NAV + broker/news).
- **Passive ETF / tracked index** — `asset_class="cn_etf"` or a tracked CN index. The fund is rule-based, so per-constituent qualitative evidence is **not** required. Investability is described at the **fund level**: NAV/return metrics as the data leg, ETF announcement (or `fund_announcement_em`) as the information leg. The "ANALYZE ONE by ONE" mandate does not apply to passive vehicles.
- **Drill-through requirement** — top-N holdings of an **active fund** must each carry their own data + information leg evidence. Does not apply to passive ETFs or tracked indices.
- **Data leg** — quantitative primary evidence (`citation_kind="data"`): filing digest, fund NAV report. Not opinion-derived.
- **Information leg** — narrative or opinion-bearing evidence (`citation_kind="information"`): broker report, news item, fund announcement. Filing-only never satisfies it.
- **Dual-coverage gate** — a publishable opportunity row requires ≥1 data-leg AND ≥1 information-leg citation, both from `scope in {"instrument", "constituent"}` and both with `owner_instrument_id == row.instrument_id`. Macro/policy scope alone never satisfies either leg.
- **Citation scope** — `instrument` (about the fund itself) | `constituent` (about a held stock) | `asset_class_macro` (theme report) | `policy` (regulatory). The first two are gate-satisfying; the latter two are supplemental.
- **Citation ID** — 16-char sha256 of `(instrument_id, scope, constituent_key, type, canonical_url_or_provider_id, date)`. Collision-resistant, not collision-proof; duplicates raise at construction time.
- **Scope precedence** (for selector tie-breaking and "fill-remaining" slots): `instrument > constituent > asset_class_macro > policy`. The instrument/constituent pair are the only scopes the dual-coverage gate accepts; macro/policy never satisfy the gate but appear in the fill-remaining tail.
- **Citation selector priority** (deterministic; used by the picks table and evidence pool to pick ≤3 citations per instrument): sort key per entry = `(scope_rank, kind_rank, holding_weight_pct, iso_date_recency, citation_id asc)`. The data slot picks the top `kind="data"` entry; the info slot picks the top `kind="information"` entry; remaining slot is filled by the same key minus the kind component. Two shuffled input orders must produce the same 3-entry output.
- **Contributing dimensions** — the subset of `{valuation, heat, thesis, product_quality}` whose sub-state drove the final `opportunity_state`. Derived deterministically from the four sub-states by `derive_contributing_dimensions` (Slice A0); never populated ad-hoc. The dual-coverage gate iterates this set so that each driver of the conclusion is independently cited.
