# Item 009 — Backfill systematically missing fundamentals metrics

## Problem

Most rows in `outputs/2026-05-17/decision_report.md` show `completeness=0.57` (4/7) or `completeness=0.71` (5/7), below the `MIN_BUY_COMPLETENESS=0.80` threshold. Per `src/irc/decision/completeness.py:9-17`, the seven required metrics are: `expense_ratio`, `drawdown_3y`, `vol_1y`, `downside_capture`, `aum_stability_pct`, `manager_tenure_years`, `holdings_concentration_top10`.

The systematic 4/7 and 5/7 patterns (and the 2-bucket distribution) suggest 2-3 of those metrics are consistently absent for whole categories of instruments, not random per-row noise.

## Approach (investigation first)

1. Read `outputs/2026-05-17/scoring.json` or `decision_report.json`. For each instrument, determine which subset of the 7 required metrics is missing.
2. Tabulate: which metrics are missing for how many instruments, segmented by `asset_class`. Identify the 2-3 metrics that are systematically absent.
3. Trace where each missing metric is *supposed* to be computed (likely in `src/irc/fundamentals/` — `akshare_fundamentals.py`, `derived_metrics.py`, or similar).
4. Backfill: either (a) compute from existing inputs (e.g. `vol_1y` from price history that's already in DuckDB), or (b) source from a new fetch path, or (c) document why it's structurally impossible for some asset class (e.g. `holdings_concentration_top10` doesn't apply to gold ETFs).
5. For asset classes where a metric is structurally inapplicable, exclude it from `required` for that asset class (modify `completeness.py:9-17` to take an asset_class-aware required set).

## Acceptance criteria

- After the change, the percentage of rows with `completeness >= 0.80` increases meaningfully (target: >50% of rows in the regenerated `decision_report.md`, from today's effectively 0%).
- The fix is observable: re-running the scoring stage against existing DuckDB data produces a new `scoring.json` with higher completeness scores for the targeted instruments.
- A test verifies: given an instrument with each of the targeted metrics present in DuckDB, scoring computes `data_completeness=1.0`.

## Files (expected)

- `src/irc/fundamentals/` — depends on which metrics are missing. Likely candidates: `derived_metrics.py`, `akshare_fundamentals.py`.
- `src/irc/decision/completeness.py:9-17` — possibly asset_class-aware required set.
- `tests/fundamentals/` and `tests/decision/` — new regression tests.

## Non-goals

- Lowering `MIN_BUY_COMPLETENESS` from 0.80.
- Re-running ingest (we work against existing DuckDB).
- Backfilling more than the systematically missing 2-3 metrics. (If discovery shows the gap is broader, split into a follow-up item rather than expanding scope here.)
