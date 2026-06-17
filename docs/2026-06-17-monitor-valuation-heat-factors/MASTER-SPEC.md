# MASTER-SPEC — Monitor valuation + heat factor wiring

**Mode:** spec (single design doc → decomposed into the author's 3 vertical slices, N=3)
**Source spec:** [`docs/superpowers/specs/2026-06-17-monitor-valuation-heat-factors-design.md`](../superpowers/specs/2026-06-17-monitor-valuation-heat-factors-design.md)
**Run date:** 2026-06-17
**Feature branch:** `monitor-valuation-heat-wiring` (current; non-protected; already holds the design-spec commit `87c9b39`)
**Project type:** non-web (Python `irc` CLI) → post-ship verifier is `/verify`

## Why N=3 (not the spec-mode default N=1)

The input is a single design spec (so brainstorming is skipped and grill is pre-completed ⏭️ —
the user authored complete intent). But §9 of the spec explicitly mandates **three independent
vertical slices** with stated independent-landability, and the project favors small reviewable
PRs. So the loop runs three times with spec-mode authoring semantics: each slice gets its own
plan → branch → impl → drift → ship → verify → pr-review → fix → merge into the feature branch.
Per-item `spec.md` files are focused excerpts of the master design doc (verbatim slice text +
shared context); no per-item brainstorming/grill.

## In scope

| id | slice | title | lights | network | risk |
|----|-------|-------|--------|---------|------|
| 001 | §9.1 | Index-path valuation + vocab unification | `009225` (and `018132` when sector slug activated) | none (cache-read) | low — proves wiring + map end-to-end |
| 002 | §9.2 | Look-through valuation | the 6 pure active funds | none (cache-read) | **high** — reuses opportunity Phase-D derivation on monitor-loaded cached holdings + stock valuations; cached-coverage dependent |
| 003 | §9.3 | Heat (restriction leg) | heat for all 10 funds | 1 `ak.fund_purchase_em()` call/run | medium — schema-drift tolerant; AUM-Δ sharpening deferred |

**Ordering rationale:** 001 → 002 → 003. 001 is smallest and creates `valuation.py` with the
index path + the shared `percentile_to_valuation_state` helper + a `resolve_valuation_state`
dispatcher whose look-through branch returns honest N/A (placeholder). 002 fills in that
look-through branch (same module → keep the two valuation slices adjacent). 003 is fully
independent (new `heat_fetch.py` + heat wiring) and lands last.

## Out of scope (carried from the spec's Non-goals / §5 deferral)

- No change to `gold` / `qdii_global` valuation eligibility — they stay `profile_ineligible`.
- No new valuation **fetch** path (the `# TODO(post-v1)` narrow index-valuation refresh in
  `fetch.py:15` stays out; read cache, ship N/A on a miss).
- No re-weighting of profile vectors.
- **AUM-Δ heat leg deferred** — no per-fund live QoQ AUM source exists
  (`fund_scale_change_em` is aggregate-only). The overheated `−1.0` tier cannot fire yet; heat
  ships on the restriction leg alone (`−0.5` crowded / `+0.3` calm). Revisit when a per-fund
  AUM-history source lands. (This is a deferral, not a skipped item — see SKIPPED.md.)

## Grounding (verified at intake, 2026-06-17)

- `src/irc/commands/monitor_cmd.py:578` — `FactorInputs(...)`; lines 581–584 hardcode
  `valuation_state=None`, `valuation_cached=False`, `restricted=None`, `aum_delta_pct=None`.
- `src/irc/monitor/factor_maps.py:3` `_VALUATION_MAP`; `:10` `valuation_state_score`; `:15` `heat_score`.
- `src/irc/monitor/factors.py:60` valuation N/A gate; `:71` `heat_score(...)`.
- `src/irc/opportunity/lookthrough_valuation.py` — `HoldingWeight` (`:37`), `MetricSeries` (`:43`),
  `fund_valuation_percentile` (`:193`). All present; reuse targets confirmed.
