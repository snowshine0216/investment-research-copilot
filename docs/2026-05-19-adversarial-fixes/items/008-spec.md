# 008 — Correlation filter caps intra-index

## Why

`proposed_allocation.yaml` selected both `017641 摩根标普500` and
`050025 博时标普500` (two S&P500 share classes = 15.3% of NAV), and both
`018043 天弘纳指100` and `019172 摩根纳指100` (two Nasdaq100 share classes
= 9.7%). `dropped_due_to_correlation: []` proves the correlation filter
either never fired or is configured too leniently.

S&P500 and Nasdaq100 have ~85–90% return correlation; two share classes
of the same index are 99%+. That is not diversification — it is
tracking-error variance dressed up as portfolio breadth.

## What changes

In `src/irc/allocation/correlation_filter.py`, add a deterministic
**tracked-index dedupe** that runs BEFORE the correlation-matrix dedupe:

```python
def drop_duplicate_index_trackers(rows: list[dict]) -> list[dict]:
    """Within each asset_class, group rows by tracked_index. For groups
    with size > 1, keep the highest target_weight (tie-broken by
    instrument_score, then instrument_id) and drop the rest.
    Rows with no tracked_index are passed through unchanged.
    """
```

Wire this into the allocation pipeline (`src/irc/allocation/pipeline.py`)
to run before `drop_correlated_and_renormalize`. The dropped rows are
added to `dropped_due_to_correlation` with a `reason: duplicate_tracked_index`
field so they appear in the allocation diagnostics.

Renormalize the kept rows so the asset-class total is preserved
(reusing the existing `class_total / kept_total` rescaling).

## Acceptance criteria

- Two instruments with the same `tracked_index` cannot both appear in
  the final selected list.
- `proposed_allocation.yaml.dropped_due_to_correlation` is non-empty
  when the input universe contained dup-index rows.
- Sum of `target_weight` + `cash_residual_weight` ≈ 1.0.
- Existing correlation-filter tests pass.

## Tests to add

- `tests/allocation/test_dedupe_tracked_index.py`:
  - Two cn_equity_fund rows with same `tracked_index=hs300` — keep one.
  - Two rows in different asset_class with same `tracked_index` — keep both
    (cross-class is the user's choice).
  - Rows with empty `tracked_index` pass through unchanged.
