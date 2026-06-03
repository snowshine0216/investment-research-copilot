# SKIPPED — out-of-scope for this run

These are explicit non-goals / deferrals carried in the design spec. Recorded here so nothing is
silently omitted; each has a recommended unblock path.

## Phase 2 — holdings look-through (bottom-up, active funds)
**Blocker:** §5 designs this only as a sketch and flags an unresolved open method question
(percentile of constructed weighted-PE history vs. percentile-of-percentiles; top-10 truncation;
HK/US holdings with no A-share indicator coverage).
**Unblock:** ships its own spec after Phase 1 is validated against real output (per §5, §9).

## QDII fundamental valuation (US/HK index PE/PB)
**Blocker:** legulegu's index PE/PB endpoints are A-share-only (§2, §3 Q3). No US/HK
index-valuation source exists in the pipeline yet.
**Unblock:** add a US/HK index-valuation feed, then extend the `_BROAD_INDEX_KEYS` gate. QDII keeps
NAV percentile + premium-to-NAV until then.

## Sector-theme CN ETF coverage (半导体 / 医药 / 新能源 …)
**Blocker:** sector ETFs carry a `theme`, not a broad `tracked_index`, so the `_BROAD_INDEX_KEYS`
gate excludes them by design (§4.0).
**Unblock:** add the sector indices' legulegu names — an explicit follow-on, not Phase 1.

## CN CPI-YoY ingest (true real-yield instead of nominal gap)
**Blocker:** CN CPI is not ingested today; Phase 1 uses the nominal 10Y CGB (股债利差 reading)
for `real_yield_10y` (§3.1 R1).
**Unblock:** ingest a CN CPI-YoY macro series, then switch `real_yield_10y` to
`(cn_10y_yield − cpi_yoy)/100`. A one-line precedence change (§4.1).

## Phase-1 `+1` mean-reversion risk driver for divergence
**Blocker:** §3 Q4 / §6 explicitly defer — risk purely inherits the grounded valuation in Phase 1;
`derive_position_risk_level` is unchanged.
**Unblock:** add the mean-reversion severity driver in a later phase once divergence flags are
validated in real output.
