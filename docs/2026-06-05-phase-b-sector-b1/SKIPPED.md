# SKIPPED — Phase B sector expansion (B1 run)

These items are part of the broader Phase B design but are **out of scope for this autonomous run**. Each is recorded with its blocker and recommended unblock path.

## B2 — activation (after gate #5)

**Blocker:** Needs ~6 months of forward PE-TTM accumulation before any wired sector index clears the `MIN_PE_POINTS=120` ∧ `MIN_PE_DAYS=180` maturity gate (csindex serves only a ~20-trading-day trailing window per call; no full-history backfill exists). Activation then requires **human sign-off (gate #5)** on the real NAV-vs-PE recommendation diff — explicitly a human-in-the-loop decision per source spec roadmap line 146.

**Recommended unblock path:** After maturation (tracked via the B1 per-slug ingest audit `audit_sector_ingest`), run a fresh short plan: produce the before/after diff (memo / opportunity / narrative valuation buckets, NAV-vs-PE band flips, Δpercentile) for matured slugs; resolve flags #7 (`sse_star_chip` 000685) and #16 (`csi_resource` 000819); obtain human sign-off; add reviewed slugs to `sector_index_grounding.activated_slugs`; ADR 0012 addendum + CHANGELOG + CONTEXT.md record the real diff. Also gated on Phase A index-path divergence-advisory validation (or B2 independently verifying it on the first matured slug).

## `中证机床ZZ` → `中证机床` universe rename

**Blocker:** Changing a fund's raw `tracked_index` alters `map_lookthrough` keys, report/selection grouping, and allocation dedup *before* any valuation alias map is consulted — so it is **not** byte-identical and would break B1's gate #2 invariant. Source spec §3.5 / §10 explicitly carve it out as a separate, separately-reviewed change.

**Recommended unblock path:** A standalone small PR that edits `config/universe/*.yaml` and re-baselines the affected grouping/dedup outputs, reviewed on its own. B1 handles the malformed `中证机床ZZ` purely via an alias (`"中证机床zz" → csi_machine_tool`) in `SECTOR_INDICES`, so no universe edit is needed now.

## Sector PB source spike

**Blocker:** csindex carries no PB column for sectors (verified). PE-only is an intentional, documented gap (PB is corroborate-only per ADR 0012 §5).

**Recommended unblock path:** A separate source spike to find/validate a sector PB history source, out of scope here.

## Gate #4 live identity+PE confirmation (execution)

**Blocker (partial):** B1 *authors* the live identity guard test, but its **execution against live AkShare** (`IRC_RUN_LIVE_AKSHARE=1`) is a network/live hard stop — not run in the autonomous CI-style flow. Flags #7 (`sse_star_chip` 000685 absent from `index_csindex_all`) and #16 (`csi_resource` 000819 display≠official) require human confirmation **before B2 activation**.

**Recommended unblock path:** Operator runs `uv run pytest -m live_akshare` with `IRC_RUN_LIVE_AKSHARE=1` and records the identity+PE results; resolves #7/#16 ahead of B2. Not a blocker for B1 (allowlist empty → inert).
