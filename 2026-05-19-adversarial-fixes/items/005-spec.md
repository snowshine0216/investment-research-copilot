# 005 — Bond valuation uses yield anchor

## Why

The 2026-05-19 opportunity report has three CNY bond instruments with
wildly different `valuation_state`:

- `000111 易方达纯债1年定开债A` → `cheap` (percentile 14%)
- `511520 政金债ETF富国` → `very_expensive`
- `000134 中信保诚嘉鸿债券A` → `fair`

The adversarial review (§B1) flags this as a methodology error:
`classify_valuation()` in `opportunity/states.py` uses each instrument's
**own NAV price percentile** as the valuation signal, which is a
momentum/mean-reversion proxy. That has no economic interpretation for a
1-year duration pure-bond fund — the right anchor is yield-to-maturity
vs the curve, or 10Y yield percentile vs the 5–10y range, or the spread
to the PBOC policy rate.

## What changes

1. In `src/irc/opportunity/types.py`, add an optional field to
   `OpportunityInput`:
   - `cn_bond_yield_percentile: float | None` — 10Y CGB yield percentile
     vs the 5–10y rolling window; same semantic direction as
     `valuation_percentile_self` (low percentile = cheap = high yield).
2. In `src/irc/opportunity/states.py`:
   - Add a new function `classify_bond_valuation(inp)` that:
     - Returns `evidence_insufficient` if both
       `cn_bond_yield_percentile` and `valuation_percentile_self` are None.
     - Otherwise uses `cn_bond_yield_percentile` (if present) with the same
       band thresholds as `classify_valuation` BUT inverted on direction:
       low yield-percentile means yields are LOW means bonds are
       EXPENSIVE. So `cheap` ⇔ yield-pct ≥ 0.80.
   - Update the dispatcher (whatever calls `classify_valuation`) so rows
     with `asset_class in {cn_bond_fund}` go through
     `classify_bond_valuation`. (Bond ETFs that track a single
     pure-bond index also count.)
3. In `src/irc/opportunity/inputs_loader.py`, populate
   `cn_bond_yield_percentile` from a new field on the macro snapshot
   produced by the ingest stage. If the snapshot doesn't have it yet
   (existing inputs won't), accept `None` and let the bond classifier
   degrade to `evidence_insufficient` with a clear rationale.

## Acceptance criteria

- `opportunity_report.json` rows for cn_bond_fund show
  `valuation_state` derived from yield percentile (or
  `evidence_insufficient` with explanation), never from NAV percentile.
- New unit tests cover the three bands cheap/fair/expensive on
  yield-percentile inputs, plus the evidence-insufficient fallback.

## Tests to add

- `tests/opportunity/test_bond_valuation.py`:
  - yield_percentile=0.85 → cheap
  - yield_percentile=0.50 → fair
  - yield_percentile=0.10 → very_expensive
  - both inputs None → evidence_insufficient
