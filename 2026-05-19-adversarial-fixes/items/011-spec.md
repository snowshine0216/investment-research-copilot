# 011 — Scoring reweight for DCA horizon

## Why

`config/scoring.yaml` weights factors as:

    valuation_cost: 0.10   risk: 0.25   quality: 0.20
    macro_fit:      0.25   thesis_news: 0.20

The adversarial review (§G) flags three problems:

1. **valuation 10% is too low** for a long-horizon DCA strategy. Valuation
   dominates 5–10y forward returns (Shiller, AQR, Research Affiliates).
   Strategic-asset-allocation frameworks weight valuation 25–30%.
2. **macro_fit 25% is opaque** when `macro_view.yaml: active=false`.
   25% of the composite is driven by implicit heuristics with no user-set
   prior — high weight on an uninterrogable factor.
3. **thesis_news 20% is dangerous** when the news pipeline is broken
   (every instrument shows `thesis_news=50` filler).

## What changes

`config/scoring.yaml`:

```yaml
factor_weights:
  valuation_cost: 0.30   # was 0.10
  risk:           0.25   # unchanged
  quality:        0.20   # unchanged
  macro_fit:      0.15   # was 0.25
  thesis_news:    0.10   # was 0.20

weights_version: "2026-05-19-v2"
```

Sum = 1.00 (verified).

`macro_view.active=false` is left as a user-configurable gate; the lower
weight (15%) means a disabled macro overlay drags the composite less.

## Acceptance criteria

- `config/scoring.yaml`: `valuation_cost >= 0.25`, `thesis_news <= 0.10`,
  `weights_version` differs from the previous value.
- Sum of factor weights = 1.00 exactly.
- Existing scoring tests still pass with the new weights (no test should
  hard-code 0.10 or 0.20).
- `scoring/instrument_score.py` produces deterministic outputs against
  the new weights.

## Tests to add / update

- `tests/scoring/test_weights_sum.py`: regression test that weights sum
  to 1.0.
- Any snapshot test that locks specific composite scores must be
  regenerated; document the diff.
